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


def _text_part(seconds_ago, text):
    """A text part - the shape the engine's max-steps notice answer has."""
    return _part(seconds_ago, {"type": "text", "text": text})


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


# ---- the step ceiling (STEPS) ----------------------------------------------------------

def _turn_messages(count, agent="Gordon-assign"):
    """A user turn, then `count` assistant messages - the turn's step count, oldest first."""
    base = NOW - 3600
    out = [(base, {"role": "user", "agent": agent, "time": {"created": int(base * 1000)}})]
    for i in range(count):
        created = base + 1 + i
        out.append((created, {"role": "assistant", "agent": agent,
                              "time": {"created": int(created * 1000)}}))
    return out


def test_a_turn_at_the_step_ceiling_is_steps(tmp_path):
    # Gordon's ceiling is 60 (personnel.json); the real turn that surfaced this had 61 and 78 tools
    db = _db(tmp_path / "o.db", parts=[_part(2)], messages=_turn_messages(60))
    report = _report(db, engine_pid=os.getpid(), engine_start=NOW - 7200)
    assert report["steps"] is True
    assert report["line"].startswith("STEPS    ")
    assert "step ceiling" in report["line"]


def test_a_turn_under_the_ceiling_is_not_steps(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(2)], messages=_turn_messages(59))
    report = _report(db, engine_pid=os.getpid(), engine_start=NOW - 7200)
    assert report["steps"] is False
    assert not report["line"].startswith("STEPS")


def test_a_max_steps_notice_part_is_steps(tmp_path):
    db = _db(tmp_path / "o.db",
             parts=[_text_part(2, "CRITICAL - MAXIMUM STEPS REACHED\n\nI reached the ceiling.")])
    report = _report(db, engine_pid=os.getpid(), engine_start=NOW - 7200)
    assert report["steps"] is True
    assert report["line"].startswith("STEPS    ")


def test_step_limit_reads_personnel():
    assert alive.step_limit("Gordon-assign") == 60
    assert alive.step_limit("Gordon") == 60
    assert alive.step_limit("") is None
    assert alive.step_limit("Nobody-assign") is None


def test_turn_steps_counts_only_the_newest_turn(tmp_path):
    # an older turn's assistants must not be added to the newest turn's count
    older = _turn_messages(30)
    newer = [(NOW - 100, {"role": "user", "agent": "Gordon-assign", "time": {"created": 1}}),
             (NOW - 90, {"role": "assistant", "agent": "Gordon-assign", "time": {"created": 2}}),
             (NOW - 80, {"role": "assistant", "agent": "Gordon-assign", "time": {"created": 3}})]
    db = _db(tmp_path / "o.db", parts=[_part(2)], messages=older + newer)
    report = _report(db, engine_pid=os.getpid(), engine_start=NOW - 7200)
    assert report["steps"] is False, "only the newest turn's steps count"


def test_a_finished_turn_reads_quiet_not_working(tmp_path):
    # The whole question is "is it still processing?". A turn that ENDED must not read WORKING
    # for two minutes just because its last part is recent (found in review, 2026-10-28).
    db = _db(tmp_path / "o.db", parts=[_part(2)], messages=[_assistant(120, completed=True)])
    report = _report(db, engine_pid=os.getpid(), engine_start=NOW - 7200)
    assert report["turn_over"] is True
    assert report["line"].startswith("QUIET  ")
    assert "no activity for" in report["line"]


def test_an_unfinished_turn_with_a_recent_part_is_working(tmp_path):
    db = _db(tmp_path / "o.db", parts=[_part(2)], messages=[_assistant(120)])
    report = _report(db, engine_pid=os.getpid(), engine_start=NOW - 7200)
    assert report["turn_over"] is False
    assert report["line"].startswith("WORKING  ")


def test_a_dead_turn_is_still_dead_even_though_it_is_not_in_flight(tmp_path):
    # the crash case: an unfinished turn plus an engine that restarted after it. The engine's
    # session status is IDLE here, which is exactly why the window must not gate the check on
    # "is a turn in flight" - it would never show the one state this feature exists for.
    db = _db(tmp_path / "o.db", parts=[_part(4000)], messages=[_assistant(4000)])
    report = _report(db, engine_start=NOW - 3600, engine_pid=os.getpid())
    assert report["turn_over"] is False
    assert report["line"].startswith("DEAD  ")


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
