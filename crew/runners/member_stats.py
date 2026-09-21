"""Per-member record across campaigns, computed from each campaign's status.json.

Arithmetic belongs to the harness, not to a member: a report task asked Hoss to sum
these figures and the grounding gate rightly refused the sums, because a total is not
in any source. This prints the table instead, so a digest can quote it verbatim.

    python crew/runners/member_stats.py [campaign ...]     (default: every campaign)
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

CAMPAIGNS = Path(__file__).resolve().parents[2] / "runs" / "crew" / "campaigns"
FIELDS = ("modules", "modules_ok", "modules_first_try", "tests", "tests_ok",
          "attempts", "requests")


def tally(names: list) -> dict:
    rows: dict = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    for name in names:
        status = CAMPAIGNS / name / "status.json"
        if not status.is_file():
            continue
        for task in json.loads(status.read_text(encoding="utf-8"))["tasks"].values():
            if not task.get("attempts"):
                continue                      # never started: says nothing about the member
            row = rows[task["member"]]
            kind = "modules" if task["kind"] == "module" else "tests"
            ok = task["state"] == "accepted"
            row[kind] += 1
            row[kind + "_ok"] += ok
            if kind == "modules":
                row["modules_first_try"] += ok and task["attempts"] == 1
            row["attempts"] += task["attempts"]
            row["requests"] += task.get("requests") or 0
    return dict(rows)


def main() -> int:
    names = sys.argv[1:] or sorted(p.name for p in CAMPAIGNS.iterdir() if p.is_dir())
    rows = tally(names)
    print(f"Campaigns: {', '.join(names)}\n")
    print("| member | modules accepted | first try | tests accepted | attempts | requests |")
    print("|---|---|---|---|---|---|")
    for member in sorted(rows):
        r = rows[member]
        print(f"| {member} | {r['modules_ok']}/{r['modules']} | {r['modules_first_try']} | "
              f"{r['tests_ok']}/{r['tests']} | {r['attempts']} | {r['requests']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
