"""Close a campaign that died without finishing.

A campaign whose process ended mid-run (killed, or its provider stalled and the PA moved the
work elsewhere) never writes summary.json, so its status.json says "running" for ever and
every reader - active_status.py, the PA brief, The Crew's Board - keeps showing it as live
or stale. Kris, 2026-10-24: "clean up the stale pt-larry-4 and pt-qwen-3 campaigns".

Nothing is deleted: the campaign's history stays where member_stats.py and rs_scoping.py
read it. Closing it means what a finished campaign looks like:
- every task not accepted or failed becomes "stopped", and the counts say so;
- a campaign_stopped event and a progress.log line give who, when, why and what took over;
- summary.json (outcome "stopped") and a short REPORT.md, so readers treat it as finished.
status.json keeps its own time, so "last activity" stays true.

    python crew/runners/close_campaign.py NAME --reason "..." [--superseded-by OTHER]   # dry run
    python crew/runners/close_campaign.py NAME --reason "..." [--superseded-by OTHER] --apply

It refuses a campaign that already has a summary, or that changed within the last two hours
(it may still be running - one attempt can take half an hour), unless --force.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ALIVE_WITHIN_S = 2 * 3600
FINAL = ("accepted", "failed")


def close(home: Path, name: str, reason: str, superseded_by: str = "", by: str = "Claude",
          apply: bool = False, force: bool = False, now: dt.datetime | None = None) -> dict:
    """-> {"ok", "problem" | "changes", ...}. Writes only when apply is True."""
    folder = home / name
    status_path = folder / "status.json"
    if not status_path.is_file():
        return {"ok": False, "problem": f"{status_path} does not exist"}
    if (folder / "summary.json").exists():
        return {"ok": False, "problem": f"{name} already has a summary: it finished"}
    age = time.time() - status_path.stat().st_mtime
    if age < ALIVE_WITHIN_S and not force:
        return {"ok": False, "problem": f"{name} changed {int(age // 60)} min ago and may still "
                                        f"be running; wait, or use --force"}
    if not reason.strip():
        return {"ok": False, "problem": "say why (--reason)"}

    status = json.loads(status_path.read_text(encoding="utf-8"))
    at = (now or dt.datetime.now()).isoformat(timespec="seconds")
    changes = []
    for tid, task in status.get("tasks", {}).items():
        if task.get("state") not in FINAL:
            changes.append(f"{tid}: {task.get('state')} -> stopped ({task.get('member')}, "
                           f"{task.get('attempts', 0)} attempt(s))")
            task["state"] = "stopped"
            task.pop("eta", None)                   # a forecast for a run that is over
    counts = {}
    for task in status.get("tasks", {}).values():
        counts[task["state"]] = counts.get(task["state"], 0) + 1
    status["counts"] = {**{k: 0 for k in status.get("counts", {})}, **counts}
    stopped = {"by": f"PA ({by})", "at": at, "reason": reason.strip(),
               "superseded_by": superseded_by}
    status.setdefault("events", []).append({"at": at, "event": "campaign_stopped",
                                            **{k: v for k, v in stopped.items() if k != "at"}})

    tasks = status.get("tasks", {})
    summary = {
        "campaign": status.get("campaign", name), "goal": status.get("goal", ""),
        "outcome": "stopped", "tasks": len(tasks),
        "accepted": counts.get("accepted", 0), "failed": counts.get("failed", 0),
        "not_started": sum(1 for t in tasks.values() if not t.get("attempts")),
        "first_try_accepts": sum(1 for t in tasks.values()
                                 if t["state"] == "accepted" and t.get("attempts") == 1),
        "requests": status.get("requests_used", 0),
        "tokens": sum(t.get("tokens") or 0 for t in tasks.values()),
        "wall_seconds": None, "requests_per_accepted": None, "teams": [],
        "failed_gate_counts": {}, "tasks_detail": tasks, "stopped": stopped,
    }
    took_over = f" The work was done in {superseded_by}." if superseded_by else ""
    report = (f"# Campaign report: {summary['campaign']}\n\n**Goal:** {summary['goal']}\n\n"
              f"**Outcome: stopped** by the PA ({by}) on {at[:10]}, without finishing.\n\n"
              f"Why: {reason.strip()}{took_over}\n\n"
              + "".join(f"- {c}\n" for c in changes)
              + "\nNothing was deleted; status.json and progress.log are as the run left them, "
                "plus the stop.\n")
    line = (f"[{at}] campaign stopped by the PA ({by}): {reason.strip()}"
            + (f" - superseded by {superseded_by}" if superseded_by else "") + "\n")
    if apply:
        mtime = status_path.stat().st_mtime
        tmp = status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
        os.replace(tmp, status_path)
        os.utime(status_path, (mtime, mtime))     # last activity stays the run's own
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (folder / "REPORT.md").write_text(report, encoding="utf-8")
        with (folder / "progress.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    return {"ok": True, "applied": apply, "campaign": name, "changes": changes,
            "stopped": stopped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--superseded-by", default="")
    ap.add_argument("--by", default="Claude")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--force", action="store_true", help="close even if it changed recently")
    args = ap.parse_args(argv)
    from crew.config import load_config
    home = Path(load_config().state_home) / "campaigns"
    result = close(home, args.name, args.reason, args.superseded_by, args.by, args.apply,
                   args.force)
    if not result["ok"]:
        print(f"NOT closed: {result['problem']}")
        return 1
    print(("closed" if result["applied"] else "DRY RUN - would close") + f": {args.name}")
    for change in result["changes"] or ["(no task was left open)"]:
        print(f"  {change}")
    if not result["applied"]:
        print("  run again with --apply to write it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
