"""What's actually running right now, across every crew driver, in one view.

Kris, 2026-09-22: "make sure the crew display information for the PM and
other users to know when processes are active." Every long-running driver
in this repo already writes a live status.json as it works
(`archaeology_swarm.py`'s `Status` class; `crew/campaign.py`'s own
`write_status`) - this just reads all of them at once instead of making
someone hunt down a log file per background process, which is what this
whole session has been doing by hand until now.

    python crew/runners/active_status.py                 # everything, once
    python crew/runners/active_status.py --watch 15       # re-print every 15s

A run counts ACTIVE if its status file says a non-terminal stage AND was
updated within the last STALE_AFTER_S seconds; STALE if non-terminal but
hasn't been touched in a while (probably crashed or was killed without
finishing cleanly - worth a human look); DONE if it reached a terminal
stage, or a campaign, a summary.json/REPORT.md exists beside it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.config import load_config  # noqa: E402

STALE_AFTER_S = 600      # 10 min with no update on a non-terminal stage
ARCH_TERMINAL = {"complete", "complete_no_unify", "complete_recon_only",
                 "failed_no_recon", "failed_no_plan"}


def _age_s(iso: str) -> float:
    try:
        return (datetime.datetime.now() - datetime.datetime.fromisoformat(iso)).total_seconds()
    except (ValueError, TypeError):
        return 1e9


def _fmt_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    return f"{seconds / 3600:.1f}h ago"


def archaeology_rows(root: Path) -> list:
    rows = []
    for status_path in sorted(root.glob("*/status.json")):
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        age = _age_s(data.get("updated_at", ""))
        stage = data.get("stage", "?")
        if stage in ARCH_TERMINAL:
            state = "DONE"
        elif age > STALE_AFTER_S:
            state = "STALE"
        else:
            state = "ACTIVE"
        members = data.get("members", {})
        member_bits = ", ".join(
            f"{m}:{v.get('state', '?')}"
            + (f"(attempt {v['attempt']})" if v.get("attempt") else "")
            for m, v in members.items())
        rows.append({"kind": "archaeology", "name": data.get("name", status_path.parent.name),
                    "state": state, "stage": stage, "age": age,
                    "detail": member_bits or "-", "requests": data.get("requests_used", 0)})
    return rows


def campaign_rows(root: Path) -> list:
    rows = []
    for status_path in sorted(root.glob("*/status.json")):
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        finished = (status_path.parent / "summary.json").is_file()
        age = _age_s(data.get("updated", ""))
        counts = data.get("counts", {})
        running = counts.get("running", 0)
        if finished:
            state = "DONE"
        elif running or age <= STALE_AFTER_S:
            state = "ACTIVE"
        else:
            state = "STALE"
        detail = ", ".join(f"{k}:{v}" for k, v in counts.items() if v) or "-"
        rows.append({"kind": "campaign", "name": data.get("campaign", status_path.parent.name),
                    "state": state, "stage": f"{running} running", "age": age,
                    "detail": detail, "requests": data.get("requests_used", 0)})
    return rows


def render(rows: list) -> str:
    if not rows:
        return "(nothing has ever written a status.json yet)"
    rows = sorted(rows, key=lambda r: r["age"])
    active = [r for r in rows if r["state"] == "ACTIVE"]
    lines = [f"{len(active)} active, {len(rows)} total "
            f"({time.strftime('%H:%M:%S')})", ""]
    width_name = max(len(r["name"]) for r in rows) + 2
    for r in rows:
        mark = {"ACTIVE": "*", "STALE": "!", "DONE": " "}[r["state"]]
        lines.append(f"{mark} [{r['state']:>6}] {r['name']:<{width_name}} "
                    f"{r['kind']:<11} {_fmt_age(r['age']):>10}  {r['detail']}")
    return "\n".join(lines)


def collect() -> list:
    home = Path(load_config().state_home)
    return (archaeology_rows(home / "outbox" / "archaeology")
           + campaign_rows(home / "campaigns"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=float, default=0,
                    help="re-print every N seconds instead of once")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    while True:
        rows = collect()
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            if args.watch:
                print("\033c", end="")            # clear terminal between refreshes
            print(render(rows))
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main())
