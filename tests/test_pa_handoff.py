"""crew/runners/pa_handoff.py and pa_brief.continuation(): a chat handed to another PA gets a
summary and a continuing-PA prompt, not the whole conversation (Kris 2026-10-25)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import pa_brief  # noqa: E402
from crew.runners import pa_handoff  # noqa: E402

STAFF = {"pa": {"approved": ["Claude", "Gordon"], "scopes": {
    "Gordon": {"runtime": "opencode", "model": "hf:deepseek-ai/DeepSeek-V4.1-Flash", "notes": "Researcher first."}}}}

CONVERSATION = """### You (plan)
We are building TheCrew. Have the crew study 15 repos and rank features.

### Gordon (plan)
plan.md is written; 18 jobs planned.

### You (assign)
Approved. Submit them.

### Gordon (assign)
Submitted t1-t15: job-1, job-2.
"""

SUMMARY = "# Handoff - study\n" + "\n".join(f"## {s}\n- fact {i}" for i, s in enumerate(pa_handoff.SECTIONS)) + "\n" + "x" * 200


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.artifacts = self.tmp / "chats" / "ses_1"
        self.folder = self.artifacts / "handoff"
        self.folder.mkdir(parents=True)
        (self.artifacts / "plan.md").write_text("# Goal\nRank the features.\n", encoding="utf-8")
        (self.artifacts / "tasks.json").write_text(json.dumps({"milestone": "study", "jobs": [
            {"id": "t1", "title": "Digest A", "assigned_to": "Gordon", "status": "ready", "job_id": "job-1"},
            {"id": "t16", "title": "Synthesis", "assigned_to": "Qwen", "status": "blocked", "job_id": ""}]}),
            encoding="utf-8")
        self.state = self.tmp / "state"
        (self.state / "jobs" / "job-1").mkdir(parents=True)
        (self.state / "jobs" / "job-1" / "job.json").write_text(json.dumps({"status": "review"}), encoding="utf-8")
        (self.folder / "conversation-1.md").write_text(CONVERSATION, encoding="utf-8")
        (self.folder / "request-1.txt").write_text("Review the 14 digests.", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_new_pa_is_told_it_continues_then_gets_the_summary_then_the_request(self):
        text = pa_brief.continuation("Gordon", "Claude", "THE SUMMARY", "C:/a/summary-1.md", "THE REQUEST", staff=STAFF)
        self.assertTrue(text.startswith("## Continuing as PA - handoff from Claude"))
        self.assertIn("You are Gordon (hf:deepseek-ai/DeepSeek-V4.1-Flash)", text)
        self.assertIn("C:/a/summary-1.md", text)
        self.assertIn("About you: Researcher first.", text)
        self.assertLess(text.index("THE SUMMARY"), text.index("THE REQUEST"))
        self.assertLess(text.index("### Handoff summary"), text.index("### The PM's request"))

    def test_a_handoff_writes_the_summary_and_the_prompt(self):
        seen = {}

        def fake(messages):
            seen["user"] = messages[-1]["content"]
            return {"content": SUMMARY, "model": "fake-model", "tokens": {"prompt": 10}}
        out = pa_handoff.handoff(self.folder, 1, "Claude", "Gordon", "study", "Gordon", self.state, chat=fake)
        self.assertTrue(out["ok"])
        self.assertFalse(out["fallback"])
        self.assertEqual(out["model"], "Gordon (fake-model)")
        self.assertIn("Review the 14 digests.", out["prompt"])
        self.assertIn("## The goal", out["prompt"])
        self.assertTrue((self.folder / "summary-1.md").read_text(encoding="utf-8").startswith("<!-- handoff Claude -> Gordon"))
        self.assertEqual((self.folder / "prompt-1.md").read_text(encoding="utf-8").strip(), out["prompt"].strip())
        # the summarizer saw the conversation and the live job status, not just the plan
        self.assertIn("Approved. Submit them.", seen["user"])
        self.assertIn("| t1 | Digest A | Gordon | ready | job-1 | review |", seen["user"])
        self.assertNotIn("conversation-1.md", seen["user"], "the handoff folder is not listed as an artifact")

    def test_without_the_summarizer_the_summary_is_built_from_the_pms_words_and_the_artifacts(self):
        def broken(messages):
            raise ConnectionError("Synthetic is down")
        out = pa_handoff.handoff(self.folder, 1, "Claude", "Gordon", "study", "Gordon", self.state, chat=broken)
        self.assertTrue(out["ok"])
        self.assertTrue(out["fallback"])
        self.assertIn("Synthetic is down", out["error"])
        summary = (self.folder / "summary-1.md").read_text(encoding="utf-8")
        self.assertIn("Written without a model", summary)
        self.assertIn("We are building TheCrew", summary)
        self.assertIn("Submitted t1-t15", summary)
        self.assertIn("| t1 | Digest A |", summary)

    def test_a_reply_that_is_not_a_summary_is_not_passed_on(self):
        out = pa_handoff.handoff(self.folder, 1, "Claude", "Gordon", "study", "Gordon", self.state,
                                 chat=lambda m: {"content": "OK", "model": "m"})
        self.assertTrue(out["fallback"])
        self.assertIn("too short", out["error"])

    def test_a_long_chat_keeps_its_start_and_its_end(self):
        text = "GOAL " + "a" * 300_000 + " LATEST"
        cut = pa_handoff.cut_middle(text)
        self.assertTrue(cut.startswith("GOAL"))
        self.assertTrue(cut.endswith("LATEST"))
        self.assertIn("characters of the middle cut", cut)
        self.assertEqual(pa_handoff.cut_middle("short"), "short")


if __name__ == "__main__":
    unittest.main()
