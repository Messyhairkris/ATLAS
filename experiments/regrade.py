"""Re-verify a historic battery run against the current verifier/extractor,
without spending any tokens (uses saved response.txt files).

    python experiments/regrade.py runs/battery-YYYYMMDD-HHMMSS

Writes regrade-<ts>.json into the run dir. Useful when the harness changes:
old model outputs are rejudged under new rules instead of re-generated.
"""

import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENTS))

from godot_battery import extract_files, expected_coverage  # noqa: E402
import verify as verify_mod  # noqa: E402


def regrade(run_dir: Path) -> dict:
    summaries = []
    for summary_path in sorted(run_dir.glob("*/*/summary.json")):
        old = json.loads(summary_path.read_text(encoding="utf-8"))
        tier_dir = summary_path.parent
        tier = old["tier"]
        # Mirror the battery's attempt semantics: pass if ANY attempt passes.
        attempt_outputs = [("base", tier_dir / "response.txt")]
        attempt_outputs += sorted(
            (p.parent.name, p.parent / "response.txt")
            for p in tier_dir.glob("repair*/response.txt")
        )
        attempts_report = []
        final = None
        for attempt_name, response_path in attempt_outputs:
            if not response_path.exists():
                continue
            text = response_path.read_text(encoding="utf-8")
            files = extract_files(text)
            coverage = expected_coverage(tier, files)
            verify = None
            if files:
                verify = verify_mod.verify_tier(
                    tier, files, tier_dir / f"work-regrade-{attempt_name}",
                )
            passed = (bool(files) and all(coverage.values())
                      and bool(verify and verify.get("passed")))
            verdicts = {(s.get("rung"), s.get("file")): s.get("ok")
                        for s in (verify or {}).get("steps", [])}
            attempts_report.append({
                "attempt": attempt_name, "passed": passed,
                "files": len(files),
                "failed_rungs": [k for k, v in verdicts.items() if not v],
            })
            final = {"passed": passed, "coverage": coverage,
                     "files": len(files)}
            if passed:
                break
        if final is None:
            continue
        summaries.append({
            "model": old["model"], "tier": tier,
            "old_passed": old.get("passed"), "new_passed": final["passed"],
            "files_extracted": final["files"], "coverage": final["coverage"],
            "attempts": attempts_report,
            "total_tokens": old.get("total_tokens", 0),
        })
    return {"run": str(run_dir), "regraded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "summaries": summaries}


def main() -> int:
    run_dir = Path(sys.argv[1])
    report = regrade(run_dir)
    out = run_dir / f"regrade-{int(time.time())}.json"
    out.write_text(json.dumps(report, indent=2))
    changed = 0
    for s in report["summaries"]:
        flag = "" if s["old_passed"] == s["new_passed"] else "  <-- VERDICT CHANGED"
        changed += s["old_passed"] != s["new_passed"]
        attempts = " ".join(
            f"{a['attempt']}:{'P' if a['passed'] else 'F'}"
            for a in s.get("attempts", []))
        print(f"{s['model']} T{s['tier']}: {s['old_passed']} -> {s['new_passed']}"
              f" [{attempts}] missing="
              f"{[k for k, v in s['coverage'].items() if not v]}{flag}")
    n = sum(1 for s in report["summaries"] if s["new_passed"])
    print(f"\n{len(report['summaries'])} tier-runs regraded, {n} now passing, "
          f"{changed} verdict changes. Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
