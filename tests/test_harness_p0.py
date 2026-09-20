"""P0 harness hygiene: best-attempt grading, loop guards, transactional parts,
Librarian grounding gate, sandbox config + probe injection.

Run: python -m pytest tests/test_harness_p0.py -q
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "experiments"))
sys.path.insert(0, str(REPO_ROOT / "v3-service"))

import attempts  # noqa: E402

OK = {"rung": "x", "file": "a.gd", "ok": True}
BAD = {"rung": "x", "file": "a.gd", "ok": False}


class AttemptTrackerTests(unittest.TestCase):
    def test_regression_never_replaces_best(self):
        t = attempts.AttemptTracker(no_progress_limit=5)
        self.assertTrue(t.add(0, {"a": "1"}, [OK, OK, BAD], False))
        self.assertTrue(t.add(1, {"a": "2"}, [OK, BAD, BAD], False))
        self.assertEqual(t.best["attempt"], 0)

    def test_pass_stops_and_is_best(self):
        t = attempts.AttemptTracker()
        t.add(0, {"a": "1"}, [BAD], False)
        self.assertFalse(t.add(1, {"a": "2"}, [OK], True))
        self.assertEqual((t.best["attempt"], t.stop_reason), (1, "passed"))

    def test_identical_output_stops(self):
        t = attempts.AttemptTracker()
        t.add(0, {"a": "same"}, [BAD], False)
        self.assertFalse(t.add(1, {"a": "same"}, [BAD], False))
        self.assertEqual(t.stop_reason, "no_change")

    def test_no_progress_stops(self):
        t = attempts.AttemptTracker(no_progress_limit=2)
        t.add(0, {"a": "0"}, [OK, BAD], False)
        self.assertTrue(t.add(1, {"a": "1"}, [OK, BAD], False))
        self.assertFalse(t.add(2, {"a": "2"}, [BAD, BAD], False))
        self.assertEqual(t.stop_reason, "no_progress")

    def test_merge_carry_and_failing_files(self):
        self.assertEqual(attempts.merge_carry({"a": "1", "b": "1"},
                                              {"a": "2"}),
                         {"a": "2", "b": "1"})
        self.assertEqual(attempts.failing_files(
            [OK, {"rung": "c", "file": "b.gd", "ok": False},
             {"rung": "c", "ok": False}]), ["b.gd"])


def _fake_reply(files):
    return {"content": "\n".join(f"```{k}\n{v}\n```" for k, v in
                                 files.items()),
            "raw": {"usage": {"total_tokens": 100}}, "time_ms": 1}


class TransactionalPartTests(unittest.TestCase):
    """A failing attempt must never touch the live project; a partial repair
    is merged over the best attempt instead of replacing it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / "project"
        self.work.mkdir()
        (self.work / "keep.gd").write_text("extends Node\n")
        prompts = self.tmp / "prompts"
        prompts.mkdir()
        (prompts / "p1.md").write_text("emit a.gd and b.gd")
        self.spec = self.tmp / "spec.json"
        self.spec.write_text(json.dumps({"parts": [{
            "id": "p1", "required": ["a.gd", "b.gd"],
            "must_contain": {"a.gd": ["GOOD"]}}]}))
        self.prompts = prompts
        import space_duty
        self.sd = space_duty
        self.patches = [
            mock.patch.object(space_duty.verify_mod, "check_only_script",
                              return_value=(True, "ok")),
            mock.patch.object(space_duty.verify_mod, "run_in_windows_sandbox",
                              return_value=(True, "TUTORIAL_READY")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, replies, repair):
        with mock.patch.object(self.sd, "chat_completion",
                               side_effect=replies):
            return self.sd.run("Hoss", "", repair, 10**9, 3600,
                               self.tmp / "out", spec_path=self.spec,
                               prompts_dir=self.prompts, work=self.work,
                               skip_scaffold=True)

    def test_failed_part_leaves_live_project_untouched(self):
        bad = _fake_reply({"a.gd": "extends Node # nope",
                           "b.gd": "extends Node"})
        bad2 = _fake_reply({"a.gd": "extends Node # still nope",
                            "b.gd": "extends Node"})
        summary = self._run([bad, bad2], repair=1)
        self.assertFalse(summary["parts"][0]["passed"])
        self.assertEqual(sorted(p.name for p in self.work.iterdir()),
                         ["keep.gd"])

    def test_partial_repair_carries_forward_and_commits(self):
        first = _fake_reply({"a.gd": "extends Node # nope",
                             "b.gd": "extends Node # b v1"})
        repair_only_a = _fake_reply({"a.gd": "extends Node # GOOD"})
        summary = self._run([first, repair_only_a], repair=1)
        part = summary["parts"][0]
        self.assertTrue(part["passed"])
        self.assertEqual(part["best_attempt"], 1)
        self.assertIn("GOOD", (self.work / "a.gd").read_text())
        self.assertIn("b v1", (self.work / "b.gd").read_text())


class GroundingGateTests(unittest.TestCase):
    def setUp(self):
        import librarian_duty
        self.L = librarian_duty
        self.root = Path(tempfile.mkdtemp())
        (self.root / "runs").mkdir()
        (self.root / "runs" / "RUN-a.md").write_text(
            "Battery: 9/12 passed. Cost $0.0091. Verdict: PASS")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_grounded_line_passes(self):
        text = "- [[runs/RUN-a]] 9/12 passed, $0.0091, PASS"
        self.assertEqual(self.L.grounding_violations(text, self.root), [])

    def test_miscalibrated_numbers_and_verdict_flagged(self):
        text = "- [[runs/RUN-a]] 11/12 passed, FAIL"
        bad = self.L.grounding_violations(text, self.root)
        self.assertEqual(len(bad), 2)
        self.assertTrue(any("11/12" in b for b in bad))
        self.assertTrue(any("FAIL" in b for b in bad))


class SandboxConfigTests(unittest.TestCase):
    def setUp(self):
        import verify
        self.v = verify
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wsb_maps_only_this_run_plus_readonly_tools(self):
        run_dir = self.tmp / "share" / "run-123"
        xml = self.v.build_wsb_config(run_dir, Path(r"C:\Godot"))
        self.assertIn(f"<HostFolder>{run_dir}</HostFolder>", xml)
        self.assertNotIn(f"<HostFolder>{run_dir.parent}</HostFolder>", xml)
        self.assertIn(f"<HostFolder>{self.v.SANDBOX_TOOLS}</HostFolder>", xml)
        tools_block = xml.split(str(self.v.SANDBOX_TOOLS))[1][:80]
        self.assertIn("<ReadOnly>true</ReadOnly>", tools_block)
        for off in ("AudioInput", "VideoInput", "ClipboardRedirection",
                    "PrinterRedirection", "Networking", "VGpu"):
            self.assertIn(f"<{off}>Disable</{off}>", xml)
        self.assertIn(r"Desktop\sandbox\runner.ps1", xml)
        self.assertIn(r'-JobDir "C:\Users\WDAGUtilityAccount\Desktop\run-123"',
                      xml)

    def test_probe_injected_with_nonce_new_autoload_section(self):
        (self.tmp / "project.godot").write_text(
            'config_version=5\n[application]\nrun/main_scene="res://m.tscn"\n')
        self.v.inject_probe(self.tmp, "abc123")
        cfg = (self.tmp / "project.godot").read_text()
        self.assertIn('[autoload]\n\nHarnessProbe="*res://harness_probe.gd"',
                      cfg)
        probe = (self.tmp / "harness_probe.gd").read_text()
        self.assertIn('const NONCE := "abc123"', probe)

    def test_probe_joins_existing_autoload_section(self):
        (self.tmp / "project.godot").write_text(
            '[autoload]\n\nGame="*res://game.gd"\n')
        self.v.inject_probe(self.tmp, "n1")
        cfg = (self.tmp / "project.godot").read_text()
        self.assertEqual(cfg.count("[autoload]"), 1)
        self.assertIn('Game="*res://game.gd"', cfg)
        self.assertIn("HarnessProbe=", cfg)

    def test_probe_status_requires_this_runs_nonce(self):
        log = "HARNESS_PROBE other SCENE_LOADED scene=x\nHARNESS_PROBE n1 BOOT"
        self.assertEqual(self.v.probe_status(log, "n1"), "boot_only")
        self.assertEqual(self.v.probe_status(
            log + "\nHARNESS_PROBE n1 SCENE_LOADED scene=x", "n1"),
            "scene_loaded")


if __name__ == "__main__":
    unittest.main()
