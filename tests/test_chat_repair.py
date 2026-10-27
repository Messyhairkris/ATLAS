"""crew/runners/chat_repair.py: the self-repair step for a chat that fails on a fixable error.

The live engine database is never touched here: every test builds its own SQLite file with the
same shape as OpenCode's (`part(id text, data text)`, as tests/test_guard.py builds it) and runs
the tool against it as a subprocess, the way the window will. The live session is repaired by
hand, never by a test (`--session ses_e8fdcc727ffe46Y7X7MqSenCyX --error ... --apply`).
"""

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "crew" / "runners" / "chat_repair.py"
REPAIRS = REPO / "crew" / "chat_repairs.json"

BMP_ERROR = "Image type image/x-ms-bmp not supported"
SESSION = "ses_test_bmp"
OTHER = "ses_other_chat"

BAD_PART = {
    "type": "file", "sessionID": SESSION, "messageID": "msg_u1", "filename": "changes.bmp",
    "mime": "image/x-ms-bmp", "url": "data:image/x-ms-bmp;base64,Qk1GMAAAAAAA",
}
FIXED_PART = {
    "type": "file", "sessionID": SESSION, "messageID": "msg_u1", "filename": "changes.bmp",
    "mime": "image/bmp", "url": "data:image/bmp;base64,Qk1GMAAAAAAA",
}
TEXT_PART = {"type": "text", "sessionID": SESSION, "messageID": "msg_u1", "text": "look at this"}


def _load():
    """The tool's own module, for the matching rules (the CLI is tested as a subprocess)."""
    spec = importlib.util.spec_from_file_location("chat_repair", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chat_repair = _load()


def _db(path, parts, messages=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table part (id text, data text)")
    con.execute("create table message (id text, data text)")
    con.executemany("insert into part values (?, ?)", [(str(i), json.dumps(p)) for i, p in enumerate(parts)])
    con.executemany("insert into message values (?, ?)", [(str(i), json.dumps(m)) for i, m in enumerate(messages)])
    con.commit()
    con.close()
    return path


def _rows(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("select id, data from part order by rowid").fetchall()
    finally:
        con.close()


def _run(db, log, *args):
    return subprocess.run(
        [sys.executable, str(TOOL), "--db", str(db), "--log", str(log), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO))


def _log_lines(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_a_bad_image_is_repaired_and_logged(tmp_path):
    db = _db(tmp_path / "opencode.db", [TEXT_PART, BAD_PART])
    log = tmp_path / "chat_repairs.jsonl"
    done = _run(db, log, "--session", SESSION, "--error", BMP_ERROR, "--apply")
    assert done.stdout.strip() == "repaired", done.stderr

    rows = _rows(db)
    assert json.loads(rows[1][1]) == FIXED_PART, "the mime AND the data: URL prefix are rewritten"
    assert json.loads(rows[0][1]) == TEXT_PART, "nothing else is touched"

    lines = _log_lines(log)
    assert len(lines) == 1 and lines[0]["result"] == "repaired"
    assert lines[0]["pattern"] == "bmp-mime" and lines[0]["applied"] is True

    again = _run(db, log, "--session", SESSION, "--error", BMP_ERROR, "--apply")
    assert again.stdout.strip() == "no-match", "a second run finds nothing to do"
    assert len(_log_lines(log)) == 2 and _log_lines(log)[1]["result"] == "no-match"


def test_a_message_that_only_mentions_the_type_keeps_its_words(tmp_path):
    prose = {"type": "text", "sessionID": SESSION, "messageID": "msg_a1",
             "text": "OpenCode labels the .bmp image/x-ms-bmp and Synthetic refuses it"}
    db = _db(tmp_path / "opencode.db", [prose, BAD_PART])
    log = tmp_path / "log.jsonl"
    assert _run(db, log, "--session", SESSION, "--error", BMP_ERROR, "--apply").stdout.strip() == "repaired"
    rows = _rows(db)
    assert json.loads(rows[0][1]) == prose, "a message that talks about the type keeps its words"
    assert json.loads(rows[1][1]) == FIXED_PART

    only_prose = _db(tmp_path / "prose.db", [prose])
    log2 = tmp_path / "log2.jsonl"
    done = _run(only_prose, log2, "--session", SESSION, "--error", BMP_ERROR, "--apply")
    assert done.stdout.strip() == "no-match", "prose alone is not an image to repair"
    assert json.loads(_rows(only_prose)[0][1]) == prose


def test_another_chat_is_never_touched(tmp_path):
    other = dict(BAD_PART, sessionID=OTHER)
    db = _db(tmp_path / "opencode.db", [other])
    log = tmp_path / "log.jsonl"
    done = _run(db, log, "--session", SESSION, "--error", BMP_ERROR, "--apply")
    assert done.stdout.strip() == "no-match"
    assert json.loads(_rows(db)[0][1]) == other, "a part of another session keeps its bytes"

    mine = _db(tmp_path / "two.db", [other, BAD_PART])
    log2 = tmp_path / "log2.jsonl"
    assert _run(mine, log2, "--session", SESSION, "--error", BMP_ERROR, "--apply").stdout.strip() == "repaired"
    rows = _rows(mine)
    assert json.loads(rows[0][1]) == other and json.loads(rows[1][1]) == FIXED_PART


def test_an_unknown_error_changes_nothing(tmp_path):
    db = _db(tmp_path / "opencode.db", [BAD_PART])
    log = tmp_path / "log.jsonl"
    before = _rows(db)
    done = _run(db, log, "--session", SESSION, "--error", "the tool crashed: no such file", "--apply")
    assert done.stdout.strip() == "no-match"
    assert _rows(db) == before, "an unknown error writes nothing"
    assert _log_lines(log)[0]["pattern"] == "" and _log_lines(log)[0]["result"] == "no-match"


def test_a_dry_run_writes_nothing(tmp_path):
    db = _db(tmp_path / "opencode.db", [BAD_PART])
    log = tmp_path / "log.jsonl"
    before = _rows(db)
    done = _run(db, log, "--session", SESSION, "--error", BMP_ERROR)
    assert done.stdout.strip() == "would-repair 1", done.stderr
    assert _rows(db) == before, "without --apply the database is untouched"
    assert _log_lines(log)[0]["applied"] is False


def test_a_locked_database_is_reported_not_waited_on(tmp_path):
    db = _db(tmp_path / "opencode.db", [BAD_PART])
    log = tmp_path / "log.jsonl"
    holder = sqlite3.connect(db)
    holder.execute("begin immediate")             # keeps the write lock; readers still pass
    try:
        before = _rows(db)
        done = _run(db, log, "--session", SESSION, "--error", BMP_ERROR, "--apply", "--timeout", "0.2")
        assert done.returncode == 0
        assert done.stdout.strip() == "no-match"
        assert "did not take the write" in done.stderr
        assert _rows(db) == before
    finally:
        holder.rollback()
        holder.close()


def test_the_error_as_a_json_body_still_matches(tmp_path):
    db = _db(tmp_path / "opencode.db", [BAD_PART])
    log = tmp_path / "log.jsonl"
    body = '{"error":{"statusCode":400,"responseBody":"{\\"message\\":\\"Image type image/x-ms-bmp not supported\\"}"}}'
    assert _run(db, log, "--session", SESSION, "--error", body, "--apply").stdout.strip() == "repaired"


def test_the_rules():
    entries = chat_repair.load_repairs(REPAIRS)
    assert entries, "crew/chat_repairs.json has at least one entry"
    for entry in entries:
        assert entry.get("name") and entry.get("_why"), entry
        assert entry["fixer"] in chat_repair.FIXERS, f"unknown fixer {entry['fixer']}"
    assert entries[0]["fixer"] == "rewrite_bmp_mime"
    assert chat_repair.match(entries, BMP_ERROR)["name"] == "bmp-mime"
    assert chat_repair.match(entries, f"Error:   {BMP_ERROR}  (HTTP 400)\n")["name"] == "bmp-mime"
    assert chat_repair.match(entries, "AI_APICallError Bad Request") is None
    assert chat_repair.match(entries, "") is None


def test_the_default_database_is_the_engines_own(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert chat_repair.db_default() == Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert chat_repair.db_default() == tmp_path / "opencode" / "opencode.db", "a build's own DB"
