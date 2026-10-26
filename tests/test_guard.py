"""crew/guard.py: limits merge tightest-wins, counting, and the live kill (no model involved)."""
import json
import sqlite3
import subprocess
import sys
import time

from crew import guard


def _db(path, parts):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table part (id text, data text)")
    con.executemany("insert into part values (?, ?)", [(str(i), json.dumps(p)) for i, p in enumerate(parts)])
    con.commit()
    con.close()


STEP = {"type": "step-finish", "tokens": {"input": 1000, "output": 100, "cache": {"read": 50000}}}
ERR = {"type": "tool", "tool": "bash", "state": {"status": "error", "error": "Error: refused"}}
OK = {"type": "tool", "tool": "read", "state": {"status": "completed", "output": "x"}}


def test_tightest_limit_wins(tmp_path):
    f = tmp_path / "limits.json"
    f.write_text(json.dumps({"defaults": {"max_steps": 40, "poll_seconds": 15},
                             "jobs": {"fix": {"max_steps": 15}},
                             "members": {"Kimi": {"max_steps": 20, "poll_seconds": 3}}}))
    assert guard.limits("Kimi", "fix", f) == {"max_steps": 15, "poll_seconds": 3}
    assert guard.limits("Kimi", "build", f)["max_steps"] == 20
    assert guard.limits("Gordon", "build", f)["max_steps"] == 40


def test_count_and_verdict():
    c = guard.count([STEP, ERR, ERR, OK, ERR, STEP])
    assert (c["steps"], c["tokens"], c["fresh_tokens"]) == (2, 102200, 2200)
    assert (c["tool_errors"], c["errors_in_a_row"], c["same_error"]) == (3, 2, 3)
    assert guard.verdict(c, {"max_steps": 5}) == ""
    assert "repeats of the same error" in guard.verdict(c, {"max_same_error": 3})
    assert "tokens" in guard.verdict(c, {"max_tokens": 100000})


def test_replay_finds_the_stop():
    i, why = guard.replay([STEP] * 10, {"max_steps": 4})
    assert i == 4 and "4 steps" in why


def test_live_job_is_killed(tmp_path):
    db = tmp_path / "opencode.db"
    _db(db, [STEP] * 5)
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    t0 = time.time()
    why = guard.run(p, db, {"max_steps": 3, "poll_seconds": 2}, t0)
    assert "steps" in why and p.poll() is not None and time.time() - t0 < 20


def test_job_inside_limits_runs_to_the_end(tmp_path):
    db = tmp_path / "opencode.db"
    _db(db, [STEP])
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    assert guard.run(p, db, {"max_steps": 3, "poll_seconds": 2}, time.time()) == ""
