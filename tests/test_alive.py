"""crew/runners/alive.py - tell alive from dead, for chats and builds (Kris, 2026-10-28).

The live engine database is never touched: every test builds its own SQLite file with OpenCode's
real shape, and pids are real processes the test controls - itself for "alive", a finished child
for "gone". The engine's start time is passed in, so the "started before the engine" rule is
deterministic.

The three cases Kris's crash asked for: a recent part is WORKING; an old part with a live pid is
QUIET; a turn older than the engine start, or a gone pid, is DEAD.
"""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "crew" / "runners" / "alive.py"
SESSION = "ses_alive_test"
NOW = 1_793_233_217.0     # a real epoch, so the millisecond stamps are realistic


def _load():
    spec = importlib.util.spec_from_file_location("alive", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


alive = _load()


def _db(path, parts=(), messages=()):
    """OpenCode's real shape: ids and times are columns, the JSON is only the row's own fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table message (id text, session_id text, time_created integer, time_updated integer, data text)")
    con.execute("create table part (id text, message_id text, session_id text, time_created integer, time_updated integer, data text)")
    for i, (created, part) in enumerate(parts):
        con.execute("insert into message values (?,?,?,?,?)", (f"m{i}", SESSION, 0, 0, "{}"))
        con.execute("insert into part values (?,?,?,?,?,?)",
                    (f"p{i}", f"m{i}", SESSION, created, created, json.dumps(part)))
    for i, (created, message) in enumerate(messages):
        con.execute("insert into message values (?,?,?,?,?)",
                    (f"msg{i}", SESSION, created, created, json.dumps(message)))
    con.commit()
    con.close()
    return path


def _part_at(epoch, body=None):
    """A part row created at a real epoch, in the engine's milliseconds."""
    return (int(epoch * 1000), body if body is not None else {"type": "tool", "tool": "read"})


def _part(seconds_ago, body=None):
    return _part_at(NOW - seconds_ago, body)


def _assistant(seconds_ago, completed=False):
    block = {"created": int((NOW - seconds_ago) * 1000)}
    if completed:
        block["completed"] = block["created"] + 500
    return (int((NOW - seconds_ago) * 1000), {"role": "assistant", "time": block})


def _gone_pid():
    """A pid that has certainly exited: a child we started and reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _report(db, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("quiet", 120)
    return alive.session_report(SESSION, db=db, **kw)


# ---- the three states ------------------------------------------------------------------

def test_a_recent_part_is_working(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(5)])
    report = _report(db, engine_pid=os.getpid())
    assert report["line"].startswith("WORKING  ")
    assert "last activity 5s ago (tool read)" in report["line"]


def test_an_old_part_with_a_live_pid_is_quiet(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(1000)])
    report = _report(db, engine_pid=os.getpid())
    assert report["line"] == "QUIET    no activity for 1000s, but the process is alive"


def test_a_turn_older_than_the_engine_is_dead(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(4000)], messages=[_assistant(4000)])
    report = _report(db, engine_start=NOW - 3600, engine_pid=os.getpid())
    assert report["line"] == "DEAD     started before this engine; it will never finish - resend"


def test_a_gone_pid_is_dead(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(5)])
    report = _report(db, engine_pid=_gone_pid())
    assert report["line"] == "DEAD     its process is gone; it will never finish - resend"


def test_a_finished_turn_is_not_dead_for_being_old(tmp_path):
    # the crash case was an UNFINISHED turn. A turn that completed long before this engine is
    # simply a chat at rest, not something that will never finish.
    db = _db(tmp_path / "o.db", parts=[_part(4000)], messages=[_assistant(4000, completed=True)])
    report = _report(db, engine_start=NOW - 3600, engine_pid=os.getpid())
    assert report["line"].startswith("QUIET  ")


def test_no_parts_yet_is_quiet_with_a_live_engine(tmp_path):
    db = _db(tmp_path / "o.db")
    report = _report(db, engine_pid=os.getpid())
    assert report["line"] == "QUIET    no activity yet, but the process is alive"


def test_a_missing_database_does_not_crash(tmp_path):
    report = _report(tmp_path / "nothing.db", engine_pid=os.getpid())
    assert report["line"].startswith("QUIET  ")


def test_the_quiet_threshold_is_honoured(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(200)])
    assert _report(db, engine_pid=os.getpid(), quiet=120)["line"].startswith("QUIET")
    assert _report(db, engine_pid=os.getpid(), quiet=600)["line"].startswith("WORKING")


def test_quiet_s_reads_limits_json():
    assert alive.quiet_s() == 120          # crew/limits.json, alive.quiet_s


def test_process_facts_of_no_pid():
    assert alive.process_facts(None, NOW) == (None, None)
    assert alive.process_facts(0, NOW) == (None, None)


def test_milliseconds_and_seconds_are_told_apart():
    assert alive._seconds(1_793_233_214_888) == 1_793_233_214.888
    assert alive._seconds(1_793_233_214) == 1_793_233_214.0
    assert alive._seconds(None) is None


# ---- builds ----------------------------------------------------------------------------

def _build(folder, state="running", pid=None, started_ago=5, age_s=5):
    folder.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - started_ago))
    (folder / "status.json").write_text(json.dumps(
        {"state": state, "pid": pid, "started": started, "branch": "pa/x"}), encoding="utf-8")
    log = folder / "opencode.stderr.txt"
    log.write_text("running\n", encoding="utf-8")
    stamp = time.time() - age_s
    os.utime(log, (stamp, stamp))
    os.utime(folder / "status.json", (stamp, stamp))
    return folder


def test_a_running_build_with_a_live_pid_is_working(tmp_path):
    folder = _build(tmp_path / "b", state="running", pid=os.getpid(), age_s=3)
    line = alive.build_report(folder)["line"]
    assert line.startswith("WORKING  ")
    assert "last activity" in line


def test_a_running_build_with_a_quiet_log_is_quiet(tmp_path):
    folder = _build(tmp_path / "b", state="running", pid=os.getpid(), started_ago=900, age_s=900)
    line = alive.build_report(folder)["line"]
    assert line.startswith("QUIET  ")


def test_a_running_build_with_a_gone_pid_is_dead(tmp_path):
    folder = _build(tmp_path / "b", state="running", pid=_gone_pid(), age_s=3)
    assert alive.build_report(folder)["line"] == \
        "DEAD     its process is gone; it will never finish - resend"


def test_a_finished_build_is_not_dead(tmp_path):
    folder = _build(tmp_path / "b", state="finished", pid=_gone_pid(), age_s=900)
    line = alive.build_report(folder)["line"]
    assert line.startswith("QUIET  ")
    assert "not running" in line and "finished" in line


def test_a_build_with_no_status_is_dead(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    report = alive.build_report(folder)
    assert report["line"].startswith("DEAD  ")
    assert report["exists"] is False


# ---- the CLI ---------------------------------------------------------------------------

def _run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(REPO))


def test_the_cli_prints_one_line_for_a_session(tmp_path):
    # the CLI reads the REAL clock, so this part is five seconds before now, not before NOW
    db = _db(tmp_path / "o.db", parts=[_part_at(time.time() - 5)])
    run = _run("--session", SESSION, "--db", str(db), "--engine-start", str(NOW - 3600))
    assert run.returncode == 0, run.stderr
    assert len(run.stdout.strip().splitlines()) == 1
    assert run.stdout.startswith("WORKING  ")


def test_the_cli_reports_a_missing_build_with_exit_one(tmp_path):
    run = _run("--build", str(tmp_path / "nope"))
    assert run.returncode == 1
    assert run.stdout.startswith("DEAD  ")


def test_the_cli_needs_a_target():
    run = _run()
    assert run.returncode != 0
