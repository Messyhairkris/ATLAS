"""crew/runners/chat_compact.py - the ready built chat compact (Kris, 2026-10-27).

The live engine database is never touched: every test builds its own SQLite file with OpenCode's
REAL shape - `message(id, session_id, data)` and `part(id, message_id, session_id, data)`, where
the JSON carries only the row's own fields and the ids are COLUMNS (measured 2026-10-28). The
summarize call is injected, so no model is ever asked to spend a request. What is under test is
the ORDER - the backup is written before the engine is called, and a failed summarize leaves the
chat exactly as it was.
"""

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "crew" / "runners" / "chat_compact.py"
SESSION = "ses_compact_test"

# (id column, session_id column, the row's JSON) - the JSON has no id and no sessionID, exactly
# as OpenCode stores it.
MESSAGES = [
    ("msg_u", SESSION, {"role": "user", "time": {"created": 1}}),
    ("msg_a", SESSION, {"role": "assistant", "modelID": "hf:test-model",
                        "time": {"created": 2, "completed": 3},
                        "tokens": {"input": 702, "output": 10, "cache": {"read": 115200}}}),
]
# (id, message_id, session_id, JSON) - a part's own JSON is only type/text/state.
PARTS = [
    ("prt_1", "msg_u", SESSION, {"type": "text", "text": "compact this chat"}),
    ("prt_2", "msg_a", SESSION, {"type": "reasoning", "text": "thinking"}),
    ("prt_3", "msg_a", SESSION, {"type": "text", "text": "done"}),
    ("prt_4", "msg_a", SESSION, {"type": "tool", "tool": "read",
                                 "state": {"input": {"file": "a.txt"}, "output": "contents"}}),
]
BEFORE = 115902


def _load():
    """The tool's own module (the CLI is exercised as a subprocess separately)."""
    spec = importlib.util.spec_from_file_location("chat_compact", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chat_compact = _load()


def _db(path, messages=MESSAGES, parts=PARTS):
    """OpenCode's real two-table shape; the ids are columns, the JSON is only the row's fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table message (id text, session_id text, data text)")
    con.execute("create table part (id text, message_id text, session_id text, data text)")
    con.executemany("insert into message values (?, ?, ?)",
                    [(i, s, json.dumps(d)) for i, s, d in messages])
    con.executemany("insert into part values (?, ?, ?, ?)",
                    [(i, m, s, json.dumps(d)) for i, m, s, d in parts])
    con.commit()
    con.close()
    return path


def test_abbrev_shows_the_header_style():
    assert chat_compact.abbrev(950) == "950"
    assert chat_compact.abbrev(115902) == "116k"
    assert chat_compact.abbrev(128_000) == "128k"
    assert chat_compact.abbrev(1_048_576) == "1.0M"


def test_the_backup_is_written_before_summarize_is_called(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    seen = {}

    def post(url, path, body, secret, timeout):
        seen["messages_before"] = (dest / "T_messages.jsonl").is_file()
        seen["path"] = path
        seen["body"] = body
        return "true"

    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", model="hf:test-model",
                               db=db, dest=dest, apply=True, post=post, stamp="T",
                               wait=5, poll=0.01)

    assert seen["messages_before"] is True, "the backup must exist before the engine is called"
    assert seen["path"] == f"/session/{SESSION}/summarize"
    assert seen["body"] == {"providerID": "synthetic", "modelID": "hf:test-model", "auto": False}
    assert out["summarized"] is True
    assert out["before"] == BEFORE


def test_a_failed_summarize_leaves_the_chat_as_it_was(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"

    def post(*_a, **_k):
        raise RuntimeError("the engine said no")

    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", model="hf:test-model",
                               db=db, dest=dest, apply=True, post=post, stamp="T",
                               wait=5, poll=0.01)

    assert out["summarized"] is False
    assert out["after"] == out["before"], "a failed compact must not change the chat"
    assert "engine said no" in out["why"]
    assert (dest / "T_messages.jsonl").is_file(), "the backup is kept even when the summarize fails"
    assert chat_compact.load_messages(db, SESSION)  # the database is untouched


def test_without_apply_it_is_a_dry_run_and_never_calls_the_engine(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    calls = []

    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", model="hf:test-model",
                               db=db, dest=dest, apply=False,
                               post=lambda *a: calls.append(a), stamp="T")

    assert calls == []
    assert out["summarized"] is False
    assert out["applied"] is False
    assert "dry run" in out["why"]
    assert (dest / "T_messages.jsonl").is_file(), "even a dry run leaves a backup"


def _add_compaction_part(db, message_id="m_engine"):
    """Record a compaction the engine wrote - what the "late" check looks for."""
    con = sqlite3.connect(db)
    con.execute("insert into part values (?, ?, ?, ?)",
                ("p_cmp", message_id, SESSION, json.dumps({"type": "compaction", "auto": False})))
    con.commit()
    con.close()


def test_a_timeout_is_not_proof_of_failure(tmp_path):
    # measured 2026-10-28: the engine completed at 639,952 ms while the client had given up at
    # 540 s, and the chat WAS compacted. A failed call must not be reported as a failure if the
    # engine left a compaction behind.
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"

    def post(*_a):
        _add_compaction_part(db)
        raise TimeoutError("gave up waiting")

    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", model="hf:test-model",
                               db=db, dest=dest, apply=True, post=post, stamp="T",
                               wait=5, poll=0.01)
    assert out["summarized"] is True, "the engine did the work, whatever the client saw"
    assert out["late"] is True
    assert out["why"] == ""
    assert "(late" in chat_compact.line_for(out)


def test_a_failure_with_no_new_compaction_is_a_real_failure(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"

    def post(*_a):
        raise TimeoutError("gave up waiting")

    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", model="hf:test-model",
                               db=db, dest=dest, apply=True, post=post, stamp="T",
                               wait=5, poll=0.01)
    assert out["summarized"] is False
    assert not out.get("late")
    assert out["after"] == out["before"]


def test_the_secret_reaches_the_request(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    seen = {}

    def post(url, path, body, secret, timeout):
        seen["secret"] = secret
        return "true"

    chat_compact.compact(SESSION, url="http://127.0.0.1:9", secret="s3cret", model="hf:test-model",
                         db=db, dest=dest, apply=True, post=post, stamp="T", wait=5, poll=0.01)
    assert seen["secret"] == "s3cret"


def test_the_secret_can_be_read_from_stdin(tmp_path):
    # a command line is visible to every process listing, so the window passes the password on
    # the pipe; this proves the flag reads stdin and does not block or fall back to argv
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    run = subprocess.run(
        [sys.executable, str(TOOL), "--session", SESSION, "--db", str(db), "--dir", str(dest),
         "--secret-stdin"],
        input="from-the-pipe\n", capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=str(REPO), timeout=120)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().startswith("would compact"), run.stdout


def test_a_chat_with_no_recorded_model_is_not_summarized(tmp_path):
    db = _db(tmp_path / "opencode.db", messages=[("msg_u", SESSION, {"role": "user"})], parts=[])
    dest = tmp_path / "compact"
    calls = []

    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", db=db, dest=dest, apply=True,
                               post=lambda *a: calls.append(a), stamp="T")

    assert calls == []
    assert out["summarized"] is False
    assert "model" in out["why"]


def test_the_backup_holds_the_messages_the_database_and_the_summary_input(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    chat_compact.compact(SESSION, db=db, dest=dest, apply=False, stamp="T")

    lines = (dest / "T_messages.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["role"] == "assistant"      # the JSON is the row, id is a column
    assert (dest / "T_opencode.db").is_file()
    summary = (dest / "T_summary_input.md").read_text(encoding="utf-8")
    assert "## assistant" in summary and "compact this chat" in summary


def test_the_line_names_the_before_and_after_and_the_backup(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    out = chat_compact.compact(SESSION, url="http://127.0.0.1:9", model="hf:test-model",
                               db=db, dest=dest, apply=True, post=lambda *a: "true",
                               stamp="T", wait=5, poll=0.01)
    line = chat_compact.line_for(out)
    assert line.startswith("compacted 116k -> ")
    assert "backup saved to" in line and "compact" in line


def test_the_dry_run_line_says_would_compact(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    out = chat_compact.compact(SESSION, db=db, dest=dest, apply=False, stamp="T")
    assert chat_compact.line_for(out).startswith("would compact 116k")


def test_session_digest_maps_the_parts_to_the_summary_shape(tmp_path):
    db = _db(tmp_path / "opencode.db")
    digest = chat_compact.session_digest(db, SESSION)
    assert [d["role"] for d in digest] == ["user", "assistant"]
    assert digest[0]["text"] == "compact this chat"
    assert digest[1]["text"] == "done"
    assert digest[1]["reasoning"] == "thinking"
    assert digest[1]["tools"] == [{"name": "read", "input": {"file": "a.txt"}}]
    assert digest[1]["results"] == [{"name": "read", "output": "contents"}]


def test_the_digest_joins_parts_to_their_message_by_the_column_not_the_json(tmp_path):
    """Regression, 2026-10-28: a part's message is the `message_id` COLUMN.

    The old code grouped by a JSON `messageID`, which does not exist on a real row: every part
    landed in one bucket keyed "", and the digest then rescanned all 3571 of them once per
    message. This pins the column join AND that a message never sees another's parts.
    """
    db = _db(
        tmp_path / "opencode.db",
        messages=[("m1", SESSION, {"role": "user", "time": {"created": 1}}),
                  ("m2", SESSION, {"role": "assistant", "time": {"created": 2, "completed": 3},
                                   "tokens": {"input": 1, "cache": {"read": 1}}})],
        parts=[("p1", "m1", SESSION, {"type": "text", "text": "first"}),
               ("p2", "m2", SESSION, {"type": "text", "text": "second"}),
               ("p3", "m2", SESSION, {"type": "text", "text": "third"})])
    digest = chat_compact.session_digest(db, SESSION)
    assert [d["text"] for d in digest] == ["first", "second\nthird"]


def test_the_digest_stays_linear_with_many_messages_and_parts(tmp_path):
    # 200 messages x 20 parts: a JSON-keyed regroup would funnel 4000 parts into one bucket and
    # rescan it 200 times. Linear, each message reads only its own 20.
    messages = [(f"m{i}", SESSION, {"role": "assistant", "time": {"created": i, "completed": i + 1},
                                    "tokens": {"input": 1, "cache": {"read": 1}}}) for i in range(200)]
    parts = [(f"p{i}_{j}", f"m{i}", SESSION, {"type": "text", "text": f"t{i}"})
             for i in range(200) for j in range(20)]
    db = _db(tmp_path / "opencode.db", messages=messages, parts=parts)
    digest = chat_compact.session_digest(db, SESSION)
    assert len(digest) == 200
    assert digest[7]["text"] == "\n".join(["t7"] * 20)      # only its own parts, no leakage


def test_model_of_reads_the_newest_assistant_model(tmp_path):
    db = _db(tmp_path / "opencode.db")
    assert chat_compact.model_of(chat_compact.load_messages(db, SESSION)) == "hf:test-model"
    empty = _db(tmp_path / "user-only.db",
                messages=[("msg_u", SESSION, {"role": "user"})], parts=[])
    assert chat_compact.model_of(chat_compact.load_messages(empty, SESSION)) == ""


def test_a_missing_database_is_handled(tmp_path):
    dest = tmp_path / "compact"
    out = chat_compact.compact(SESSION, db=tmp_path / "nothing.db", dest=dest, apply=False, stamp="T")
    assert out["before"] == 0
    assert (dest / "T_messages.jsonl").is_file()


def test_summarize_reports_a_post_failure():
    def post(*_a):
        raise ValueError("boom")

    assert chat_compact.summarize("http://x", SESSION, "synthetic", "m", post=post)["ok"] is False


def test_the_cli_dry_run_prints_one_line_and_exits_zero(tmp_path):
    db = _db(tmp_path / "opencode.db")
    dest = tmp_path / "compact"
    run = subprocess.run(
        [sys.executable, str(TOOL), "--session", SESSION, "--db", str(db), "--dir", str(dest)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO))
    assert run.returncode == 0, run.stderr
    assert len(run.stdout.strip().splitlines()) == 1, run.stdout
    assert run.stdout.strip().startswith("would compact 116k")
    assert "backup saved to" in run.stdout
