"""PA roster, Kris-only promotion, and the PA brief (Kris, 2026-10-23).

Run: python -m pytest tests/test_pa.py -q
"""

import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import pa, pa_brief  # noqa: E402
from crew.config import CrewError  # noqa: E402


class PaRosterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "personnel.json"
        shutil.copy(REPO / "crew" / "personnel.json", self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_the_four_approved_pas(self):
        self.assertEqual(pa.approved(self.path), ["Claude", "Kimi", "Qwen", "Gordon"])
        self.assertEqual(pa.listing(self.path)["default"], "Claude")

    def test_promote_needs_kris(self):
        with self.assertRaises(CrewError):
            pa.promote("Larry", "Claude", path=self.path, interactive=True, ask=lambda _: "Larry")

    def test_promote_refuses_a_non_interactive_shell(self):
        """A PA's shell has no console: it cannot promote anyone, even with --by Kris."""
        with self.assertRaises(CrewError) as e:
            pa.promote("Larry", "Kris", path=self.path, interactive=False)
        self.assertIn("real console", str(e.exception))
        self.assertNotIn("Larry", pa.approved(self.path))

    def test_promote_needs_the_name_typed_back(self):
        with self.assertRaises(CrewError):
            pa.promote("Larry", "Kris", path=self.path, interactive=True, ask=lambda _: "y")
        self.assertNotIn("Larry", pa.approved(self.path))

    def test_promote_adds_member_and_a_minimal_scope(self):
        out = pa.promote("Larry", "Kris", path=self.path, interactive=True,
                         ask=lambda _: "Larry", today="2026-10-23")
        self.assertEqual(out["approved"][-1], "Larry")
        data = self.data()
        self.assertIn("Larry", data["pa"]["approved"])
        scope = data["pa"]["scopes"]["Larry"]
        self.assertEqual(scope["runtime"], "opencode")
        self.assertEqual(scope["model"], data["members"]["Larry"]["model"])
        self.assertIn("2026-10-23", scope["notes"])
        # the rest of the file is untouched
        self.assertEqual(data["posts"]["clerk"], ["Larry", "Hoss"])

    def test_promote_refuses_strangers_and_repeats(self):
        for name in ("Nobody", "Gordon"):
            with self.assertRaises(CrewError):
                pa.promote(name, "Kris", path=self.path, interactive=True, ask=lambda _: name)

    def test_demote_keeps_the_scope_and_moves_the_default(self):
        pa.demote("Claude", "Kris", path=self.path, interactive=True, ask=lambda _: "Claude")
        data = self.data()
        self.assertEqual(data["pa"]["approved"], ["Kimi", "Qwen", "Gordon"])
        self.assertEqual(data["pa"]["default"], "Kimi")
        self.assertIn("Claude", data["pa"]["scopes"])

    def test_demote_refuses_the_last_pa(self):
        for name in ("Claude", "Kimi", "Qwen"):
            pa.demote(name, "Kris", path=self.path, interactive=True, ask=lambda _, n=name: n)
        with self.assertRaises(CrewError):
            pa.demote("Gordon", "Kris", path=self.path, interactive=True, ask=lambda _: "Gordon")


class PaBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        (self.state / "campaigns" / "demo").mkdir(parents=True)
        (self.state / "campaigns" / "demo" / "status.json").write_text(json.dumps({
            "campaign": "demo", "counts": {"accepted": 1, "failed": 0, "waiting": 1},
            "tasks": {"t1": {"state": "running", "member": "Hoss"}}}), encoding="utf-8")
        (self.state / "night").mkdir()
        (self.state / "night" / "night-2026-10-23.json").write_text(json.dumps({
            "generated": "2026-10-23T03:00:01", "headline": "2 failed job(s) in 1 group(s)",
            "groups": [{"signature": "code_task|frontmatter|x", "count": 3,
                        "candidate": True}]}), encoding="utf-8")
        self.staff = json.loads((REPO / "crew" / "personnel.json").read_text(encoding="utf-8"))
        self.now = dt.datetime(2026, 10, 23, 9, 0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def render(self, who, **kw):
        return pa_brief.render(who, staff=self.staff, state=self.state, now=self.now, **kw)

    def test_unapproved_pa_is_refused(self):
        with self.assertRaises(ValueError) as e:
            self.render("Larry")
        self.assertIn("python -m crew pa promote Larry --by Kris", str(e.exception))

    def test_brief_names_the_pa_scope_and_live_state(self):
        text = self.render("Gordon")
        self.assertIn("You are Gordon, the Project Assistant (PA). Kris is the Project Manager",
                      text)
        self.assertIn("Runtime: opencode", text)
        self.assertIn("You may NOT: push or upload anywhere", text)
        self.assertIn("campaign demo: 1 accepted, 0 failed, 1 waiting; running t1: Hoss", text)
        self.assertIn("fixer candidate: code_task|frontmatter|x (3x)", text)
        self.assertIn("Other approved PAs: Claude, Kimi, Qwen", text)

    def test_non_claude_pa_gets_the_standing_rules_claude_does_not(self):
        rule = "PowerShell is the default shell"
        self.assertIn(rule, self.render("Kimi"))
        claude = self.render("Claude")
        self.assertNotIn(rule, claude)
        self.assertIn("CLAUDE.md and project memory carry the standing rules", claude)

    def test_brief_stays_under_the_cap(self):
        self.staff["pa"]["brief_max_chars"] = 3000
        text = self.render("Qwen")
        self.assertLessEqual(len(text), 3000)
        self.assertIn("You are Qwen", text)

    def test_default_cap_holds_with_real_state(self):
        text = pa_brief.render("Kimi", staff=self.staff, now=self.now)
        self.assertLessEqual(len(text), self.staff["pa"]["brief_max_chars"])

    def test_session_task_is_layer_three(self):
        self.assertIn("## This session's task\nBuild the guard.",
                      self.render("Gordon", task="Build the guard."))

    def test_hook_json_is_sessionstart_additional_context(self):
        out = json.loads(pa_brief.hook_json("hello"))
        self.assertEqual(out, {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                      "additionalContext": "hello"}})

    def test_first_sentence_keeps_lines_informative(self):
        short = pa_brief._first_sentence("vision 3/3. research 12/32 with 4 loop_repeat stops.",
                                         110)
        self.assertEqual(short, "vision 3/3. research 12/32 with 4 loop_repeat stops.")
        long = pa_brief._first_sentence("a" * 200, 50)
        self.assertEqual(len(long), 50)
        self.assertTrue(long.endswith("..."))


if __name__ == "__main__":
    unittest.main()
