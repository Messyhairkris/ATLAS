"""The Crew: lifecycle, gates, leash, roster rules, and MCP surface.
A scripted fake model drives every run, so no provider requests are made.

Run: python -m pytest tests/test_crew.py -q
"""

import asyncio
import json
import pathlib
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "v3-service"))

from crew.config import Config, CrewError  # noqa: E402
from crew.core import Crew  # noqa: E402
from crew import playbook  # noqa: E402

INDEX_OK = """SUBMIT
```INDEX.md
---
title: Index
tags: [lab]
last_updated: 2026-09-19
---
# Lab
- [[PLAN]] master plan
- [[runs/RUN-a]] battery 9/12 PASS
```
```notes
- read the run note before quoting its score
```"""


def reply(text):
    return {"content": text, "raw": {"usage": {"total_tokens": 100}}}


class FakeModel:
    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def factory(self, model, job_id, task_type, persona, renew):
        def chat(messages, n):
            renew()
            self.seen.append(messages)
            return reply(self.script.pop(0) if self.script else "…")
        return chat


class CrewTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.vault = self.tmp / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.lab = self.vault / "wiki" / "lab"
        (self.lab / "runs").mkdir(parents=True)
        (self.lab / "PLAN.md").write_text("# Plan\nthesis: small models\n")
        (self.lab / "runs" / "RUN-a.md").write_text(
            "# Run a\nBattery result 9/12. Verdict: PASS\n")
        (self.vault / ".git").mkdir()
        (self.vault / ".git" / "config").write_text("secret")
        self._pb_backup = {t: playbook.load(t) for t in playbook.PREFIX}
        self._env = dict(os.environ)
        # The governor prefers the provider's own quota reading over its own
        # model. Point that at a path with no reading, so the tests below
        # exercise the fallback model deliberately rather than by accident.
        os.environ["ATLAS_QUOTA_FILE"] = str(self.tmp / "no-quota-reading.json")
        os.environ["ATLAS_PROVIDER"] = "synthetic"
        os.environ.pop("ATLAS_DENY_MODELS", None)
        self.cfg = Config({
            "state_home": str(self.tmp / "state"),
            "read_roots": [str(self.vault)],
            "write_roots": [str(self.vault / "wiki"), str(self.tmp / "state" / "outbox")],
            "deny_globs": ["**/.git/**", "**/state/jobs/**"],
            "deny_models": ["Kimi"],
            "telemetry_file": str(self.tmp / "telemetry.jsonl"),
            "defaults": {"max_requests": 6, "lease_seconds": 60},
        })

    def tearDown(self):
        for t, text in self._pb_backup.items():
            playbook._path(t).write_text(text, encoding="utf-8")
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def crew(self, script):
        self.model = FakeModel(script)
        return Crew(self.cfg, chat_factory=self.model.factory)

    def submit_index(self, crew, **extra):
        return crew.submit({"task_type": "vault_index", "title": "Index lab",
                            "folder": str(self.lab), **extra}, "Claude")


class LifecycleTests(CrewTestCase):
    def test_submit_run_review_approve_writes_with_backup(self):
        (self.lab / "INDEX.md").write_text("old index\n")
        c = self.crew(['{"tool": "read_file", "args": {"path": "runs/RUN-a.md"}}',
                       INDEX_OK])
        job = self.submit_index(c, exclude=["INDEX.md"])
        self.assertEqual(job["status"], "ready")
        self.assertEqual(c.tick(), job["task_id"])
        st = c.status(job["task_id"])
        self.assertEqual((st["status"], st["passed_gates"], st["requests"]),
                         ("review", True, 2))
        self.assertEqual((self.lab / "INDEX.md").read_text(), "old index\n")
        res = c.result(job["task_id"])
        self.assertIn("read the run note", res["member_notes"][0])
        out = c.review(job["task_id"], "approve", "Claude",
                       playbook_add=["Quote run scores only after reading the run note."],
                       accept_member_notes=True)
        self.assertEqual(out["status"], "completed")
        self.assertIn("[[runs/RUN-a]]", (self.lab / "INDEX.md").read_text())
        backup = self.cfg.state_home / "jobs" / job["task_id"] / "backup" / "INDEX.md"
        self.assertEqual(backup.read_text(), "old index\n")
        self.assertEqual(len(out["playbook_entries"]), 2)
        types = [n["type"] for n in c.store.nodes_for(job["task_id"])]
        self.assertEqual(types, ["task_submitted", "task_claimed", "output_staged",
                                 "review_submitted", "output_applied",
                                 "playbook_updated"])
        prof = c.roster.profile("Hoss", "vault_index")
        self.assertEqual((prof["samples"], prof["approved"]), (1, 1))

    def test_ungrounded_number_fails_until_note_is_read(self):
        bad = INDEX_OK.replace("9/12", "11/12")
        c = self.crew([bad, '{"tool": "read_file", "args": {"path": "runs/RUN-a.md"}}',
                       INDEX_OK])
        job = self.submit_index(c)
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual(st["status"], "review")
        first_feedback = self.model.seen[1][-1]["content"]
        self.assertIn("grounding", first_feedback)
        self.assertIn("11/12", first_feedback)

    def test_revise_requeues_with_constraint_member_sees(self):
        c = self.crew(["not a tool call", "still nothing"])
        job = self.submit_index(c)
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual((st["status"], st["stop_reason"]),
                         ("failed", "contract_abandoned"))
        c.review(job["task_id"], "revise", "Crush",
                 retry_constraint="Reply with SUBMIT and the INDEX.md block only.")
        self.assertEqual(c.status(job["task_id"])["status"], "ready")
        self.model.script = [INDEX_OK]
        c.tick()
        self.assertIn("REVIEWER CONSTRAINT 1: Reply with SUBMIT",
                      self.model.seen[-1][1]["content"])
        self.assertEqual(c.status(job["task_id"])["status"], "review")

    def test_repeated_tool_calls_end_in_loop_repeat(self):
        call = '{"tool": "list_dir", "args": {"path": "."}}'
        c = self.crew([call] * 6)
        job = self.submit_index(c)
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual((st["status"], st["stop_reason"]), ("failed", "loop_repeat"))
        self.assertEqual(st["requests"], 4)

    def test_request_budget_is_hard(self):
        calls = [json.dumps({"tool": "search", "args": {"pattern": f"x{i}"}})
                 for i in range(10)]
        c = self.crew(calls)
        job = c.submit({"task_type": "vault_index", "title": "t",
                        "folder": str(self.lab), "budget": {"max_requests": 3}}, "K")
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual((st["requests"], st["stop_reason"]), (3, "budget_requests"))

    def test_stale_snapshot_cannot_rerun_a_finished_job(self):
        """Regression (2026-09-19): a scan saw in_progress, the worker then
        finished and released its claim, and the scan's stale copy reset the
        job to ready so it ran twice."""
        c = self.crew([])
        job = self.submit_index(c)
        j = c.store.load(job["task_id"])
        j["status"] = "review"            # the job actually finished
        c.store.save(j)
        self.assertFalse(c._transition(job["task_id"], "in_progress", "ready",
                                       "task_reclaimed"))
        self.assertEqual(c.store.load(job["task_id"])["status"], "review")

    def test_dependencies_block_until_completed(self):
        c = self.crew([INDEX_OK])
        a = self.submit_index(c)
        b = self.submit_index(c, dependencies=[a["task_id"]])
        self.assertEqual(b["status"], "blocked")
        c.tick()
        c.review(a["task_id"], "approve", "Claude")
        self.model.script = [INDEX_OK]
        c.tick()
        self.assertEqual(c.status(b["task_id"])["status"], "review")


class EnforceableReviewTests(CrewTestCase):
    def test_must_read_counts_only_files_the_member_opened(self):
        c = self.crew([INDEX_OK])
        job = self.submit_index(c)
        c.tick()          # passes; PLAN.md was only excerpted in the inventory
        c.review(job["task_id"], "revise", "Claude",
                 retry_constraint="Read the plan before summarizing it.",
                 must_read=["PLAN.md"], ascii_only=True)
        read_plan = '{"tool": "read_file", "args": {"path": "PLAN.md"}}'
        self.model.script = [INDEX_OK, read_plan, INDEX_OK]
        c.tick()
        feedback = self.model.seen[-2][-1]["content"]
        self.assertIn("must-read", feedback)
        self.assertIn("PLAN.md", feedback)
        self.assertEqual(c.status(job["task_id"])["status"], "review")

    def test_ascii_gate_flags_typographic_dashes(self):
        from crew import gates
        self.assertFalse(gates.ascii_only("Run 1 — 2026‑09")["ok"])
        self.assertTrue(gates.ascii_only("Run 1 - 2026-09")["ok"])

    def test_gates_only_attach_on_revise(self):
        c = self.crew([INDEX_OK])
        job = self.submit_index(c)
        c.tick()
        with self.assertRaises(CrewError):
            c.review(job["task_id"], "approve", "Claude", must_read=["PLAN.md"])

    def test_empty_replies_are_nudged_not_abandoned(self):
        c = self.crew(["", "", INDEX_OK])
        job = self.submit_index(c)
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual((st["status"], st["requests"]), ("review", 3))
        self.assertIn("EMPTY REPLY", self.model.seen[-1][-1]["content"])
        self.assertEqual(c.result(job["task_id"])["runs"][0]["requests"], 3)

    def test_native_tool_call_with_null_content_is_accepted(self):
        native = {"content": None, "raw": {"usage": {"total_tokens": 50},
                  "choices": [{"message": {"content": None, "tool_calls": [
                      {"type": "function", "function": {
                          "name": "repo_browser.open_file",
                          "arguments": json.dumps({"path": "runs/RUN-a.md",
                                                   "line_start": 1, "line_end": 40})}}]}}]}}
        c = self.crew([])
        seq = [native, reply(INDEX_OK)]

        def factory(model, job_id, task_type, persona, renew):
            def chat(messages, n):
                self.model.seen.append(messages)
                return seq.pop(0)
            return chat
        c.chat_factory = factory
        job = self.submit_index(c)
        c.tick()
        res = c.result(job["task_id"])
        self.assertEqual(res["status"], "review")
        self.assertTrue(any(f.endswith("RUN-a.md") for f in res["files_read"]))
        self.assertIn('"tool": "read_file"', self.model.seen[-1][2]["content"])
        from crew.agent import native_tool_call
        self.assertEqual(native_tool_call(native),
                         ("read_file", {"path": "runs/RUN-a.md", "start": 1, "lines": 40}))

    def test_three_empty_replies_stop(self):
        c = self.crew(["", "", "", INDEX_OK])
        job = self.submit_index(c)
        c.tick()
        self.assertEqual(c.status(job["task_id"])["stop_reason"], "empty_replies")


class GateTests(CrewTestCase):
    def test_research_digest_citation_must_be_opened(self):
        digest = ("SUBMIT\n```d.md\n---\ntitle: D\ntags: [x]\n---\n"
                  "- Battery scored 9/12 [src: wiki/lab/runs/RUN-a.md]\n```")
        c = self.crew([digest, '{"tool": "read_file", "args": '
                       '{"path": "wiki/lab/runs/RUN-a.md"}}', digest])
        job = c.submit({"task_type": "research_digest", "title": "Battery score",
                        "instructions": "What did the battery score?",
                        "output": {"files": ["d.md"]}}, "Claude")
        c.tick()
        first_feedback = self.model.seen[1][-1]["content"]
        self.assertIn("never opened", first_feedback)
        self.assertEqual(c.status(job["task_id"])["status"], "review")

    def test_citation_leniency_where_it_is_safe(self):
        from crew import gates
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        tb.read_file("wiki/lab/PLAN.md")
        text = ("| Command | Action |\n|---|---|\n"
                "| new line | inserts a break [[src: wiki/lab/PLAN.md]] |\n"
                "## Open questions\n- Does it work offline?\n")
        self.assertTrue(gates.cited_lines(text, tb)["ok"])
        self.assertTrue(gates.wikilinks_resolve(text, self.vault, None)["ok"])
        self.assertFalse(gates.cited_lines("## Findings\n- uncited claim\n", tb)["ok"])

    def test_labels_emphasis_and_source_lists_are_not_claims(self):
        from crew import gates
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        tb.read_file("wiki/lab/PLAN.md")
        text = ("## Findings\n- **Command-line options** –\n"
                "  - `-v` picks a voice [src: wiki/lab/PLAN.md]\n"
                "*Note: feedback wording not in source.*\n"
                "## Sources\n- [wiki/lab/PLAN.md] - the plan\n")
        self.assertTrue(gates.cited_lines(text, tb)["ok"], gates.cited_lines(text, tb))
        self.assertFalse(gates.cited_lines("## Findings\n- `-r` sets the rate\n", tb)["ok"])

    def test_citation_line_locators_are_stripped(self):
        from crew import gates
        self.assertEqual(gates.citations("x [src: a/B.md#71-86] y [src: e.py:120]"),
                         ["a/B.md", "e.py"])

    def test_github_repo_url_fetches_readme_via_api(self):
        from unittest import mock
        from crew.tools import Evidence, Toolbox
        self.cfg.fetch_allowlist = ["github.com"]
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        seen = {}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b"# wsay\nWindows say"

        def fake(req, timeout):
            seen["url"], seen["accept"] = req.full_url, req.get_header("Accept")
            return Resp()
        with mock.patch("crew.tools.urllib.request.urlopen", side_effect=fake):
            out = tb.fetch_url("https://github.com/p-groarke/wsay")
        self.assertEqual(seen["url"], "https://api.github.com/repos/p-groarke/wsay/readme")
        self.assertEqual(seen["accept"], "application/vnd.github.raw")
        self.assertIn("Windows say", out)
        self.assertIsNotNone(tb.evidence_key("https://github.com/p-groarke/wsay"))

    def test_uncited_item_fails(self):
        digest = ("SUBMIT\n```d.md\n---\ntitle: D\ntags: [x]\n---\n"
                  "- The plan is about small models\n```")
        c = self.crew([digest, digest])
        job = c.submit({"task_type": "research_digest", "title": "t",
                        "instructions": "q", "output": {"files": ["d.md"]}}, "K")
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual(st["status"], "failed")
        self.assertTrue(any("citation" in g for g in st["failed_gates"]))

    def test_organize_plan_rejects_escape_and_missing_source(self):
        plan = json.dumps({"moves": [
            {"from": "PLAN.md", "to": "../../outside.md", "why": "x"},
            {"from": "nope.md", "to": "a.md", "why": "y"}], "tags": [], "notes": ""})
        c = self.crew([f"SUBMIT\n```plan.json\n{plan}\n```"] * 2)
        job = c.submit({"task_type": "organize_plan", "title": "tidy",
                        "folder": str(self.lab)}, "K")
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual(st["status"], "failed")
        detail = " ".join(st["failed_gates"])
        self.assertIn("leaves", detail)
        self.assertIn("does not exist", detail)


class TestTriageTests(CrewTestCase):
    """The harness runs the suite; the member may not invent what it said."""

    def setUp(self):
        super().setUp()
        self.proj = self.vault / "wiki" / "proj"
        self.proj.mkdir(parents=True)
        (self.proj / "test_thing.py").write_text(
            "def test_adds():\n    assert 1 + 1 == 3\n\n\ndef test_ok():\n    assert True\n")
        self.cfg.data["test_commands"] = {
            "pytest": {"argv": ["{python}", "-m", "pytest", "-q"], "timeout_s": 120}}

    def _submit(self, c, **extra):
        return c.submit({"task_type": "test_triage", "title": "triage",
                         "project_root": str(self.proj), **extra}, "Claude")

    def test_member_cannot_choose_the_command(self):
        c = self.crew([])
        with self.assertRaises(CrewError):
            self._submit(c, test_command="rm -rf /")

    def test_harness_runs_suite_and_report_must_match_it(self):
        good = ("SUBMIT\n```test-triage-proj.md\n---\ntitle: T\ntags: [test]\n---\n"
                "1 failed, 1 passed [src: run_log]\n\n## Failures\n"
                "- test_adds: assert 1 + 1 == 3 [src: run_log]\n```")
        invented = good.replace("test_adds: assert 1 + 1 == 3",
                                "test_missing_feature: assert 1 + 1 == 3")
        c = self.crew([invented, good])
        job = self._submit(c)
        c.tick()
        res = c.result(job["task_id"])
        self.assertEqual(res["status"], "review")
        log = (self.cfg.state_home / "jobs" / job["task_id"] / "run_log.txt").read_text()
        self.assertIn("1 failed", log)          # the harness really ran pytest
        feedback = self.model.seen[-1][-1]["content"]
        self.assertIn("no-invented-tests", feedback)
        self.assertIn("test_missing_feature", feedback)

    def test_absence_claims_need_an_opened_source_or_the_inferred_label(self):
        from crew import gates
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        tb.read_file("wiki/lab/PLAN.md")                       # opened
        tb.evidence.add("run_log", "0 failed, 19 passed", opened=True)
        bad = "## Gaps\n- No test covers audio routing [src: run_log]\n"
        good_cited = ("## Gaps\n- Nothing in the plan covers audio routing "
                      "[src: wiki/lab/PLAN.md]\n")
        good_marked = "## Gaps\n- No test covers audio routing (inferred)\n"
        exempt = "## Open questions\n- Is audio routing tested anywhere?\n"
        # run_log is opened evidence, so a log-cited absence claim passes only
        # when the log itself is the thing being read; that is the point of the
        # gate: it must cite something it actually looked in.
        self.assertTrue(gates.absence_claims(good_cited, tb)["ok"])
        self.assertTrue(gates.absence_claims(good_marked, tb)["ok"])
        self.assertTrue(gates.absence_claims(exempt, tb)["ok"])
        tb2 = Toolbox(self.cfg, [self.vault], Evidence())
        self.assertFalse(gates.absence_claims(bad, tb2)["ok"])
        detail = gates.absence_claims(bad, tb2)["detail"]
        self.assertIn("(inferred)", detail)

    def test_absence_patterns_catch_the_common_phrasings(self):
        from crew import gates
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        for line in ["- no test exercises the TTS pipeline",
                     "- routing is untested",
                     "- the log never reports a device change",
                     "- volume handling is missing",
                     "- nothing verifies the fallback tone",
                     "- there is no such setting"]:
            self.assertFalse(gates.absence_claims("## Gaps\n" + line + "\n", tb)["ok"],
                             f"should be caught: {line}")
        self.assertTrue(gates.absence_claims(
            "## Findings\n- routing sends speech to the headset [src: x]\n", tb)["ok"])

    def test_a_control_that_never_opened_must_be_reported(self):
        """Kris watched a sweep move past "open the logs" while nothing opened,
        and the report called the run clean. The run log now records it, and the
        gate refuses a report that leaves it out."""
        from crew import gates
        log = ('{"event": "nothing_opened", "control": "Open Log", '
               '"waited_s": 12.1}\n'
               '{"event": "stalled", "control": "Export", "waited_s": 12.0}\n')
        clean = "Every control responded and the run looks healthy."
        self.assertFalse(gates.reports_stalls(clean, log)["ok"])
        honest = ("Open Log never opened anything within 12.1s, and Export was "
                  "still busy when the wait ran out.")
        self.assertTrue(gates.reports_stalls(honest, log)["ok"])
        self.assertTrue(gates.reports_stalls(clean, "no such events")["ok"])

    def test_totals_line_must_be_quoted_verbatim(self):
        from crew import gates
        log = "....\n=========== 3 failed, 29 passed in 1.21s ==========="
        self.assertFalse(gates.quotes_the_totals("mostly fine", log)["ok"])
        self.assertTrue(gates.quotes_the_totals(
            "the suite reports 3 failed, 29 passed today", log)["ok"])


class FenceLabelTests(CrewTestCase):
    """A member that labels its fence with a LANGUAGE has still submitted a good
    file; our parser misread the label and failed a real task on 2026-09-20."""

    FENCE = chr(96) * 3

    def _reply(self, tag: str) -> str:
        lines = ["SUBMIT", self.FENCE + tag, "VALUE = 1", self.FENCE, ""]
        return chr(10).join(lines)

    def test_a_language_tag_is_not_a_filename(self):
        from crew.agent import parse_reply
        for tag in ("python", "py", "bash", "ini", "yaml", "diff", "javascript"):
            kind, files, _notes = parse_reply(self._reply(tag), ["thing.py"])
            self.assertEqual(kind, "submit", tag)
            self.assertEqual(sorted(files), ["thing.py"], tag)

    def test_a_real_filename_still_wins(self):
        from crew.agent import parse_reply
        kind, files, _ = parse_reply(self._reply("thing.py"), ["thing.py"])
        self.assertEqual((kind, sorted(files)), ("submit", ["thing.py"]))

    def test_two_expected_files_will_not_guess(self):
        """With more than one output a language tag is genuinely ambiguous, so the
        harness must not pick one."""
        from crew.agent import parse_reply
        kind, files, _ = parse_reply(self._reply("python"), ["a.py", "b.py"])
        picked = sorted(files) if kind == "submit" else []
        self.assertNotEqual(picked, ["a.py"])


class CodeTaskTests(CrewTestCase):
    """The only task types whose output is executed. These tests are the reason
    that is not reckless."""

    GOOD = ("from dataclasses import dataclass\n\n"
            "VALUE = 3\n\n\n"
            "def pick(items):\n"
            "    \"\"\"First item or None.\"\"\"\n"
            "    return items[0] if items else None\n")

    def test_scan_allows_pure_logic(self):
        from crew import codetask
        self.assertEqual(codetask.scan(self.GOOD), [])

    def test_scan_allows_ordinary_method_names(self):
        """str.replace and list.remove are not escapes; an early version of the
        blocklist failed honest code on them."""
        from crew import codetask
        src = "def f(s, items):\n    items.remove(1)\n    return s.replace('a', 'b')\n"
        self.assertEqual(codetask.scan(src), [])

    def test_scan_refuses_the_ways_out(self):
        from crew import codetask
        for src in ("import os\n",
                    "from subprocess import run\n",
                    "import socket\n",
                    "def f():\n    return open('x').read()\n",
                    "def f():\n    return eval('1')\n",
                    "def f(o):\n    return o.__class__.__bases__\n",
                    "def f(o):\n    return o.system('dir')\n",
                    "from . import sibling\n"):
            self.assertTrue(codetask.scan(src), f"should be refused: {src!r}")

    def test_dependency_modules_may_be_imported_but_nothing_else(self):
        from crew import codetask
        src = "import verbalize\n"
        self.assertTrue(codetask.scan(src))
        self.assertEqual(codetask.scan(src, extra_imports=["verbalize"]), [])

    def test_run_tests_refuses_unsafe_source_before_executing_it(self):
        from crew import codetask
        ok, out, detail = codetask.run_tests(
            {"m.py": "import os\n"}, {"test_m.py": "def test_x():\n    assert True\n"})
        self.assertFalse(ok)
        self.assertIn("REFUSED", out)
        self.assertTrue(detail["blocked"])

    def test_run_tests_reports_a_real_pass_and_a_real_failure(self):
        from crew import codetask
        ok, out, _ = codetask.run_tests(
            {"m.py": self.GOOD},
            {"test_m.py": "import m\ndef test_pick():\n    assert m.pick([1]) == 1\n"})
        self.assertTrue(ok, out)
        ok2, out2, _ = codetask.run_tests(
            {"m.py": self.GOOD},
            {"test_m.py": "import m\ndef test_pick():\n    assert m.pick([1]) == 2\n"})
        self.assertFalse(ok2)
        self.assertIn("test_pick", codetask.summarize(out2))

    def test_run_tests_stops_an_infinite_loop(self):
        from crew import codetask
        ok, out, _ = codetask.run_tests(
            {"m.py": "def spin():\n    while True:\n        pass\n"},
            {"test_m.py": "import m\ndef test_spin():\n    m.spin()\n"},
            timeout_s=5)
        self.assertFalse(ok)
        self.assertIn("TIMEOUT", out)

    def test_api_and_stub_gates(self):
        from crew import gates
        self.assertTrue(gates.defines_api(self.GOOD, ["VALUE", "pick"])["ok"])
        self.assertFalse(gates.defines_api(self.GOOD, ["VALUE", "missing"])["ok"])
        self.assertTrue(gates.not_stubbed(self.GOOD, ["pick"])["ok"])
        for stub in ("def pick(x):\n    pass\n",
                     "def pick(x):\n    ...\n",
                     "def pick(x):\n    raise NotImplementedError\n",
                     "def pick(x):\n    \"\"\"doc\"\"\"\n    pass\n"):
            self.assertFalse(gates.not_stubbed(stub, ["pick"])["ok"], stub)

    def test_enough_tests_counts_test_functions(self):
        from crew import gates
        src = "".join(f"def test_{i}():\n    assert True\n\n" for i in range(4))
        self.assertTrue(gates.enough_tests(src, 4)["ok"])
        self.assertFalse(gates.enough_tests(src, 5)["ok"])

    def test_a_module_that_writes_files_fails_even_if_tests_pass(self):
        """A module that leaves files behind is not pure, whatever its tests say.
        open() is already refused, so this proves the leftover check itself."""
        from crew import gates
        step = gates.hidden_tests_pass(
            {"m.py": self.GOOD},
            {"test_m.py": ("import m\n"
                           "def test_write(tmp_path):\n"
                           "    import pathlib\n"
                           "    pathlib.Path('litter.txt').write_text('x')\n"
                           "    assert m.pick([1]) == 1\n")},
            60)
        self.assertFalse(step["ok"])
        self.assertIn("writing to disk", step["detail"])

    def test_code_task_spec_is_validated_at_submit(self):
        c = self.crew([])
        contract = self.tmp / "contract.md"
        contract.write_text("api: pick\n", encoding="utf-8")
        base = {"task_type": "code_task", "title": "t",
                "contract": str(contract), "api": ["pick"],
                "output": {"root": str(self.cfg.write_roots[0] / "workspace")}}
        with self.assertRaises(CrewError):        # module must be a .py file name
            c.submit({**base, "module": "src/thing.py"}, "K")
        with self.assertRaises(CrewError):        # api may not be empty
            c.submit({**base, "module": "thing.py", "api": []}, "K")
        with self.assertRaises(CrewError):        # contract must exist
            c.submit({**base, "module": "thing.py",
                      "contract": str(self.tmp / "nope.md")}, "K")


class CampaignTests(CrewTestCase):
    def _spec(self):
        contract = self.tmp / "c.md"
        contract.write_text("api: a\n", encoding="utf-8")
        return {"name": "unit", "senior": "none", "max_requests": 5,
                "teams": {"A": {"author": "Hoss", "tester": "Qwen"}},
                "tasks": [{"id": "one", "team": "A", "module": "one.py",
                           "contract": str(contract), "api": ["a"]},
                          {"id": "two", "team": "A", "module": "two.py",
                           "contract": str(contract), "api": ["a"],
                           "depends": ["one"]}]}

    def test_planning_adds_a_tester_task_for_each_module(self):
        from crew.campaign import Campaign
        c = Campaign(self._spec(), cfg=self.cfg, crew=self.crew([]), quiet=True)
        self.assertEqual(sorted(c.tasks), ["one", "one-tests", "two", "two-tests"])
        self.assertEqual(c.tasks["one"]["member"], "Hoss")
        self.assertEqual(c.tasks["one-tests"]["member"], "Qwen")
        self.assertEqual(c.tasks["one-tests"]["depends"], ["one"])

    def test_only_unblocked_tasks_are_ready(self):
        from crew.campaign import Campaign
        c = Campaign(self._spec(), cfg=self.cfg, crew=self.crew([]), quiet=True)
        self.assertEqual([t["id"] for t in c._ready()], ["one"])
        c.tasks["one"]["state"] = "accepted"
        self.assertEqual(sorted(t["id"] for t in c._ready()), ["one-tests", "two"])

    def test_dependency_modules_are_transitive(self):
        """A tester of two.py needs one.py as well, because two.py imports it.
        The dry run failed exactly here."""
        from crew.campaign import Campaign
        c = Campaign(self._spec(), cfg=self.cfg, crew=self.crew([]), quiet=True)
        paths = c._module_paths(c.tasks["two-tests"])
        self.assertEqual([pathlib.Path(p).name for p in paths],
                         ["one.py", "two.py"])

    def test_a_task_can_build_on_a_module_accepted_earlier(self):
        """profiles.py had to import devices.py, accepted in a different campaign
        and already in the workspace. `depends` cannot say that - it means "a task
        here that must finish first" - so `uses` does."""
        from crew.campaign import Campaign

        spec = self._spec()
        spec["tasks"][0]["uses"] = ["devices.py"]
        c = Campaign(spec, cfg=self.cfg, crew=self.crew([]), quiet=True)
        (c.workspace / "devices.py").write_text("X = 1\n", encoding="utf-8")
        names = [pathlib.Path(p).name for p in c._module_paths(c.tasks["one"])]
        self.assertEqual(names, ["devices.py"])
        # the tester gets it too, or every test fails on the import line
        names = [pathlib.Path(p).name for p in c._module_paths(c.tasks["one-tests"])]
        self.assertEqual(names, ["devices.py", "one.py"])

    def test_using_an_earlier_module_does_not_delay_the_start(self):
        from crew.campaign import Campaign

        spec = self._spec()
        spec["tasks"][0]["uses"] = ["devices.py"]
        c = Campaign(spec, cfg=self.cfg, crew=self.crew([]), quiet=True)
        (c.workspace / "devices.py").write_text("X = 1\n", encoding="utf-8")
        self.assertEqual([t["id"] for t in c._ready()], ["one"])

    def test_a_missing_earlier_module_is_refused_loudly(self):
        """Quietly handing the author nothing would look like the model failing."""
        from crew.campaign import Campaign
        from crew.config import CrewError

        spec = self._spec()
        spec["tasks"][0]["uses"] = ["not_there.py"]
        c = Campaign(spec, cfg=self.cfg, crew=self.crew([]), quiet=True)
        with self.assertRaises(CrewError):
            c._module_paths(c.tasks["one"])

    def test_the_budget_and_the_deadline_both_stop_new_work(self):
        from crew.campaign import Campaign
        spec = self._spec()
        c = Campaign(spec, cfg=self.cfg, crew=self.crew([]), quiet=True)
        self.assertIsNone(c.stop_reason())
        c.requests_used = 99
        self.assertIn("budget", c.stop_reason())
        c.requests_used = 0
        c.deadline = time.time() - 1
        self.assertIn("deadline", c.stop_reason())

    def test_report_names_the_failed_check_and_recommends_something(self):
        from crew import report
        from crew.campaign import Campaign
        c = Campaign(self._spec(), cfg=self.cfg, crew=self.crew([]), quiet=True)
        c.tasks["one"].update(state="accepted", attempts=1, requests=4, tokens=10)
        c.tasks["two"].update(state="failed", attempts=3, requests=9,
                              failed_gates=[["hidden tests: two of them fail"]])
        out = report.campaign_report(c)
        self.assertEqual(out["data"]["outcome"], "partial")
        self.assertIn("hidden tests", out["data"]["failed_gate_counts"])
        self.assertIn("## What to change next time", out["markdown"])
        self.assertIn("three or more attempts", out["markdown"])


class SafetyTests(CrewTestCase):
    def test_tools_refuse_outside_roots_and_denied(self):
        from crew.tools import Evidence, Toolbox, ToolError
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        with self.assertRaises(ToolError):
            tb.read_file(str(self.tmp / "state" / "x.md"))
        with self.assertRaises(ToolError):
            tb.read_file(".git/config")
        with self.assertRaises(ToolError):
            tb.read_file("../../etc")
        self.assertNotIn(".git", tb.list_dir("."))
        with self.assertRaises(ToolError):
            tb.fetch_url("https://example.com/")

    def test_denied_member_and_unknown_member(self):
        c = self.crew([])
        with self.assertRaises(CrewError):
            self.submit_index(c, assigned_to="Kimi")
        with self.assertRaises(CrewError):
            self.submit_index(c, assigned_to="Nobody")

    def test_output_outside_write_roots_refused_at_submit(self):
        c = self.crew([])
        with self.assertRaises(CrewError):
            c.submit({"task_type": "research_digest", "title": "t",
                      "instructions": "q", "output": {"root": str(self.tmp)}}, "K")

    def test_renew_survives_a_locked_lock_file(self):
        from unittest import mock
        c = self.crew([])
        self.assertTrue(c.store.try_claim("job-y"))
        with mock.patch("crew.store.os.replace", side_effect=PermissionError(5, "denied")), \
                mock.patch("crew.store.time.sleep"):
            c.store.renew("job-y")          # must not raise
        self.assertEqual(list(c.store.claims_dir.glob("*.tmp")), [])

    def test_atomic_write_retries_transient_sharing_violation(self):
        from unittest import mock
        from crew import store
        target = self.tmp / "f.json"
        real = os.replace
        calls = {"n": 0}

        def flaky(a, b):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(5, "denied")
            return real(a, b)
        with mock.patch("crew.store.os.replace", side_effect=flaky), \
                mock.patch("crew.store.time.sleep"):
            store._atomic_write(target, "ok")
        self.assertEqual(target.read_text(), "ok")

    def test_claims_are_exclusive_and_expire(self):
        c = self.crew([])
        self.assertTrue(c.store.try_claim("job-x"))
        self.assertFalse(c.store.try_claim("job-x"))
        (c.store.claims_dir / "job-x.lock").write_text(
            json.dumps({"owner": "dead", "lease_until": time.time() - 1}))
        self.assertTrue(c.store.try_claim("job-x"))


class RosterTests(CrewTestCase):
    def test_promotion_rules(self):
        c = self.crew([])
        r = c.roster
        with self.assertRaises(CrewError):
            r.promote("Hoss", "vault_index", "Supervised", "Kris")   # skip
        r.record_run("Hoss", "vault_index", "j1", False, False, 3, 100)
        with self.assertRaises(CrewError):
            r.promote("Hoss", "vault_index", "Checkpoint", "Kris")   # after failure
        for i in range(5):
            r.record_run("Hoss", "vault_index", f"k{i}", True, True, 2, 100)
            r.record_review("Hoss", "vault_index", f"k{i}", "approve")
        self.assertIn("eligible", r.suggestion("Hoss", "vault_index"))
        r.promote("Hoss", "vault_index", "Checkpoint", "Kris")
        self.assertIsNone(r.suggestion("Hoss", "vault_index"))

    def test_supervised_auto_applies_with_notice(self):
        c = self.crew([INDEX_OK])
        data = {"Hoss": {"vault_index": {**c.roster._blank(), "stage": "Supervised"}}}
        c.roster._write(data)
        job = self.submit_index(c)
        c.tick()
        st = c.status(job["task_id"])
        self.assertEqual((st["status"], st["notice"]), ("completed", True))
        self.assertTrue((self.lab / "INDEX.md").exists())
        self.assertEqual(len(c.inbox()["auto_applied_notices"]), 1)
        c.review(job["task_id"], "acknowledge", "Kris")
        self.assertEqual(len(c.inbox()["auto_applied_notices"]), 0)


class RateBudgetTests(CrewTestCase):
    def _ledger(self, rows, minutes_ago=1):
        import datetime
        path = self.tmp / "telemetry.jsonl"
        stamp = (datetime.datetime.now()
                 - datetime.timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        path.write_text("".join(
            json.dumps({"ts": stamp, "requests": 1, "model": "m"}) + "\n"
            for _ in range(rows)), encoding="utf-8")
        os.environ["ATLAS_TELEMETRY_FILE"] = str(path)
        return path

    def test_counts_only_requests_inside_the_window(self):
        from crew.ratelimit import RateWindow
        self.cfg.data["rate_limit"] = {"mode": "window", "window_seconds": 3600, "max_requests": 100,
                                       "reserve": 10, "min_headroom": 4}
        self._ledger(5, minutes_ago=1)
        self.assertEqual(RateWindow(self.cfg).used(), 5)
        self._ledger(5, minutes_ago=120)          # aged out
        self.assertEqual(RateWindow(self.cfg).used(), 0)
        self.assertEqual(RateWindow(self.cfg).remaining(), 90)

    def test_gate_holds_a_job_when_the_window_is_full(self):
        from crew.ratelimit import RateWindow
        self.cfg.data["rate_limit"] = {"mode": "window", "window_seconds": 3600, "max_requests": 10,
                                       "reserve": 2, "min_headroom": 4}
        self._ledger(8, minutes_ago=5)
        rw = RateWindow(self.cfg)
        self.assertEqual(rw.remaining(), 0)
        ok, wait, detail = rw.gate(6)
        self.assertFalse(ok)
        self.assertGreater(wait, 0)
        self.assertIn("requests left", detail)

    def test_partial_headroom_still_starts(self):
        from crew.ratelimit import RateWindow
        self.cfg.data["rate_limit"] = {"mode": "window", "window_seconds": 3600, "max_requests": 10,
                                       "reserve": 0, "min_headroom": 4}
        self._ledger(5, minutes_ago=5)
        self.assertTrue(RateWindow(self.cfg).gate(12)[0])   # 5 left, want 12

    def test_worker_holds_jobs_and_logs_once(self):
        self.cfg.data["rate_limit"] = {"mode": "window", "window_seconds": 3600, "max_requests": 4,
                                       "reserve": 2, "min_headroom": 4}
        self._ledger(4, minutes_ago=1)
        c = self.crew([INDEX_OK])
        job = self.submit_index(c)
        self.assertIsNone(c.tick())
        self.assertEqual(c.status(job["task_id"])["status"], "ready")
        self.assertGreater(c._hold, 0)
        self.assertEqual([n["type"] for n in c.store.nodes_for(job["task_id"])],
                         ["task_submitted", "rate_hold"])


class ProviderQuotaTests(CrewTestCase):
    """Synthetic reports the live limits in `x-synthetic-quotas`, and a reading
    beats a model. Measured 2026-09-20: a cheap-model call costs 0.0333 requests,
    not 1, and the binding limit was the weekly credit pool at 6.9%, which the
    bucket model could not see at all."""

    def _with_reading(self, **over):
        import sys
        sys.path.insert(0, str(REPO_ROOT / "v3-service"))
        from providers import quotas
        snapshot = {"rollingFiveHourLimit": {"remaining": 999.9, "max": 1000,
                                            "tickPercent": 0.05,
                                            "nextTickAt": "2026-09-20T20:08:24Z",
                                            "limited": False},
                    "weeklyTokenLimit": {"maxCredits": "$48.00",
                                         "remainingCredits": "$24.00",
                                         "percentRemaining": 50.0,
                                         "nextRegenCredits": "$0.96",
                                         "nextRegenAt": "2026-09-20T20:59:13Z"}}
        for key, value in over.items():
            section, field = key.split("__", 1)
            snapshot[section][field] = value
        os.environ["ATLAS_QUOTA_FILE"] = str(self.tmp / "quota.json")
        quotas.record(snapshot)
        self.cfg.data["rate_limit"] = {"mode": "bucket", "max_requests": 1000,
                                       "regen_percent": 5, "regen_hours": 3,
                                       "reserve": 10, "min_headroom": 4,
                                       "credit_reserve_percent": 5}
        from crew.ratelimit import RateWindow
        return RateWindow(self.cfg)

    def test_money_is_parsed_not_guessed(self):
        import sys
        sys.path.insert(0, str(REPO_ROOT / "v3-service"))
        from providers import quotas
        self.assertEqual(quotas._money("$3.32"), 3.32)
        self.assertEqual(quotas._money("$48.00"), 48.0)
        self.assertIsNone(quotas._money(None))
        self.assertIsNone(quotas._money("plenty"))

    def test_a_healthy_reading_lets_work_start(self):
        ok, wait, detail = self._with_reading().gate(14)
        self.assertTrue(ok)
        self.assertEqual(wait, 0.0)
        self.assertIn("provider reports", detail)

    def test_the_credit_pool_can_stop_a_campaign_even_with_requests_to_spare(self):
        """The case that was invisible before: 99.99% of requests available and
        the weekly credits nearly gone."""
        rate = self._with_reading(weeklyTokenLimit__percentRemaining=3.0,
                                  weeklyTokenLimit__remainingCredits="$1.44")
        ok, wait, detail = rate.gate(14)
        self.assertFalse(ok)
        self.assertGreater(wait, 0)
        self.assertIn("weekly credits", detail)
        self.assertIn("reserve", detail)

    def test_a_reported_request_limit_stops_work(self):
        rate = self._with_reading(rollingFiveHourLimit__limited=True)
        ok, _wait, detail = rate.gate(1)
        self.assertFalse(ok)
        self.assertIn("five-hour request limit", detail)

    def test_the_binding_limit_is_named(self):
        import sys
        sys.path.insert(0, str(REPO_ROOT / "v3-service"))
        from providers import quotas
        self._with_reading(weeklyTokenLimit__percentRemaining=6.9)
        self.assertEqual(quotas.binding_limit()["limit"], "credits")
        self._with_reading(rollingFiveHourLimit__remaining=10.0)
        self.assertEqual(quotas.binding_limit()["limit"], "requests")

    def test_no_reading_falls_back_to_the_model(self):
        os.environ["ATLAS_QUOTA_FILE"] = str(self.tmp / "missing.json")
        self.cfg.data["rate_limit"] = {"mode": "bucket", "max_requests": 100,
                                       "regen_percent": 5, "regen_hours": 3,
                                       "reserve": 10, "min_headroom": 4}
        from crew.ratelimit import RateWindow
        rate = RateWindow(self.cfg)
        self.assertIsNone(rate.provider_gate(1))
        ok, _wait, _detail = rate.gate(1)
        self.assertTrue(ok)


class BucketBudgetTests(CrewTestCase):
    """The fallback model, used only before the provider has answered us once:
    the allowance refills a percentage of capacity on a timer."""

    def _bucket(self, **over):
        self.cfg.data["rate_limit"] = {"mode": "bucket", "max_requests": 100,
                                       "regen_percent": 5, "regen_hours": 3,
                                       "reserve": 10, "min_headroom": 4, **over}
        from crew.ratelimit import RateWindow
        return RateWindow(self.cfg)

    def test_spend_lowers_the_level_and_refill_is_time_based(self):
        import datetime
        log = self.tmp / "t.jsonl"
        os.environ["ATLAS_TELEMETRY_FILE"] = str(log)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        log.write_text("".join(json.dumps({"ts": now, "requests": 1}) + "\n"
                               for _ in range(30)), encoding="utf-8")
        rw = self._bucket()
        self.assertEqual(rw.remaining(), 60)          # 100 - 30 spent - 10 reserve
        state = json.loads((self.cfg.state_home / "rate_state.json").read_text())
        self.assertEqual(state["ledger_total"], 30)
        # rewind the clock 6h in the saved state: 2 refills of 5 requests
        state["ts"] -= 6 * 3600
        (self.cfg.state_home / "rate_state.json").write_text(json.dumps(state))
        self.assertEqual(self._bucket().remaining(), 70)

    def test_refill_wait_is_reported_and_capped_at_capacity(self):
        rw = self._bucket(max_requests=10, reserve=9)
        log = self.tmp / "t2.jsonl"
        os.environ["ATLAS_TELEMETRY_FILE"] = str(log)
        log.write_text(json.dumps({"ts": "2026-09-19T00:00:00", "requests": 9}) + chr(10),
                       encoding="utf-8")
        rw = self._bucket(max_requests=10, reserve=9)
        ok, wait, detail = rw.gate(4)
        self.assertFalse(ok)
        self.assertIn("5% per 3h", detail)
        self.assertGreater(wait, 60)
        report = rw.report()
        self.assertEqual(report["mode"], "bucket")
        self.assertIn("requests/hour", report["refill"])


class AutofixTests(CrewTestCase):
    """Near-misses are corrected for free and recorded; meaning is never
    guessed at."""

    def test_typography_and_near_miss_names_are_corrected(self):
        from crew import autofix
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        tb.read_file("wiki/lab/PLAN.md")
        log = '{"control": "Bulleted list"}\n0 failed, 23 passed in 97.73s'
        text = ('The “Bulletted list” button – fine ‑ ok. '
                'Summary: "0 failed, 23 passed in 97.73 s".')
        fixed, notes = autofix.apply({"r.md": text}, log, tb)
        out = fixed["r.md"]
        self.assertIn('"Bulleted list"', out)          # typo corrected
        self.assertNotIn("–", out)                 # en dash normalized
        self.assertNotIn("‑", out)                 # nb hyphen normalized
        self.assertTrue(any("corrected name" in n for n in notes))
        self.assertTrue(any("typographic" in n for n in notes))

    def test_citation_typo_is_corrected_to_an_observed_source(self):
        from crew import autofix
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        tb.read_file("wiki/lab/runs/RUN-a.md")
        fixed, notes = autofix.apply(
            {"r.md": "- battery scored 9/12 [src: wiki/lab/runs/RUN-á.md]\n"}, "", tb)
        self.assertIn("RUN-a.md", fixed["r.md"])
        self.assertTrue(any("corrected citation" in n for n in notes))

    def test_meaning_is_never_invented(self):
        from crew import autofix
        from crew.tools import Evidence, Toolbox
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        log = '{"control": "Bold"}'
        # a wholly different name is NOT a typo: leave it for the gate to fail
        fixed, notes = autofix.apply({"r.md": 'the "Ghost Button" did nothing'}, log, tb)
        self.assertIn("Ghost Button", fixed["r.md"])
        self.assertEqual(notes, [])

    def test_autofix_runs_before_gates_and_is_reported(self):
        good = INDEX_OK.replace("master plan", "master plan – ok")
        c = self.crew([good])
        job = self.submit_index(c)
        c.tick()
        res = c.result(job["task_id"])
        self.assertEqual(res["status"], "review")
        self.assertTrue(any("typographic" in n for n in res["harness_autofixes"]))
        applied = (self.cfg.state_home / "jobs" / job["task_id"] / "output" / "INDEX.md")
        self.assertNotIn("–", applied.read_text(encoding="utf-8"))


class ReviewHandoffTests(unittest.TestCase):
    """Kris, after using the desk: "Other than not knowing an LLM received the
    info, it worked... I would add a button that confirms everything is complete
    and tells the user the next steps"."""

    def setUp(self):
        from crew.runners import review_desk

        self.rd = review_desk
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._home = review_desk.home
        review_desk.home = lambda: self.tmp / "review"
        self.addCleanup(setattr, review_desk, "home", self._home)
        self.paths = {}
        for name in ("alpha.py", "beta.py", "gamma.py", "delta.py"):
            path = self.tmp / name
            path.write_text(f"# {name}\nvalue = 1\n", encoding="utf-8")
            self.paths[name] = path

    def queue(self, *decisions):
        from crew.reviewdesk import review_index

        items = []
        for name, decision, note in decisions:
            item = review_index.new_item(item_id=f"file:{name}", title=name,
                                        path=str(self.paths[name]), origin="test")
            if decision:
                item.update(decision=decision, note=note, state="decided",
                            decided_at="2026-09-20T12:00:00")
            items.append(item)
        self.rd.save_queue(items)
        return items

    def test_only_complete_decisions_are_ready_and_defer_never_is(self):
        items = self.queue(("alpha.py", "approve", ""),
                           ("beta.py", "reject", "this name says nothing at all"),
                           ("gamma.py", "defer", "not until the spec settles here"),
                           ("delta.py", "", ""))
        ready = [i["item_id"] for i in self.rd.ready_to_send(items)]
        self.assertEqual(ready, ["file:alpha.py", "file:beta.py"])

    def test_an_incomplete_reject_is_not_handed_over(self):
        items = self.queue(("alpha.py", "reject", "no"))
        self.assertEqual(self.rd.ready_to_send(items), [])

    def test_send_records_the_action_for_every_item(self):
        items = self.queue(("alpha.py", "approve", ""),
                           ("beta.py", "question", "why does this return a one?"))
        handoff = self.rd.send_to_agent(items)
        self.assertEqual(handoff["count"], 2)
        actions = {r["item_id"]: r["action"] for r in handoff["items"]}
        self.assertEqual(actions["file:alpha.py"], "apply the work")
        self.assertEqual(actions["file:beta.py"],
                         "answer the question, then ask again")
        self.assertTrue(self.rd.handoff_file().is_file())
        self.assertIn("for_agent.json", handoff["message"])

    def test_sending_twice_hands_nothing_over_twice(self):
        items = self.queue(("alpha.py", "approve", ""))
        self.rd.send_to_agent(items)
        self.assertEqual(self.rd.ready_to_send(items), [])
        self.assertEqual(self.rd.send_to_agent(items)["count"], 0)

    def test_the_decision_survives_being_sent(self):
        items = self.queue(("beta.py", "reject", "this name says nothing at all"))
        self.rd.send_to_agent(items)
        reloaded = self.rd.load_queue()
        self.assertEqual(reloaded[0]["decision"], "reject")
        self.assertEqual(reloaded[0]["note"], "this name says nothing at all")
        self.assertEqual(reloaded[0]["state"], "closed")

    def test_a_file_touched_after_a_decision_comes_back(self):
        items = self.queue(("alpha.py", "approve", ""))
        self.rd.stamp_decision(items[0])
        stamps = self.rd.load_sent()
        self.assertFalse(self.rd.changed_since_he_looked(items[0], stamps))
        self.paths["alpha.py"].write_text("# changed by the agent\n", encoding="utf-8")
        self.assertTrue(self.rd.changed_since_he_looked(items[0], stamps))

    def test_a_file_touched_after_the_handoff_comes_back(self):
        items = self.queue(("alpha.py", "approve", ""))
        self.rd.send_to_agent(items)
        sent = self.rd.load_sent()
        self.assertFalse(self.rd.changed_since_he_looked(items[0], sent))
        self.paths["alpha.py"].write_text("# changed\nvalue = 2\n",
                                          encoding="utf-8")
        self.assertTrue(self.rd.changed_since_he_looked(items[0], sent))

    def test_an_item_never_sent_is_not_treated_as_updated(self):
        items = self.queue(("alpha.py", "approve", ""))
        self.assertFalse(self.rd.changed_since_he_looked(items[0], self.rd.load_sent()))

    def test_next_steps_says_what_happens_to_each_kind(self):
        items = self.queue(("alpha.py", "approve", ""),
                           ("beta.py", "reject", "this name says nothing at all"),
                           ("gamma.py", "question", "why does this return a one?"),
                           ("delta.py", "defer", "not until the spec settles here"))
        lines = self.rd.next_steps(items)
        words = {count: what for count, what, _colour in lines}
        self.assertIn("1 approved", words)
        self.assertIn("leave your list", words["1 approved"])
        self.assertIn("revises", words["1 rejected"])
        self.assertIn("asks you again", words["1 questions"])
        self.assertIn("nobody is told", words["1 deferred"])

    def test_next_steps_mentions_what_is_still_undecided(self):
        items = self.queue(("alpha.py", "approve", ""), ("delta.py", "", ""))
        words = {count for count, _what, _colour in self.rd.next_steps(items)}
        self.assertIn("1 still undecided", words)

    def test_the_log_keeps_a_history_of_every_handoff(self):
        items = self.queue(("alpha.py", "approve", ""))
        self.rd.send_to_agent(items)
        more = self.queue(("alpha.py", "approve", ""),
                          ("beta.py", "reject", "this name says nothing at all"))
        more[0]["state"] = "closed"
        self.rd.send_to_agent(more)
        lines = (self.rd.home() / "handoff.log").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(line.split(chr(9))) == 4 for line in lines))


class UnifyImportSniffingTests(unittest.TestCase):
    """profiles.py says `from devices import classify`, and the old check looked
    for the substring "import devices" - so the module looked dependency-free and
    the airlock refused its cleanup for importing something undeclared."""

    def test_both_spellings_of_an_import_are_recognised(self):
        from crew.unify import _imports

        self.assertTrue(_imports("from devices import classify", "devices"))
        self.assertTrue(_imports("import devices", "devices"))
        self.assertTrue(_imports("    import devices  # indented", "devices"))
        self.assertTrue(_imports("from devices import (classify,\n    HEADSET)",
                                 "devices"))

    def test_a_mention_is_not_an_import(self):
        from crew.unify import _imports

        self.assertFalse(_imports("# devices are chosen elsewhere", "devices"))
        self.assertFalse(_imports("DEVICES = []", "devices"))
        self.assertFalse(_imports("import devices_extra", "devices"))
        self.assertFalse(_imports("from devices_extra import thing", "devices"))
        self.assertFalse(_imports("print('import devices')", "devices"))


class ClaudeMemberTests(unittest.TestCase):
    """Haiku joins the crew through Anthropic's own SDK, never an OpenAI shim, and
    must look to the agent loop exactly like every other member."""

    def fake_client(self, seen, text="SUBMIT a.py"):
        class Block:
            type = "text"
        block = Block()
        block.text = text

        class Usage:
            input_tokens, output_tokens = 1000, 200

        class Response:
            content = [block]
            usage = Usage()
            stop_reason = "end_turn"

        class Messages:
            def create(self, **kwargs):
                seen.update(kwargs)
                return Response()

        class Client:
            messages = Messages()
        return Client

    def test_the_reply_has_the_shape_the_agent_loop_reads(self):
        from crew import claude_chat
        seen = {}
        chat = claude_chat.claude_chat("claude-haiku-4-5", 4096,
                                       client_factory=self.fake_client(seen))
        out = chat([{"role": "system", "content": "rules"},
                    {"role": "user", "content": "go"}], 1)
        self.assertEqual(out["content"], "SUBMIT a.py")
        self.assertEqual(out["raw"]["usage"]["total_tokens"], 1200)
        self.assertEqual(seen["system"], "rules")
        self.assertEqual(seen["model"], "claude-haiku-4-5")
        self.assertNotIn("temperature", seen)

    def test_haiku_is_priced_at_anthropics_rates(self):
        from crew import claude_chat
        self.assertEqual(claude_chat.price("claude-haiku-4-5", 1_000_000, 0), 1.0)
        self.assertEqual(claude_chat.price("claude-haiku-4-5", 0, 1_000_000), 5.0)

    def test_a_transcript_always_opens_with_the_user(self):
        from crew import claude_chat
        _system, turns = claude_chat.to_anthropic(
            [{"role": "assistant", "content": "x"}, {"role": "tool", "content": "y"}])
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user"])

    def test_haiku_resolves_from_the_crew_config_not_providers(self):
        crew = Crew()
        self.assertEqual(crew._model_for("Haiku"), "claude-haiku-4-5")

    def test_without_the_sdk_the_error_names_what_is_missing(self):
        from crew import claude_chat
        from crew.config import CrewError
        try:
            import anthropic  # noqa: F401
            self.skipTest("the SDK is installed here")
        except ImportError:
            pass
        with self.assertRaises(CrewError) as caught:
            claude_chat.claude_chat("claude-haiku-4-5")(
                [{"role": "user", "content": "x"}], 1)
        self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))


class AhkTaskTypeTests(unittest.TestCase):
    """AutoHotkey tasks: refused on the host before any sandbox boots, routed by
    extension, and a grant is carried to both author and tester."""

    def test_a_dangerous_module_never_reaches_the_sandbox(self):
        from crew import task_types
        from crew.config import load_config
        spec = {"output": {"root": str(Path(tempfile.gettempdir())),
                           "files": ["kit.ahk"]},
                "api": ["Add"], "grants": []}
        cfg = load_config()
        cfg.writable = lambda p: True
        src = "Add(a, b) {\n    Run, calc.exe\n    return a + b\n}\n"
        steps = task_types.ahk_code_task_gates({"kit.ahk": src}, spec, cfg, None)
        names = [st["rung"] for st in steps]
        self.assertIn("safety", names)
        self.assertFalse(next(st for st in steps if st["rung"] == "safety")["ok"])
        self.assertNotIn("sandbox tests", names)

    def test_campaigns_route_ahk_and_carry_grants(self):
        from crew.campaign import Campaign, _language
        self.assertEqual([_language(m) for m in ("a.ahk", "b.js", "c.py")],
                         ["ahk", "js", "py"])
        spec = {"name": "unit-ahk", "senior": "none", "max_requests": 1,
                "teams": {"A": {"author": "Nemotron", "tester": "Qwen"}},
                "tasks": [{"id": "kit", "team": "A", "module": "Kit.ahk",
                           "contract": "c.md", "api": ["X"],
                           "grants": ["clipboard"]}]}
        c = Campaign(spec, quiet=True)
        self.assertEqual(c.tasks["kit-tests"]["test_file"], "test_Kit.ahk")
        self.assertEqual(c.tasks["kit-tests"]["grants"], ["clipboard"])


class PlaybookTests(CrewTestCase):
    def test_near_duplicates_refused_and_ids_increment(self):
        first = playbook.add("organize_plan", "Never move the PLAN note.", "t")
        self.assertRegex(first, r"op-\d{3}")
        self.assertIsNone(playbook.add("organize_plan", "never move the plan note", "t"))


class ClerkTaskTests(CrewTestCase):
    """scout / log_clerk / completion_audit: Crush-lite's workers, gated."""

    def setUp(self):
        super().setUp()
        self.proj = self.vault / "wiki" / "proj"
        self.proj.mkdir(parents=True)
        (self.proj / "engine.py").write_text(
            "import os\n\n\ndef announce(text):\n    return speak(text, loud=True)\n")
        (self.proj / "build.log").write_text(
            "$ make all\ncompiling a.c\na.c:3: error: expected ';' before '}'\n"
            "compiling b.c\nb.c:9: warning: unused variable 'n'\n"
            "make: *** [all] Error 2\n")

    def _status(self, c, job):
        c.tick()
        return c.result(job["task_id"])["status"]

    SCOUT = ("SUBMIT\n```scout-announce.md\n---\ntitle: S\ntags: [scout]\n---\n"
             "announce is in engine.py [src: wiki/proj/engine.py]\n\n## Findings\n"
             "- announce defined at L4-5 [src: wiki/proj/engine.py]\n"
             "  > {quote}\n\n## Unknowns\n- where speak is defined\n```")

    def _scout(self, c):
        return c.submit({"task_type": "scout", "title": "announce",
                         "instructions": "Where is announce defined?",
                         "read_roots": [str(self.vault)]}, "Claude")

    def test_scout_quotes_are_checked_word_for_word(self):
        read = '{"tool": "read_file", "args": {"path": "wiki/proj/engine.py"}}'
        good = self.SCOUT.format(quote="return speak(text, loud=True)")
        paraphrase = self.SCOUT.format(quote="return speak(text, volume=loud)")
        c = self.crew([read, paraphrase, good])
        self.assertEqual(self._status(c, self._scout(c)), "review")
        self.assertIn("verbatim", self.model.seen[-1][-1]["content"])

    def test_scout_line_numbers_must_exist(self):
        read = '{"tool": "read_file", "args": {"path": "wiki/proj/engine.py"}}'
        past_end = self.SCOUT.format(quote="return speak(text, loud=True)") \
            .replace("L4-5", "L40-45")
        c = self.crew([read, past_end, past_end])
        self._scout(c)
        c.tick()
        self.assertIn("past the end", self.model.seen[-1][-1]["content"])

    LOG = ("SUBMIT\n```log-clerk-build.md\n---\ntitle: L\ntags: [log]\n---\n"
           "The build failed. [src: log]\n\n## Exit codes\n"
           "- `make all` ended with `make: *** [all] Error 2` [src: log]\n\n"
           "## Failures\n{failures}\n```")

    def _log(self, c):
        return c.submit({"task_type": "log_clerk", "title": "build log",
                         "log_file": str(self.proj / "build.log")}, "Claude")

    def test_log_clerk_failures_verbatim_and_in_order(self):
        first = "1. compile_error: `a.c:3: error: expected ';' before '}'` [src: log]"
        second = "2. warning: `b.c:9: warning: unused variable 'n'` [src: log]"
        swapped = self.LOG.format(failures=f"{second}\n{first}")
        good = self.LOG.format(failures=f"{first}\n{second}")
        c = self.crew([swapped, good])
        self.assertEqual(self._status(c, self._log(c)), "review")
        self.assertIn("log order", self.model.seen[-1][-1]["content"])

    def test_log_clerk_invented_error_line_fails(self):
        invented = self.LOG.format(
            failures="1. compile_error: `a.c:3: error: missing semicolon here` [src: log]")
        c = self.crew([invented, invented])
        self._log(c)
        c.tick()
        self.assertIn("verbatim", self.model.seen[-1][-1]["content"])

    AUDIT = ("SUBMIT\n```completion-announce.md\n---\ntitle: A\ntags: [audit]\n---\n"
             "| Artifact | State | Path | Note |\n|---|---|---|---|\n"
             "| source change | {src} | wiki/proj/engine.py | ok [src: {cite}] |\n"
             "| test file | {test} | wiki/proj/test_engine.py | none [src: inventory] |\n\n"
             "Conclusion: {concl}\n```")

    def _audit(self, c):
        return c.submit({"task_type": "completion_audit", "title": "announce",
                         "claim": "announce() added with tests",
                         "read_roots": [str(self.vault)],
                         "expected": [{"artifact": "source change",
                                       "path": "wiki/proj/engine.py"},
                                      {"artifact": "test file",
                                       "path": "wiki/proj/test_engine.py"}]}, "Claude")

    def test_completion_audit_states_must_match_the_disk(self):
        claims_test_exists = self.AUDIT.format(src="YES", cite="inventory", test="YES",
                                               concl="EVIDENCE_COMPLETE")
        c = self.crew([claims_test_exists, claims_test_exists])
        self._audit(c)
        c.tick()
        fb = self.model.seen[-1][-1]["content"]
        self.assertIn("does not exist, so the state is NO", fb)
        self.assertIn("open", fb)      # engine.py exists but was never opened

    def test_completion_audit_passes_when_opened_and_consistent(self):
        read = '{"tool": "read_file", "args": {"path": "wiki/proj/engine.py"}}'
        good = self.AUDIT.format(src="YES", cite="wiki/proj/engine.py", test="NO",
                                 concl="EVIDENCE_INCOMPLETE")
        c = self.crew([read, good])
        self.assertEqual(self._status(c, self._audit(c)), "review")

    def test_completion_audit_conclusion_follows_states(self):
        read = '{"tool": "read_file", "args": {"path": "wiki/proj/engine.py"}}'
        wrong = self.AUDIT.format(src="YES", cite="wiki/proj/engine.py", test="NO",
                                  concl="EVIDENCE_COMPLETE")
        c = self.crew([read, wrong, wrong])
        self._audit(c)
        c.tick()
        self.assertIn("EVIDENCE_COMPLETE needs every state YES",
                      self.model.seen[-1][-1]["content"])

    def test_clerk_playbooks_exist(self):
        for t in ("scout", "log_clerk", "completion_audit"):
            self.assertGreaterEqual(len(playbook.entries(t)), 8, t)


class LspTests(CrewTestCase):
    """Language-server tools are opt-in, and a missing server never fails work."""

    def test_lsp_tools_absent_unless_enabled(self):
        from crew.tools import Evidence, Toolbox, ToolError
        tb = Toolbox(self.cfg, [self.vault], Evidence())
        with self.assertRaises(ToolError):
            tb.call("symbols", {"path": "wiki/lab/PLAN.md"})

    def test_lsp_gate_skips_when_server_cannot_start(self):
        from crew import gates
        cfg = {"python": {"command": [str(self.tmp / "no-such-server.exe")],
                          "extensions": [".py"], "start_timeout_s": 5}}
        st = gates.lsp_clean(cfg, "python", {"m.py": "x = y\n"}, "m.py", "m.py")
        self.assertTrue(st["ok"])
        self.assertIn("lsp skipped", st["note"])

    def test_lsp_gate_fails_only_on_errors(self):
        from crew import gates
        ruff = shutil.which("ruff")
        if not ruff:
            self.skipTest("ruff not installed")
        cfg = {"python": {"command": [ruff, "server"], "extensions": [".py"],
                          "diagnostics_command": [ruff, "server"],
                          "diagnostics_settings": {"settings": {
                              "configurationPreference": "editorOnly",
                              "lint": {"select": ["E9", "F"]}}}}}
        bad = gates.lsp_clean(cfg, "python", {"m.py": "def f():\n    return g()\n"},
                              "m.py", "m.py")
        self.assertFalse(bad["ok"])
        self.assertIn("F821", bad["detail"])
        warn_only = gates.lsp_clean(cfg, "python",
                                    {"m.py": "import os\n\n\ndef f():\n    return 1\n"},
                                    "m.py", "m.py")
        self.assertTrue(warn_only["ok"])


class PersonnelTests(CrewTestCase):
    """The building: posts, fitted budgets, quirk profiles, context trimming."""

    STAFF = {"context_policy": {"context_ceiling": 0.5, "context_ceiling_max": 0.75,
                                "practical_cap_tokens": 200000},
             "task_baselines": {"scout": 18},
             "posts": {"scout": ["Kimi", "Gordon"]},
             "members": {"Gordon": {"context_window": 1000000,
                                    "quirks": {"addenda": ["Never repeat a search."],
                                               "leash": {"max_repeats": 2}}},
                         "Hoss": {"context_window": 131072}}}

    def test_post_resolves_to_first_holder_not_denied(self):
        from crew import personnel
        self.assertEqual(personnel.resolve("@scout", self.STAFF, ["Kimi"]), "Gordon")
        self.assertEqual(personnel.resolve("Hoss", self.STAFF), "Hoss")
        with self.assertRaises(CrewError):
            personnel.resolve("@nobody", self.STAFF)

    def test_budget_follows_passing_history_then_baseline(self):
        from crew import personnel
        hist = {("Hoss", "scout"): [{"passed": True, "requests": n, "tokens": 20000}
                                    for n in (2, 3, 4, 9)]}
        b = personnel.budget_for(self.STAFF, "Hoss", "scout", hist)
        self.assertEqual(b["max_requests"], 4 + personnel.HEADROOM)   # p75 of 2,3,4,9
        self.assertEqual(b["context_tokens"], 65536)                  # half of 131072
        self.assertEqual(b["max_tokens"], 60000)      # 2 x p90 (40k) is under the floor
        g = personnel.budget_for(self.STAFF, "Gordon", "scout", hist)
        self.assertEqual(g["max_requests"], 18)                       # baseline, no history
        self.assertEqual(g["context_tokens"], 100000)                 # capped window
        capped = personnel.budget_for(self.STAFF, "Gordon", "scout", hist,
                                      {"context_ceiling": 0.9, "extra_requests": 4})
        self.assertEqual(capped["context_tokens"], 150000)            # max 0.75
        self.assertEqual(capped["max_requests"], 22)

    def test_house_notes_and_leash(self):
        from crew import personnel
        self.assertIn("Never repeat a search.", personnel.system_addenda(self.STAFF, "Gordon"))
        self.assertEqual(personnel.system_addenda(self.STAFF, "Hoss"), "")
        self.assertEqual(personnel.leash(self.STAFF, "Gordon"), {"max_repeats": 2})

    def test_context_trimming_keeps_what_fits(self):
        from crew.agent import _trim_old_results
        def msgs():
            return [{"role": "user", "content": "x" * 5000, "_result": True} for _ in range(8)]
        flat = msgs()
        _trim_old_results(flat)
        self.assertEqual(sum(1 for m in flat if m.get("_trimmed")), 5)   # old rule: keep 3
        roomy = msgs()
        _trim_old_results(roomy, context_tokens=100000)                   # 350k chars fit
        self.assertFalse(any(m.get("_trimmed") for m in roomy))
        tight = msgs()
        _trim_old_results(tight, context_tokens=4000)                     # 14k chars
        self.assertEqual(sum(1 for m in tight if not m.get("_trimmed")), 3)

    def test_submit_fits_budget_and_resolves_post(self):
        self.cfg.data.setdefault("defaults", {})["budget_from_personnel"] = True
        self.cfg.defaults["budget_from_personnel"] = True
        c = self.crew([])
        job = c.submit({"task_type": "log_clerk", "title": "l", "assigned_to": "@clerk",
                        "log_file": str(self.lab / "PLAN.md")}, "Claude")
        j = c.store.load(job["task_id"])
        self.assertEqual(j["assigned_to"], "Larry")
        self.assertIn("context_tokens", j["budget"])
        self.assertIn("source", j["budget"])


class InspectorTests(CrewTestCase):
    """The recursive pass: signatures -> bounded trials or PA proposals."""

    def _job(self, jid, passed, stop, requests, max_requests=12, trial=None):
        return {"task_id": jid, "assigned_to": "Gordon", "task_type": "scout",
                "budget": {"max_requests": max_requests, "max_tokens": 100000,
                           **({"trial": trial} if trial else {})},
                "result": {"passed": passed, "stop_reason": stop, "requests": requests}}

    def _inspect(self, job, transcript=()):
        from crew import inspector
        p = self.tmp / f"{job['task_id']}.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in transcript), encoding="utf-8")
        return inspector.inspect_job(self.cfg, job, p)

    def test_budget_exhaustion_starts_one_bounded_trial(self):
        from crew import inspector
        rec = self._inspect(self._job("j1", False, "budget_requests", 12))
        self.assertEqual(len(rec["trials_started"]), 1)
        rec2 = self._inspect(self._job("j2", False, "budget_requests", 12))
        self.assertEqual(rec2["trials_started"], [])        # one change at a time
        t = inspector.active_trial(self.cfg, "Gordon", "scout")
        self.assertEqual(t["overrides"], {"extra_requests": 4})

    def test_trial_is_kept_or_reverted_by_measurement(self):
        from crew import inspector
        self._inspect(self._job("j1", False, "budget_requests", 12))
        tid = inspector.active_trial(self.cfg, "Gordon", "scout")["id"]
        for i in range(inspector.TRIAL_WINDOW):
            self._inspect(self._job(f"t{i}", True, "passed", 9, 16, trial=tid))
        trial = next(t for t in inspector._load_trials(self.cfg) if t["id"] == tid)
        self.assertEqual(trial["status"], "kept")
        self.assertEqual(inspector.active_trial(self.cfg, "Gordon", "scout")["overrides"],
                         {"extra_requests": 4})             # kept trials stay applied

    def test_stuck_gate_is_a_proposal_never_an_edit(self):
        bad = {"rung": "citations", "ok": False, "detail": "x"}
        tr = [{"event": "submission", "steps": [bad]}, {"event": "submission", "steps": [bad]}]
        rec = self._inspect(self._job("j1", False, "no_change", 5), tr)
        self.assertIn("gate_stuck", [s["signature"] for s in rec["signatures"]])
        props = (self.cfg.state_home / "inspector" / "proposals.jsonl").read_text()
        self.assertIn("gate_suspect", props)


class SpecialTeamsTests(CrewTestCase):
    """Kimi's harness: nothing runs unchecked, and claims must match what tools returned."""

    class FakeMcp:
        def __init__(self):
            self.calls = []

        def tools(self):
            return [{"name": n, "inputSchema": {"type": "object",
                                                "properties": {"url": {"type": "string"},
                                                               "target": {"type": "string"},
                                                               "element": {"type": "string"},
                                                               "function": {"type": "string"},
                                                               "filename": {"type": "string"}}}}
                    for n in ("browser_navigate", "browser_click", "browser_run_code_unsafe",
                              "browser_evaluate", "browser_take_screenshot", "browser_snapshot")]

        def call(self, name, args):
            self.calls.append(name)
            return {"ok": True, "text": "page says 1 OK and 1 / 26", "images": 0}

    def test_guard_refuses_and_grades_quotes(self):
        import crew.special_teams as st
        st.WORKSPACE = REPO_ROOT / "crew" / "hidden_tests" / "reference"
        mcp = self.FakeMcp()

        def tc(i, name, args):
            return {"id": f"c{i}", "function": {"name": name, "arguments": json.dumps(args)}}
        script = [[tc(1, "browser_navigate", {"url": "http://127.0.0.1:1/x"}),
                   tc(2, "browser_run_code_unsafe", {"code": "1"}),
                   tc(3, "browser_navigate", {"url": "https://evil.example/"})],
                  [tc(4, "browser_click", {"element": "OK", "target": "e1"})],
                  "Counters: `page says 1 OK and 1 / 26`; also `a quote nobody returned`"]

        def chat(messages, tools):
            names = {t["function"]["name"] for t in tools}
            assert "browser_run_code_unsafe" not in names and "browser_evaluate" not in names
            step = script.pop(0)
            msg = {"content": step} if isinstance(step, str) else {"content": "", "tool_calls": step}
            return {"content": msg["content"], "raw": {"usage": {"total_tokens": 5},
                                                        "choices": [{"message": msg}]}}
        mission = {"name": "unit", "goal": "g", "url_prefixes": ["http://127.0.0.1:1/"],
                   "allowed_tools": ["browser_navigate", "browser_click", "browser_snapshot"],
                   "acting_tools": ["browser_click"], "max_steps": 6, "max_actions": 1,
                   "expect_observed": ["1 OK"]}
        r = st.run_mission(mission, chat=chat, mcp=mcp, out_dir=self.tmp / "st")
        self.assertEqual(mcp.calls.count("browser_run_code_unsafe"), 0)
        self.assertNotIn("https://evil.example/", json.dumps(r))
        # run_code is stopped by the schema check (never offered); the evil URL
        # passes the schema and is refused by the mission guard
        self.assertEqual(r["guard"]["refused"], 1)
        self.assertIn("browser_evaluate", mcp.calls)     # the orange highlight ran before the click
        self.assertLess(mcp.calls.index("browser_evaluate"), mcp.calls.index("browser_click"))
        quotes = next(c for c in r["checks"] if c["check"] == "quotes seen")
        self.assertFalse(quotes["ok"])
        self.assertIn("a quote nobody returned", quotes["detail"])
        self.assertTrue(next(c for c in r["checks"] if c["check"] == "expected observations")["ok"])
        steps = (self.tmp / "st" / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("refused", steps)


class McpSurfaceTests(unittest.TestCase):
    def test_tools_registered_and_no_promotion_tool(self):
        from crew import server
        names = {t.name for t in asyncio.run(server.mcp.list_tools())}
        self.assertEqual(names, {"crew_task_types", "crew_submit", "crew_status",
                                 "crew_result", "crew_review", "crew_inbox",
                                 "crew_roster", "crew_playbook", "crew_budget"})


if __name__ == "__main__":
    unittest.main()
