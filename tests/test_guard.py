"""crew/guard.py: limits merge, progress vs failing, the live kill, and that no runner can
start opencode.exe without it (no model involved anywhere)."""
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from crew import guard

REPO = Path(__file__).resolve().parents[1]


def _db(path, parts):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table part (id text, data text)")
    con.executemany("insert into part values (?, ?)", [(str(i), json.dumps(p)) for i, p in enumerate(parts)])
    con.commit()
    con.close()


STEP = {"type": "step-finish", "tokens": {"input": 1000, "output": 100, "cache": {"read": 50000}}}
ERR = {"type": "tool", "tool": "bash", "state": {"status": "error", "error": "Error: refused"}}
READ = {"type": "tool", "tool": "read", "state": {"status": "completed", "output": "x"}}
EDIT = {"type": "tool", "tool": "edit", "state": {"status": "completed"}}
TEST_OK = {"type": "tool", "tool": "bash", "state": {"status": "completed", "input": {
    "command": "cargo test -p x"}, "metadata": {"exit": 0}}}
TEST_BAD = {"type": "tool", "tool": "bash", "state": {"status": "completed", "input": {
    "command": "cargo test -p x"}, "metadata": {"exit": 101}}}
LIM = {"budget_tokens": 200000, "stall_steps": 5, "stall_steps_over_budget": 2,
       "ceiling_tokens": 10 ** 9, "max_same_error": 3, "progress_commands": ["cargo test"]}


def test_tightest_limit_wins(tmp_path):
    f = tmp_path / "limits.json"
    f.write_text(json.dumps({"defaults": {"ceiling_steps": 40, "poll_seconds": 15, "progress_commands": ["a"]},
                             "jobs": {"fix": {"ceiling_steps": 15}},
                             "members": {"Kimi": {"ceiling_steps": 20, "poll_seconds": 3,
                                                  "progress_commands": ["b"]}}}))
    assert guard.limits("Kimi", "fix", f) == {"ceiling_steps": 15, "poll_seconds": 3, "progress_commands": ["b"]}
    assert guard.limits("Gordon", "build", f)["ceiling_steps"] == 40


def test_the_real_limits_file_loads():
    lim = guard.limits("Kimi", "build")
    assert lim["stall_steps"] > 0 and lim["budget_tokens"] < lim["ceiling_tokens"]


def test_progress_is_edits_and_passing_tests_not_reading():
    c = guard.count([STEP, READ, STEP, EDIT, STEP, TEST_BAD, STEP, TEST_OK, STEP, READ], ["cargo test"])
    assert c["progress"] == 2 and c["since_progress"] == 1


def test_working_job_may_pass_the_budget():
    parts = [STEP, EDIT] * 6                       # 306k tokens, progress every step
    assert guard.count(parts)["tokens"] > LIM["budget_tokens"]
    assert guard.replay(parts, LIM) == (None, "")


def test_job_only_reading_is_stopped():
    i, why = guard.replay([STEP, READ] * 10, LIM)
    assert "no progress" in why and guard.count([STEP, READ] * 10)["steps"] > 5


def test_past_budget_the_stall_allowance_shrinks():
    parts = [STEP, EDIT] * 4 + [STEP, READ] * 3    # over budget, then 3 steps reading
    assert "past the token budget" in guard.replay(parts, LIM)[1]
    assert guard.replay(parts, {**LIM, "budget_tokens": 10 ** 9}) == (None, "")


def test_repeating_a_failure_is_stopped_even_while_editing():
    i, why = guard.replay([STEP, EDIT, ERR] * 3, LIM)
    assert why.startswith("failing") and "repeats of the same error" in why


def test_next_round_only_on_improvement():
    assert guard.next_round([0]) and guard.next_round([1, 2])
    assert not guard.next_round([2, 2]) and not guard.next_round([2, 1])


def test_live_job_is_killed(tmp_path):
    _db(guard.db_path(tmp_path), [STEP, READ] * 10)
    argv = [sys.executable, "-c", "import time; time.sleep(60)"]
    t0 = time.time()
    out, err, code, why = guard.launch(argv, tmp_path, {}, tmp_path, "r1",
                                       {**LIM, "poll_seconds": 2}, t0)
    assert "no progress" in why and time.time() - t0 < 20
    assert json.loads((tmp_path / "guard.json").read_text())["stopped"] == why


def test_job_inside_limits_runs_to_the_end(tmp_path):
    _db(guard.db_path(tmp_path), [STEP, EDIT])
    out, err, code, why = guard.launch([sys.executable, "-c", "print('hi')"], tmp_path, {},
                                       tmp_path, "r1", {**LIM, "poll_seconds": 2}, time.time())
    assert (why, code, out.strip()) == ("", 0, "hi")


def test_no_runner_starts_opencode_without_the_guard():
    """The guard cannot be forgotten: only crew/guard.py may Popen/run the opencode binary."""
    offenders = []
    for f in (REPO / "crew").rglob("*.py"):
        if f.name == "guard.py":
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"subprocess\.(Popen|run|call|check_output)\((?P<arg>[^)\n]{0,80})", src):
            if "OPENCODE" in m.group("arg") or "opencode" in m.group("arg").lower():
                offenders.append(f"{f.relative_to(REPO)}: {m.group(0)}")
        for m in re.finditer(r"(\w+)\s*=\s*\[OPENCODE\b", src):
            name = m.group(1)
            if re.search(rf"subprocess\.\w+\(\s*{name}\b", src):
                offenders.append(f"{f.relative_to(REPO)}: launches {name} directly")
    assert not offenders, "start OpenCode with crew.guard.launch():\n" + "\n".join(offenders)
