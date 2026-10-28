"""The guard: every OpenCode job runs through launch() here, and is stopped by software, not
by an AI, the moment it stops earning its tokens.

Kris, 2026-10-26, after Kimi's Inbox build ran 80 steps / 8.6M tokens and ~20 failed tool
calls without anything stopping it: "CREATE A TOOL THAT DOES THIS AND DOES NOT RELY ON AI
AT ALL", and: "How can we not see a difference between a tool that is using too many
tokens and completing the job versus a mis-scoped tool that fails repeatedly?"

The difference is PROGRESS, which software can see in the job's own OpenCode database:
a code edit that went through, or a test/build command (limits.json progress_commands)
that exited 0. Reading and searching are not progress. So:

- under budget_tokens a job may go stall_steps steps without progress (stall_steps_opening
  for the opening read, before its first change: a new pane needs one, 2026-10-26);
- past budget_tokens it may go only stall_steps_over_budget: it carries on while it is
  still producing, and stops as soon as it is only spending;
- failures stop it whatever its progress: failed tool calls, failures in a row, the same
  error repeated;
- the ceilings (tokens, fresh tokens, steps, minutes) stop it no matter what;
- between check rounds, next_round() allows another round only if the last one passed
  MORE checks than the one before - repeating a failure is not working through it.

Limits live in crew/limits.json: defaults, then the job type, then the member; a ceiling
is the tightest of all three, any other setting the most specific one's. tests/test_guard.py fails if any runner starts opencode.exe without
launch(), so the guard cannot be forgotten.

  python -m crew.guard <job dir>             counts vs limits for a running or finished job
  python -m crew.guard <job dir> --replay    where a finished job WOULD have been stopped
"""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

LIMITS = Path(__file__).resolve().parent / "limits.json"


FLOORS = ("min_free_gb",)     # a floor, not a ceiling: the HIGHEST wins (the tightest)


# Safety limits: the tightest of defaults, job type and member always wins, so no layer can
# loosen them. Every other number (budget_tokens, stall_*, max_* error counts, check rounds)
# is a working setting: the most specific layer wins, so each member can be tuned from its
# own replays - looser as well as tighter (Kris 2026-10-26: different models react
# differently; Gordon's cheap tokens needed a larger budget than the default, 2026-10-27).
CEILING_KEYS = ("ceiling_tokens", "ceiling_fresh_tokens", "ceiling_steps", "max_minutes")


def limits(member: str, job: str = "build", path: Path = LIMITS) -> dict:
    """The effective limits for one member on one job type: a ceiling the lowest of all
    layers, a floor (min_free_gb) the highest, anything else the most specific layer's."""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    out = dict(cfg.get("defaults") or {})
    for layer in ((cfg.get("jobs") or {}).get(job) or {}, (cfg.get("members") or {}).get(member) or {}):
        for k, v in layer.items():
            both = isinstance(v, (int, float)) and isinstance(out.get(k), (int, float))
            if both and k in CEILING_KEYS:
                out[k] = min(out[k], v)
            elif both and k in FLOORS:
                out[k] = max(out[k], v)
            else:
                out[k] = v
    return out


def db_path(job_dir: Path) -> Path:
    return Path(job_dir) / "data" / "opencode" / "opencode.db"


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


def _progress(p: dict, commands) -> bool:
    state = p.get("state") or {}
    if state.get("status") != "completed":
        return False
    if p.get("tool") in ("edit", "write", "patch", "multiedit"):
        return True
    if p.get("tool") == "bash":
        cmd = " ".join(str((state.get("input") or {}).get("command") or "").split())
        return (state.get("metadata") or {}).get("exit") == 0 and any(c in cmd for c in commands)
    return False


def count(parts: list, commands=()) -> dict:
    """Steps, tokens, progress and tool errors so far, from the job's database parts."""
    c = {"steps": 0, "tokens": 0, "fresh_tokens": 0, "tool_calls": 0, "tool_errors": 0,
         "errors_in_a_row": 0, "same_error": 0, "progress": 0, "since_progress": 0,
         "last_error": ""}
    seen, run = {}, 0
    for p in parts:
        if p.get("type") == "step-finish":
            k = p.get("tokens") or {}
            fresh = k.get("input", 0) + k.get("output", 0) + k.get("reasoning", 0)
            c["steps"] += 1
            c["since_progress"] += 1
            c["fresh_tokens"] += fresh
            c["tokens"] += fresh + (k.get("cache") or {}).get("read", 0)
        elif p.get("type") == "tool":
            state = p.get("state") or {}
            if state.get("status") not in ("completed", "error"):
                continue                   # still running
            c["tool_calls"] += 1
            if state.get("status") == "error":
                key = f"{p.get('tool')}: " + " ".join(str(state.get("error") or "").split())[:80]
                seen[key] = seen.get(key, 0) + 1
                run += 1
                c["tool_errors"] += 1
                c["last_error"] = key
                c["same_error"] = max(c["same_error"], seen[key])
            else:
                run = 0
                if _progress(p, commands):
                    c["progress"] += 1
                    c["since_progress"] = 0
            c["errors_in_a_row"] = max(c["errors_in_a_row"], run)
    return c


CEILINGS = (("tokens", "ceiling_tokens", "tokens"),
            ("fresh_tokens", "ceiling_fresh_tokens", "fresh (uncached) tokens"),
            ("steps", "ceiling_steps", "steps"))
FAILURES = (("tool_errors", "max_tool_errors", "failed tool calls"),
            ("errors_in_a_row", "max_errors_in_a_row", "failed tool calls in a row"),
            ("same_error", "max_same_error", "repeats of the same error"))


def weighed(c: dict, lim: dict) -> dict:
    """Token counts in Kimi-equivalent tokens: a member's tokens x its cost_weight (limits.json,
    1.0 = Kimi). Budgets and token ceilings are set in these units, so a cheap member (Gordon,
    Barry, Larry) gets proportionally more room (Kris 2026-10-27). Steps, minutes and the
    no-progress and failure rules are not weighed: wasted steps are waste on any model."""
    w = float(lim.get("cost_weight", 1.0))
    return {**c, "tokens": int(c["tokens"] * w), "fresh_tokens": int(c["fresh_tokens"] * w)}


def verdict(c: dict, lim: dict, seconds: float = 0) -> str:
    """'' while the job may go on, else the reason it is stopped."""
    c = weighed(c, lim)
    for key, limit, label in CEILINGS:
        if limit in lim and c[key] >= lim[limit]:
            unit = " (weighed)" if "tokens" in key and lim.get("cost_weight", 1) != 1 else ""
            return f"ceiling: {c[key]:,} {label}{unit}, ceiling {lim[limit]:,}"
    for key, limit, label in FAILURES:
        if limit in lim and c[key] >= lim[limit]:
            return f"failing: {c[key]:,} {label}, limit {lim[limit]:,} (last: {c['last_error']})"
    over = c["tokens"] >= lim.get("budget_tokens", float("inf"))
    stall = lim.get("stall_steps_over_budget" if over else "stall_steps")
    if not c["progress"] and not over:      # the opening read, before the first change
        stall = lim.get("stall_steps_opening", stall)
    if stall is not None and c["since_progress"] >= stall:
        return (f"no progress: {c['since_progress']} steps without a code change or a passing "
                f"test/build{', past the token budget' if over else ''} (limit {stall})")
    if "max_minutes" in lim and seconds >= lim["max_minutes"] * 60:
        return f"ceiling: {seconds / 60:.0f} minutes, ceiling {lim['max_minutes']}"
    return ""


def next_round(passing: list) -> bool:
    """passing = checks passed after each round so far. Another round only if the last one
    improved on the one before (the first failed round always gets its retry)."""
    return len(passing) < 2 or passing[-1] > passing[-2]


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def free_gb(path) -> float:
    """Free space in GB on the drive that holds path; walks up to the nearest existing parent
    (a job's home may not exist yet, but its drive does)."""
    p = Path(path).resolve()
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free / (1024 ** 3)


def disk_reason(lim: dict, path) -> str:
    """'' unless the drive holding path has less free space than min_free_gb, else the reason.
    Software checks it before launch() and on every poll of watch(): a full disk is what made
    Kimi's Inbox build fail (2026-10-26)."""
    floor = lim.get("min_free_gb")
    if not floor:
        return ""
    free = free_gb(path)
    if free < floor:
        root = Path(path).resolve().anchor or str(path)
        return f"disk: {free:.1f} GB free on {root}, below min_free_gb {floor}"
    return ""


def watch(proc, db: Path, lim: dict, started: float, on_poll=None, disk=None) -> str:
    """Wait for proc, checking the limits every poll_seconds; kill it the moment one trips.
    started is when the whole job began, so minutes count across rounds."""
    poll = max(2, int(lim.get("poll_seconds", 15)))
    commands = lim.get("progress_commands") or ()
    while True:
        try:
            proc.wait(timeout=poll)
            done = True
        except subprocess.TimeoutExpired:
            done = False
        c = count(_parts(db), commands)
        why = verdict(c, lim, time.time() - started)
        if not why and not done and disk:
            why = disk_reason(lim, disk)
        if on_poll:
            on_poll(c)
        if why and not done:
            kill_tree(proc.pid)
            proc.wait()
        if why or done:
            return why                     # tripped on the last step: still stop the job


# Variables a job must never inherit from the chat engine it may be started from. The window
# runs the engine with OPENCODE_SERVER_PASSWORD (engine.rs); a job started from a PA's chat
# shell inherited it, and `opencode run`'s in-process server then refused its own client:
# "service=server error= failed", "Session not found", every build (2026-10-28, first
# blamed on sleep). OPENCODE_PERMISSION / _CONFIG_CONTENT would override the job's config.
ENGINE_ONLY_ENV = ("OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME",
                   "OPENCODE_PERMISSION", "OPENCODE_CONFIG_CONTENT")


def launch(argv: list, cwd: Path, env: dict, home: Path, name: str, lim: dict, started: float,
           timeout_s: float = None, on_poll=None) -> tuple:
    """THE way to run opencode.exe: its own database under home/data (the guard reads it,
    and parallel jobs never lock each other), output to home/<name>.jsonl, watched.
    -> (stdout, stderr, returncode, stopped reason or ''); returncode is None when the
    disk check refuses the job before it starts."""
    home.mkdir(parents=True, exist_ok=True)
    refused = disk_reason(lim, home)     # a full disk: refuse before the job writes anything
    if refused:
        (home / "guard.json").write_text(json.dumps({"stopped": refused, "counts": count(
            _parts(db_path(home)), lim.get("progress_commands") or ())}, indent=1), encoding="utf-8")
        return "", "", None, refused
    env = {k: v for k, v in env.items() if k not in ENGINE_ONLY_ENV}
    env["XDG_DATA_HOME"] = str(home / "data")
    if timeout_s:                          # the caller's own timeout, counted from started
        lim = {**lim, "max_minutes": min(lim.get("max_minutes", float("inf")),
                                         (time.time() - started + timeout_s) / 60)}
    out_f, err_f = home / f"{name}.jsonl", home / f"{name}.stderr.txt"
    with open(out_f, "w", encoding="utf-8") as fo, open(err_f, "w", encoding="utf-8") as fe:
        p = subprocess.Popen(argv, cwd=str(cwd), stdout=fo, stderr=fe, env=env)
        stopped = watch(p, Path(env["XDG_DATA_HOME"]) / "opencode" / "opencode.db", lim,
                        started, on_poll, disk=home)
    if stopped:
        (home / "guard.json").write_text(json.dumps({"stopped": stopped, "counts": count(
            _parts(db_path(home)), lim.get("progress_commands") or ())}, indent=1), encoding="utf-8")
    return (out_f.read_text(encoding="utf-8", errors="replace"),
            err_f.read_text(encoding="utf-8", errors="replace"), p.returncode, stopped)


def replay(parts: list, lim: dict) -> tuple:
    """-> (index into parts where the guard would have stopped, reason) or (None, '')."""
    commands = lim.get("progress_commands") or ()
    for i in range(1, len(parts) + 1):
        why = verdict(count(parts[:i], commands), lim)
        if why:
            return i, why
    return None, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("job_dir", help="runs/crew/pa/builds/<name> or runs/crew/opencode/<label>")
    ap.add_argument("--member", default="", help="default: status.json's pa or member")
    ap.add_argument("--job", default="", help="build, fix, ...; default: build for a PA build")
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args(argv)
    d = Path(a.job_dir)
    try:
        st = json.loads((d / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}                            # missing, or cut short (a full disk, 2026-10-26)
    member = a.member or st.get("pa") or st.get("member") or ""
    job = a.job or ("build" if st.get("pa") else "module")
    lim = limits(member, job)
    parts = _parts(db_path(d))
    c = count(parts, lim.get("progress_commands") or ())
    print(f"{d.name} ({member or '?'}, {job}, cost weight {lim.get('cost_weight', 1.0)})")
    raw, c = c, weighed(c, lim)
    for key, limit, label in CEILINGS + FAILURES:
        print(f"  {label:28} {c[key]:>12,} / {lim.get(limit, '-'):,}")
    print(f"  {'progress events':28} {c['progress']:>12,}   steps since: {c['since_progress']}")
    if raw["tokens"] != c["tokens"]:
        print(f"  {'(raw tokens)':28} {raw['tokens']:>12,}")
    if a.replay:
        i, why = replay(parts, lim)
        n = count(parts[:i])["steps"] if i else c["steps"]
        print(f"  replay: {'stopped at step ' + str(n) + ': ' + why if i else 'never stopped'}")
    else:
        print(f"  {verdict(raw, lim) or 'may go on'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
