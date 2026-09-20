import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "experiments"))

import senior_review as sr  # noqa: E402

GOOD = (
    "ROOT CAUSE: Junior used Godot 3 input API (Key.D) which does not exist "
    "in 4.6.\n"
    "FIX 1: Replace Key.D with KEY_D.\n"
    "FIX 2: Replace new_from_scancode with InputEventKey.new.\n"
    "FIX 3: Use the 2-arg intersect_ray via PhysicsDirectSpaceState3D.\n"
    "CONSTRAINT: Never emit Godot 3 APIs; if unsure, prefer the simplest "
    "4.6 call.\n"
)


class ParseDirectivesTests(unittest.TestCase):
    def test_wellformed(self):
        d = sr.parse_directives(GOOD)
        self.assertTrue(d["raw_ok"])
        self.assertIn("Godot 3 input API", d["root_cause"])
        self.assertEqual(len(d["fixes"]), 3)
        self.assertEqual(d["fixes"][0], "Replace Key.D with KEY_D.")
        self.assertIn("Never emit Godot 3 APIs", d["constraint"])

    def test_optional_third_fix(self):
        text = GOOD.replace(
            "FIX 3: Use the 2-arg intersect_ray via "
            "PhysicsDirectSpaceState3D.\n", "")
        d = sr.parse_directives(text)
        self.assertTrue(d["raw_ok"])
        self.assertEqual(len(d["fixes"]), 2)

    def test_garbage(self):
        d = sr.parse_directives("sorry, I cannot help")
        self.assertFalse(d["raw_ok"])
        self.assertEqual(d["fixes"], [])


class EvidencePackTests(unittest.TestCase):
    def _summary(self):
        return {
            "model": "hf:x/y",
            "coverage": {"project.godot": True, "main.tscn": False},
            "verify": {"steps": [
                {"rung": "check_only_script", "ok": False, "file": "main.gd",
                 "detail": "Parse Error: Identifier 'Key' not declared"},
                {"rung": "structural_check", "ok": True, "file": "main.tscn",
                 "detail": ""}]},
            "attempts": [
                {"attempt": 0, "prompt_tokens": 900, "completion_tokens": 3000,
                 "passed": False},
                {"attempt": 1, "prompt_tokens": 4200,
                 "completion_tokens": 3000, "passed": False}],
            "total_tokens": 10100, "budget_cap": 15000,
            "failure_class": "verification",
        }

    def test_pack_contents(self):
        pack = sr.build_evidence_pack(3, "PROMPT-BODY", self._summary(),
                                      "LAST-RESPONSE")
        self.assertIn("PROMPT-BODY", pack)
        self.assertIn("MISSING required files: main.tscn", pack)
        self.assertIn("Identifier 'Key' not declared", pack)
        self.assertIn("cumulative: 10100 tok", pack)
        self.assertIn("LAST-RESPONSE", pack)
        self.assertNotIn("DIFF", pack)

    def test_pack_diff_and_cap(self):
        pack = sr.build_evidence_pack(3, "P" * 20000, self._summary(),
                                      "line1\nline2\nline3",
                                      "line1\nCHANGED\nline3")
        self.assertLessEqual(len(pack), sr.EVIDENCE_CHAR_CAP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
