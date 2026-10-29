"""Tell alive from dead, for a chat turn or a build (Kris, 2026-10-28).

Kris after the crash: "there is no way for me to tell if it's still processing or just appears to
be." A turn that will never finish looked exactly like a slow one, and the only recovery was a
human guessing. Measured the same day: a compact dry run in ses_e8fdcc727ffe46Y7X7MqSenCyX started
15:00:32, the engine was restarted at 15:41, so that turn could never complete - nothing said so.

Read-only. It reads the facts and hands them to `crew/alive_lib.py`, which decides:

- the newest part's `time_created` for the session (the activity, in the engine database)
- the running turn's start (the newest assistant message with no `time.completed`)
- the engine process and when it started (psutil, from its pid)
- a build's pid and start, from its `status.json`
- the QUIET threshold, from `crew/limits.json` (`alive.quiet_s`)

    python crew/runners/alive.py --session ses_x [--db PATH] [--engine-pid N] [--engine-start S]
    python crew/runners/alive.py --build <build dir>

Prints one line: WORKING, QUIET or DEAD, with the age. Exit 0 always except a missing target.
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew import alive_lib  # noqa: E402
from crew.config import load_config  # noqa: E402

LIMITS_FILE = REPO_ROOT / "crew" / "limits.json"


def db_default() -> Path:
    """The chat engine's database (XDG_DATA_HOME wins, as the engine itself honours it)."""
    import os
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"


def quiet_s(default: float = alive_lib.DEFAULT_QUIET_S) -> float:
    """The WORKING/QUIET line from crew/limits.json, or the default when it is not set."""
    try:
        value = json.loads(LIMITS_FILE.read_text(encoding="utf-8")).get("alive", {}).get("quiet_s")
    except (OSError, ValueError, AttributeError):
        return float(default)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else float(default)


def _connect(db: Path, timeout: float = 2.0):
    if not db.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=max(0.05, timeout))
        con.execute(f"pragma busy_timeout={int(max(0.05, timeout) * 1000)}")
        return con
    except sqlite3.Error:
        return None


def _newest_part(con, session: str):
    """The newest part row for the session, as (epoch seconds, part JSON), or (None, None)."""
    columns = [r[1] for r in con.execute("pragma table_info(part)")]
    sid = next((c for c in columns if c.lower() in ("sessionid", "session_id")), "")
    if not sid or "time_created" not in columns:
        return None, None
    try:
        row = con.execute(
            f"select time_created, data from part where {sid} = ? order by time_created desc limit 1",
            (session,)).fetchone()
    except sqlite3.Error:
        return None, None
    if not row:
        return None, None
    try:
        part = json.loads(row[1]) if isinstance(row[1], str) else {}
    except ValueError:
        part = {}
    return _seconds(row[0]), part


def _seconds(value):
    """OpenCode stamps milliseconds; a value that is clearly already seconds is left alone."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value / 1000.0 if value > 1e11 else float(value)


def running_turn(con, session: str):
    """The start (epoch seconds) of the newest assistant message that has not finished.

    A finished turn returns None: rule 2 must never call a turn that is over "dead", and a chat
    with nothing running is simply QUIET while its engine is alive.
    """
    columns = [r[1] for r in con.execute("pragma table_info(message)")]
    sid = next((c for c in columns if c.lower() in ("sessionid", "session_id")), "")
    if not sid:
        return None
    try:
        rows = con.execute(
            f"select data from message where {sid} = ? order by time_created desc limit 20",
            (session,)).fetchall()
    except sqlite3.Error:
        return None
    for (data,) in rows:
        try:
            message = json.loads(data) if isinstance(data, str) else {}
        except ValueError:
            continue
        if message.get("role") != "assistant":
            continue
        time_block = message.get("time") if isinstance(message.get("time"), dict) else {}
        if "completed" not in time_block:
            return _seconds(time_block.get("created"))
    return None


def process_facts(pid, now: float):
    """(alive, start epoch seconds) for a pid. `alive` is None when nobody asked about one."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None, None
    try:
        import psutil
    except ImportError:
        return None, None
    try:
        proc = psutil.Process(pid)
        return proc.is_running(), float(proc.create_time())
    except Exception:                                        # noqa: BLE001 - a gone pid is a fact
        return False, None


def turn_steps(con, session: str):
    """How many assistant messages the newest turn used, and its agent name.

    The window's brief says "up to 60 steps per message"; a turn that reaches the ceiling is cut
    off by the engine, which then injects its own max-steps prompt. Counting is the reliable
    signal - the notice itself is never stored, and a reply may quote its wording.
    """
    columns = [r[1] for r in con.execute("pragma table_info(message)")]
    sid = next((c for c in columns if c.lower() in ("sessionid", "session_id")), "")
    if not sid:
        return 0, ""
    try:
        rows = con.execute(
            f"select data from message where {sid} = ? order by time_created desc", (session,)).fetchall()
    except sqlite3.Error:
        return 0, ""
    used, agent = 0, ""
    for (data,) in rows:
        try:
            message = json.loads(data) if isinstance(data, str) else {}
        except ValueError:
            continue
        role = message.get("role")
        if role == "user":
            break
        if role == "assistant":
            used += 1
            if not agent and message.get("agent"):
                agent = str(message["agent"])
    return used, agent


def step_limit(agent: str):
    """The step ceiling for an agent like `Gordon-assign`, from personnel.json. None if unset."""
    pa = (agent or "").split("-")[0]
    if not pa:
        return None
    try:
        staff = json.loads((REPO_ROOT / "crew" / "personnel.json").read_text(encoding="utf-8"))
        value = (((staff.get("pa") or {}).get("scopes") or {}).get(pa) or {}).get("steps")
    except (OSError, ValueError, AttributeError):
        return None
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def turn_is_over(con, session: str) -> bool:
    """True when the newest assistant message has finished: nothing is running.

    A turn that ENDED normally must not keep reading as WORKING for the next two minutes just
    because its last part is recent - the whole question is "is it still processing?". The
    runner answers it by telling alive_lib to accept no pause at all (quiet_s=0), so a finished
    turn reads QUIET with its age, and only a turn that is genuinely unfinished can be DEAD
    (started before this engine) or WORKING.
    """
    columns = [r[1] for r in con.execute("pragma table_info(message)")]
    sid = next((c for c in columns if c.lower() in ("sessionid", "session_id")), "")
    if not sid:
        return False
    try:
        rows = con.execute(
            f"select data from message where {sid} = ? order by time_created desc limit 20",
            (session,)).fetchall()
    except sqlite3.Error:
        return False
    for (data,) in rows:
        try:
            message = json.loads(data) if isinstance(data, str) else {}
        except ValueError:
            continue
        if message.get("role") != "assistant":
            continue
        time_block = message.get("time") if isinstance(message.get("time"), dict) else {}
        return "completed" in time_block          # the newest assistant message's own state
    return False


def session_report(session: str, db=None, engine_pid=None, engine_start=None, now=None, quiet=None):
    """The facts for one chat, ready to hand to alive_lib.line."""
    db = Path(db) if db else db_default()
    now = time.time() if now is None else now
    con = _connect(db)
    activity = started = None
    doing = ""
    steps = False
    over = False
    if con is not None:
        try:
            activity, part = _newest_part(con, session)
            doing = alive_lib.doing_of(part)
            started = running_turn(con, session)
            over = turn_is_over(con, session)
            used, agent = turn_steps(con, session)
            steps = alive_lib.hit_ceiling(used, step_limit(agent)) or alive_lib.steps_notice(part)
        finally:
            con.close()
    if engine_start is None and engine_pid is not None:
        _, engine_start = process_facts(engine_pid, now)
    alive = None
    if engine_pid is not None:
        alive, _ = process_facts(engine_pid, now)
    # A finished turn accepts no pause: it reports QUIET with its age, never WORKING.
    limit = 0.0 if over else (quiet_s() if quiet is None else quiet)
    return {
        "session": session,
        "now": now,
        "started": started,
        "activity": activity,
        "engine_start": engine_start,
        "alive": alive,
        "steps": steps,
        "turn_over": over,
        "quiet_s": limit,
        "doing": doing,
        "line": alive_lib.line(now, started=started, activity=activity,
                               engine_start=engine_start, alive=alive,
                               quiet_s=limit, doing=doing, steps=steps),
    }


def _newest_mtime(folder: Path):
    newest = None
    try:
        for path in folder.iterdir():
            if path.is_file():
                stamp = path.stat().st_mtime
                newest = stamp if newest is None else max(newest, stamp)
    except OSError:
        return None
    return newest


def build_report(folder, now=None, quiet=None):
    """The facts for one build directory, from its status.json."""
    folder = Path(folder)
    now = time.time() if now is None else now
    status_path = folder / "status.json"
    quiet = quiet_s() if quiet is None else quiet
    if not status_path.is_file():
        return {"build": str(folder), "exists": False, "line": f"DEAD     no status.json in {folder}"}
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"build": str(folder), "exists": True, "line": f"DEAD     unreadable status.json ({exc})"}
    state = str(status.get("state") or "")
    pid = status.get("pid")
    activity = _newest_mtime(folder)
    alive, _ = process_facts(pid, now)
    if state != "running":
        age = alive_lib.age_of(now, activity)
        tail = "no activity recorded yet" if age is None else f"last activity {age}s ago"
        return {"build": str(folder), "exists": True, "state": state, "line":
                f"QUIET    the build is not running (state {state or 'unknown'}); {tail}"}
    started = None
    try:
        started = time.mktime(time.strptime(str(status.get("started")), "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        started = None
    return {"build": str(folder), "exists": True, "state": state, "pid": pid, "line":
            alive_lib.line(now, started=started, activity=activity, alive=alive, quiet_s=quiet)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--session", help="the chat's session id")
    target.add_argument("--build", help="a build directory holding status.json")
    ap.add_argument("--db", default="", help="the engine's opencode.db (default: OpenCode's own)")
    ap.add_argument("--engine-pid", type=int, default=None, help="the running engine's pid")
    ap.add_argument("--engine-start", type=float, default=None, help="the engine's start, epoch seconds")
    ap.add_argument("--quiet", type=float, default=None, help="override crew/limits.json alive.quiet_s")
    a = ap.parse_args(argv)

    if a.build:
        report = build_report(a.build, quiet=a.quiet)
    else:
        report = session_report(a.session, db=a.db or None, engine_pid=a.engine_pid,
                                engine_start=a.engine_start, quiet=a.quiet)
    print(report["line"])
    return 0 if report.get("exists", True) else 1


if __name__ == "__main__":
    sys.exit(main())
