"""The guard: stop an OpenCode job the moment it crosses a limit. Software only, no AI.

Kris, 2026-10-26, after Kimi's Inbox build ran 80 steps / 8.6M tokens and ~20 failed tool
calls without anything stopping it: "CREATE A TOOL THAT DOES THIS AND DOES NOT RELY ON AI
AT ALL TO FUNCTION." The limits live in crew/limits.json (the tightest of defaults, job
type and member wins). The guard reads the job's own OpenCode database read-only - the
same numbers the provider bills - so it needs nothing from the model.

  python -m crew.guard <build dir>             counts vs limits for a running or finished job
  python -m crew.guard <build dir> --replay    where a finished job WOULD have been stopped
"""

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

LIMITS = Path(__file__).resolve().parent / "limits.json"


def limits(member: str, job: str = "build", path: Path = LIMITS) -> dict:
    """The effective limits for one member on one job type: the tightest value wins."""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    out = dict(cfg.get("defaults") or {})
    for layer in ((cfg.get("jobs") or {}).get(job) or {}, (cfg.get("members") or {}).get(member) or {}):
        for k, v in layer.items():
            out[k] = v if k not in out or k == "poll_seconds" else min(out[k], v)
    return out


def db_path(build_dir: Path) -> Path:
    return Path(build_dir) / "data" / "opencode" / "opencode.db"


def _parts(db: Path) -> list:
    if not db.is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            return [json.loads(s) for (s,) in con.execute("select data from part order by rowid")]
        finally:
            con.close()
    except sqlite3.Error:
        return []                          # busy or mid-migration: count again next poll


def count(parts: list) -> dict:
    """Steps, tokens and tool errors so far, plus every error's (tool, text) key in order."""
    c = {"steps": 0, "tokens": 0, "fresh_tokens": 0, "tool_calls": 0, "tool_errors": 0,
         "errors_in_a_row": 0, "same_error": 0, "last_error": ""}
    seen, run = {}, 0
    for p in parts:
        if p.get("type") == "step-finish":
            k = p.get("tokens") or {}
            fresh = k.get("input", 0) + k.get("output", 0) + k.get("reasoning", 0)
            c["steps"] += 1
            c["fresh_tokens"] += fresh
            c["tokens"] += fresh + (k.get("cache") or {}).get("read", 0)
        elif p.get("type") == "tool":
            state = p.get("state") or {}
            if state.get("status") not in ("completed", "error"):
                continue                   # still running
            c["tool_calls"] += 1
            if state.get("status") == "error":
                text = " ".join(str(state.get("error") or "").split())[:80]
                key = f"{p.get('tool')}: {text}"
                seen[key] = seen.get(key, 0) + 1
                run += 1
                c["tool_errors"] += 1
                c["last_error"] = key
                c["same_error"] = max(c["same_error"], seen[key])
            else:
                run = 0
            c["errors_in_a_row"] = max(c["errors_in_a_row"], run)
    return c


CHECKS = (("steps", "max_steps", "steps"), ("tokens", "max_tokens", "tokens"),
          ("fresh_tokens", "max_fresh_tokens", "fresh (uncached) tokens"),
          ("tool_errors", "max_tool_errors", "failed tool calls"),
          ("errors_in_a_row", "max_errors_in_a_row", "failed tool calls in a row"),
          ("same_error", "max_same_error", "repeats of the same error"))


def verdict(c: dict, lim: dict, seconds: float = 0) -> str:
    """'' while inside every limit, else the reason the job is stopped."""
    for key, limit, label in CHECKS:
        if limit in lim and c[key] >= lim[limit]:
            why = f" (last: {c['last_error']})" if "error" in key and c["last_error"] else ""
            return f"limit reached: {c[key]:,} {label}, limit {lim[limit]:,}{why}"
    if "max_minutes" in lim and seconds >= lim["max_minutes"] * 60:
        return f"limit reached: {seconds / 60:.0f} minutes, limit {lim['max_minutes']}"
    return ""


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def run(proc, db: Path, lim: dict, started: float, on_poll=None) -> str:
    """Wait for proc, checking the limits every poll_seconds; kill it the moment one trips.
    started is when the whole job began, so minutes count across rounds."""
    poll = max(2, int(lim.get("poll_seconds", 15)))
    while True:
        try:
            proc.wait(timeout=poll)
            done = True
        except subprocess.TimeoutExpired:
            done = False
        c = count(_parts(db))
        why = verdict(c, lim, time.time() - started)
        if on_poll:
            on_poll(c)
        if why and not done:
            kill_tree(proc.pid)
            proc.wait()
            return why
        if done:
            return why                     # tripped on the last step: still stop the job


def replay(parts: list, lim: dict) -> tuple:
    """-> (index into parts where the guard would have stopped, reason) or (None, '')."""
    for i in range(1, len(parts) + 1):
        why = verdict(count(parts[:i]), lim)
        if why:
            return i, why
    return None, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("build_dir", help="runs/crew/pa/builds/<name>")
    ap.add_argument("--member", default="", help="default: status.json's pa")
    ap.add_argument("--job", default="build")
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args(argv)
    d = Path(a.build_dir)
    st = d / "status.json"
    member = a.member or (json.loads(st.read_text(encoding="utf-8")).get("pa", "") if st.is_file() else "")
    lim = limits(member, a.job)
    parts = _parts(db_path(d))
    c = count(parts)
    print(f"{d.name} ({member or '?'}, {a.job})")
    for key, limit, label in CHECKS:
        print(f"  {label:28} {c[key]:>12,} / {lim.get(limit, '-'):,}")
    if a.replay:
        i, why = replay(parts, lim)
        n = count(parts[:i])["steps"] if i else c["steps"]
        print(f"  replay: {'stopped at step ' + str(n) + ': ' + why if i else 'never stopped'}")
    else:
        print(f"  {verdict(c, lim) or 'inside every limit'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
