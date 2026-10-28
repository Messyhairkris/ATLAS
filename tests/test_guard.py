"""crew/guard.py: limits merge, progress vs failing, the live kill, and that no runner can
start opencode.exe without it (no model involved anywhere)."""
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

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


def test_a_member_may_loosen_a_working_setting_but_never_a_ceiling(tmp_path):
    f = tmp_path / "limits.json"
    f.write_text(json.dumps({"defaults": {"budget_tokens": 100, "ceiling_tokens": 500},
                             "members": {"Gordon": {"budget_tokens": 300, "ceiling_tokens": 900}}}))
    lim = guard.limits("Gordon", "build", f)
    assert (lim["budget_tokens"], lim["ceiling_tokens"]) == (300, 500)


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


def test_min_free_gb_is_a_floor_the_highest_wins(tmp_path):
    f = tmp_path / "limits.json"
    f.write_text(json.dumps({"defaults": {"min_free_gb": 5},
                             "jobs": {"build": {"min_free_gb": 10}},
                             "members": {"Kimi": {"min_free_gb": 2}}}))
    assert guard.limits("Kimi", "build", f)["min_free_gb"] == 10   # job 10 > default 5 > member 2
    assert guard.limits("Hoss", "build", f)["min_free_gb"] == 10   # a looser member cannot lower it
    assert guard.limits("Kimi", "fix", f)["min_free_gb"] == 5      # no job override: default stands


def test_free_gb_reads_the_drive_of_the_nearest_existing_parent(tmp_path):
    assert guard.free_gb(tmp_path / "not" / "there" / "yet") > 0


def test_disk_reason_only_when_below_the_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda p: SimpleNamespace(free=3 * 1024 ** 3))
    assert guard.disk_reason({"min_free_gb": 5}, tmp_path).startswith("disk: 3.0 GB free")
    assert guard.disk_reason({"min_free_gb": 2}, tmp_path) == ""
    assert guard.disk_reason({}, tmp_path) == ""                   # unset: never refuses


def test_launch_refuses_when_the_drive_is_too_full(tmp_path, monkeypatch):
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda p: SimpleNamespace(free=1024 ** 3))
    marker = tmp_path / "ran.txt"
    out, err, code, why = guard.launch(
        [sys.executable, "-c", f"open(r'{marker}', 'w').write('x')"],
        tmp_path, {}, tmp_path, "r1", {**LIM, "min_free_gb": 5}, time.time())
    assert why.startswith("disk:") and code is None
    assert not marker.exists()                     # the job never started
    assert json.loads((tmp_path / "guard.json").read_text())["stopped"] == why


def test_watch_stops_a_running_job_when_the_drive_fills(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake(path):
        calls["n"] += 1
        return SimpleNamespace(free=(100 if calls["n"] == 1 else 1) * 1024 ** 3)

    monkeypatch.setattr(guard.shutil, "disk_usage", fake)
    _db(guard.db_path(tmp_path), [STEP, EDIT])     # otherwise a perfectly healthy, progressing job
    t0 = time.time()
    out, err, code, why = guard.launch(
        [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, {}, tmp_path, "r1",
        {**LIM, "min_free_gb": 5, "poll_seconds": 2}, t0)
    assert why.startswith("disk:") and time.time() - t0 < 20

# Starts OpenCode without launch(), on purpose, with the reason. Anything not listed fails.
KNOWN_UNGUARDED = {
    # The window's chat server: one long-lived `opencode serve` for every chat, so killing
    # it would end all chats. Chats are capped per message by personnel steps; a per-session
    # guard (abort one session over the server's API) is still to be built (2026-10-26).
    "pa_engine.py": "chat server, per-message steps only",
    # The interactive OpenCode window Kris opens and drives himself, message by message.
    "pa_session.py": "interactive, driven by Kris",
}


def test_no_runner_starts_opencode_without_the_guard():
    """The guard cannot be forgotten: only crew/guard.py may Popen/run the opencode binary."""
    offenders = []
    for f in (REPO / "crew").rglob("*.py"):
        if f.name == "guard.py" or f.name in KNOWN_UNGUARDED:
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        if "_opencode_exe(" in src and "def _opencode_exe" not in src:
            offenders.append(f"{f.relative_to(REPO)}: finds the opencode binary itself")
        for m in re.finditer(r"subprocess\.(Popen|run|call|check_output)\((?P<arg>[^)\n]{0,80})", src):
            if "OPENCODE" in m.group("arg") or "opencode" in m.group("arg").lower():
                offenders.append(f"{f.relative_to(REPO)}: {m.group(0)}")
        for m in re.finditer(r"(\w+)\s*=\s*\[(?:OPENCODE|exe)\b", src):
            name = m.group(1)
            if re.search(rf"subprocess\.\w+\(\s*{name}\b", src):
                offenders.append(f"{f.relative_to(REPO)}: launches {name} directly")
    assert not offenders, "start OpenCode with crew.guard.launch():\n" + "\n".join(offenders)


def test_the_opening_read_gets_its_own_allowance():
    lim = {**LIM, "stall_steps_opening": 8, "budget_tokens": 10 ** 9}   # stay under budget
    assert guard.replay([STEP, READ] * 7, lim) == (None, "")          # 7 reads, no change yet
    assert "no progress" in guard.replay([STEP, READ] * 9, lim)[1]
    after = [STEP, EDIT] + [STEP, READ] * 6                              # after a change: 5 again
    assert "no progress" in guard.replay(after, lim)[1]


def test_a_cheap_member_gets_proportionally_more_tokens():
    parts = [STEP, EDIT] * 4                                 # 204,400 raw tokens
    lim = {"budget_tokens": 10 ** 9, "ceiling_tokens": 150000}
    assert "ceiling" in guard.verdict(guard.count(parts), lim)
    assert guard.verdict(guard.count(parts), {**lim, "cost_weight": 0.5}) == ""


def test_a_job_never_inherits_the_chat_engines_password(tmp_path, monkeypatch):
    seen = {}

    class Done:
        returncode, pid = 0, 1
        def poll(self): return 0
        def wait(self, timeout=None): return 0

    def popen(argv, **kw):
        seen.update(kw["env"])
        return Done()
    monkeypatch.setattr(guard.subprocess, "Popen", popen)
    env = {"PATH": "x", "OPENCODE_SERVER_PASSWORD": "s", "OPENCODE_PERMISSION": "{}"}
    guard.launch(["opencode"], tmp_path, env, tmp_path / "job", "r", {"min_free_gb": 0}, 0)
    assert "OPENCODE_SERVER_PASSWORD" not in seen and "OPENCODE_PERMISSION" not in seen
    assert seen["PATH"] == "x" and seen["XDG_DATA_HOME"].endswith("data")
