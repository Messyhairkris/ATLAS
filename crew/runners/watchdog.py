"""Watchdog: every crew run either shows progress, finishes, or is flagged - never silent.

Kris, 2026-09-26: "If this is going to be a process we rely on it needs to be
dependable, and trackable." Nemotron's OpenCode v3 hung 3 hours and the Review
Desk learner ran 3 hours with no sign of progress; both were found only by
chance. This reads every run's status.json and decides:

  lost     the file says running but its process is gone -> the file is marked
           "lost" (a killed run otherwise says "running" forever)
  stalled  it writes a heartbeat, and the heartbeat is older than STALL_S
  overdue  its worst-case finish time (eta.worst_by) has passed
  killed   stalled past KILL_STALL_S, or overdue past its grace period, AND the
           process is one the crew started (its command line runs a script from
           this repo). The whole process tree is killed (taskkill /T - a plain
           kill leaves opencode.exe grandchildren behind) and the status marked.

Anything else on the machine is never touched. Every decision goes to
runs/crew/watchdog/watchdog.log; the current picture to report.json, which the
status overlay shows.

    python watchdog.py            # scan once, act, print the report
    python watchdog.py --dry-run  # scan once, change nothing
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "runs" / "crew"
HOME = RUNS / "watchdog"
PATTERNS = ("jobs/*/status.json", "opencode/*/status.json", "special_teams/*/status.json",
            "fsm/*/status.json", "campaigns/*/status.json", "timed/*/status.json")
STALL_S = 180                  # no heartbeat for 3 min: flag it
KILL_STALL_S = 15 * 60         # no heartbeat for 15 min: stop it
OVERDUE_GRACE_MIN = 30         # past worst case by max(30 min, 2 x worst case): stop it
RECENT_S = 24 * 3600           # older status files are history, not live runs


def _now() -> dt.datetime:
    return dt.datetime.now()


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(p: Path, data: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _proc(pid):
    import psutil
    try:
        return psutil.Process(int(pid))
    except (psutil.Error, TypeError, ValueError):
        return None


def ours(proc) -> bool:
    """Only processes the crew started: their command line runs a file in this repo."""
    try:
        cmd = " ".join(proc.cmdline()).replace("/", "\\").lower()
    except Exception:  # noqa: BLE001 - access denied etc.: not ours to touch
        return False
    return str(REPO).lower() in cmd or ("crew\\runners\\" in cmd and "python" in cmd)


def _at(hhmm: str, ref: dt.datetime):
    """eta.worst_by is 'HH:MM' on the day the run started (or the next day)."""
    try:
        h, m = map(int, hhmm.split(":"))
    except (ValueError, AttributeError):
        return None
    t = ref.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t >= ref - dt.timedelta(minutes=1) else t + dt.timedelta(days=1)


def _started(s: dict, p: Path) -> dt.datetime:
    raw = s.get("started") or ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%H:%M:%S"):
        try:
            t = dt.datetime.strptime(raw[:19], fmt)
            if fmt == "%H:%M:%S":
                t = dt.datetime.fromtimestamp(p.stat().st_ctime).replace(
                    hour=t.hour, minute=t.minute, second=t.second)
            return t
        except ValueError:
            continue
    return dt.datetime.fromtimestamp(p.stat().st_ctime)


def assess(s: dict, p: Path, now: dt.datetime, alive: bool) -> dict:
    """-> {verdict: ok|lost|stalled|overdue, kill: bool, why}"""
    if not alive:
        return {"verdict": "lost", "kill": False, "why": "process is gone"}
    hb = s.get("heartbeat")
    if hb:
        try:
            age = (now - dt.datetime.fromisoformat(hb)).total_seconds()
        except ValueError:
            age = 0
        if age > STALL_S:
            return {"verdict": "stalled", "kill": age > KILL_STALL_S,
                    "why": f"no heartbeat for {age / 60:.0f} min"}
    eta = s.get("eta") or {}
    if eta.get("worst_by"):
        started = _started(s, p)
        worst = _at(eta["worst_by"], started)
        if worst and now > worst:
            late = (now - worst).total_seconds() / 60
            grace = max(OVERDUE_GRACE_MIN, 2 * float(eta.get("worst_minutes") or 0))
            return {"verdict": "overdue", "kill": late > grace,
                    "why": f"{late:.0f} min past its worst-case finish ({eta['worst_by']})"}
    return {"verdict": "ok", "kill": False, "why": ""}


def kill_tree(pid) -> bool:
    r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, text=True)
    return r.returncode == 0


def scan(act: bool = True) -> dict:
    now = _now()
    flagged, log = [], []
    for pattern in PATTERNS:
        for p in RUNS.glob(pattern):
            s = _read(p)
            if not s or s.get("state") != "running":
                continue
            try:
                if time.time() - p.stat().st_mtime > RECENT_S:
                    continue
            except OSError:
                continue
            pid = s.get("pid")
            proc = _proc(pid) if pid else None
            if not pid:
                continue                      # cannot judge a run that names no process
            a = assess(s, p, now, proc is not None and proc.is_running())
            if a["verdict"] == "ok":
                continue
            entry = {"run": str(p.parent.relative_to(RUNS)), "pid": pid, **a}
            if act and a["verdict"] == "lost":
                _write(p, {**s, "state": "lost", "watchdog": f"{now:%H:%M} process was gone"})
                entry["action"] = "marked lost"
            elif act and a["kill"]:
                if proc is not None and ours(proc):
                    ok = kill_tree(pid)
                    _write(p, {**s, "state": "killed by watchdog" if ok else s["state"],
                               "watchdog": f"{now:%H:%M} {a['why']}"})
                    entry["action"] = "killed (process tree)" if ok else "kill failed"
                else:
                    entry["action"] = "not killed: not a crew-started process"
            flagged.append(entry)
            log.append(f"{now:%Y-%m-%dT%H:%M:%S} {entry['verdict']:8} {entry['run']} pid={pid} "
                       f"{entry['why']} {entry.get('action', '')}".rstrip())
    report = {"checked": now.isoformat(timespec="seconds"), "flagged": flagged}
    if act:
        HOME.mkdir(parents=True, exist_ok=True)
        _write(HOME / "report.json", report)
        if log:
            with open(HOME / "watchdog.log", "a", encoding="utf-8") as fh:
                fh.write("\n".join(log) + "\n")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(REPO))
    print(json.dumps(scan(act=not a.dry_run), indent=1))
