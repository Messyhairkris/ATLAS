"""close_campaign.py: a dead campaign is closed, never deleted, and a live one is left alone."""

import datetime as dt
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew.runners import close_campaign  # noqa: E402


class CloseCampaignTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.folder = self.home / "pt-old"
        self.folder.mkdir()
        self.status = self.folder / "status.json"
        self.status.write_text(json.dumps({
            "campaign": "pt-old", "goal": "g", "updated": "2026-10-20T14:22:09",
            "requests_used": 3,
            "tasks": {
                "a": {"state": "accepted", "kind": "module", "member": "Hoss", "attempts": 1,
                      "tokens": 100},
                "b": {"state": "running", "kind": "module", "member": "Larry", "attempts": 0,
                      "eta": {"likely_minutes": 2}},
                "b-tests": {"state": "waiting", "kind": "tests", "member": "Hoss",
                            "attempts": 0},
            },
            "counts": {"accepted": 1, "running": 1, "waiting": 1, "escalated": 0, "failed": 0},
            "events": [],
        }), encoding="utf-8")
        (self.folder / "progress.log").write_text("[2026-10-20T14:22:09] started\n",
                                                  encoding="utf-8")
        self.old = time.time() - 3 * 86400
        os.utime(self.status, (self.old, self.old))

    def close(self, **kw):
        args = dict(reason="provider stalled; Kimi took it", superseded_by="pt-kimi-5",
                    apply=True, now=dt.datetime(2026, 10, 24, 9, 0, 0))
        args.update(kw)
        return close_campaign.close(self.home, "pt-old", **args)

    def test_dry_run_writes_nothing(self):
        before = self.status.read_text(encoding="utf-8")
        result = self.close(apply=False)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["changes"]), 2)
        self.assertEqual(self.status.read_text(encoding="utf-8"), before)
        self.assertFalse((self.folder / "summary.json").exists())

    def test_apply_closes_open_tasks_and_keeps_the_rest(self):
        self.close()
        status = json.loads(self.status.read_text(encoding="utf-8"))
        states = {k: t["state"] for k, t in status["tasks"].items()}
        self.assertEqual(states, {"a": "accepted", "b": "stopped", "b-tests": "stopped"})
        self.assertNotIn("eta", status["tasks"]["b"])
        self.assertEqual(status["counts"], {"accepted": 1, "running": 0, "waiting": 0,
                                            "escalated": 0, "failed": 0, "stopped": 2})
        self.assertEqual(status["updated"], "2026-10-20T14:22:09")
        event = status["events"][-1]
        self.assertEqual((event["event"], event["superseded_by"], event["by"]),
                         ("campaign_stopped", "pt-kimi-5", "PA (Claude)"))

    def test_apply_writes_summary_report_and_log(self):
        self.close()
        summary = json.loads((self.folder / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual((summary["outcome"], summary["accepted"], summary["not_started"],
                          summary["first_try_accepts"], summary["tokens"]),
                         ("stopped", 1, 2, 1, 100))
        self.assertIn("Outcome: stopped", (self.folder / "REPORT.md").read_text(encoding="utf-8"))
        log = (self.folder / "progress.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(log[0], "[2026-10-20T14:22:09] started")
        self.assertIn("superseded by pt-kimi-5", log[-1])

    def test_last_activity_time_is_kept(self):
        self.close()
        self.assertAlmostEqual(self.status.stat().st_mtime, self.old, delta=1)

    def test_refuses_a_finished_campaign(self):
        self.close()
        again = self.close()
        self.assertFalse(again["ok"])
        self.assertIn("already has a summary", again["problem"])

    def test_refuses_a_recent_one_unless_forced(self):
        os.utime(self.status, None)
        result = self.close()
        self.assertFalse(result["ok"])
        self.assertIn("may still be running", result["problem"])
        self.assertTrue(self.close(force=True)["ok"])

    def test_needs_a_reason(self):
        self.assertFalse(self.close(reason="  ")["ok"])


if __name__ == "__main__":
    unittest.main()
