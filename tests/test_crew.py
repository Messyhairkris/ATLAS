"""The Crew: lifecycle, gates, leash, roster rules, and MCP surface.
A scripted fake model drives every run, so no provider requests are made.

Run: python -m pytest tests/test_crew.py -q
"""

import asyncio
import json
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


class BucketBudgetTests(CrewTestCase):
    """Kris's allowance refills 5% of capacity every 3 hours, so the crew
    models it as a bucket rather than a rolling window."""

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


class PlaybookTests(CrewTestCase):
    def test_near_duplicates_refused_and_ids_increment(self):
        first = playbook.add("organize_plan", "Never move the PLAN note.", "t")
        self.assertRegex(first, r"op-\d{3}")
        self.assertIsNone(playbook.add("organize_plan", "never move the plan note", "t"))


class McpSurfaceTests(unittest.TestCase):
    def test_tools_registered_and_no_promotion_tool(self):
        from crew import server
        names = {t.name for t in asyncio.run(server.mcp.list_tools())}
        self.assertEqual(names, {"crew_task_types", "crew_submit", "crew_status",
                                 "crew_result", "crew_review", "crew_inbox",
                                 "crew_roster", "crew_playbook", "crew_budget"})


if __name__ == "__main__":
    unittest.main()
