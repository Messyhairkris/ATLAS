"""One repair step for a chat that died on a fixable error (Kris, 2026-10-27).

The chat engine (OpenCode) keeps a session's messages and parts in SQLite - the window's engine
uses `~/.local/share/opencode/opencode.db`, table `part(id, data)`, in WAL mode, and the guard
already reads it read-only while a PA runs. A part the model call cannot accept (today an image
labelled `image/x-ms-bmp`, which Synthetic refuses) stays in that history, so every later message
fails the same way and the chat is dead. This tool rewrites the part; the window then sends the
message again. It is called once per failed message, never on a good one.

    python crew/runners/chat_repair.py --session ses_x --error "..."            # dry run
    python crew/runners/chat_repair.py --session ses_x --error "..." --apply     # repair

Standard output is one line, the word the caller compares: `repaired`, `no-match`, or (dry run)
`would-repair N`. The detail goes to standard error and to one JSON line in
`runs/crew/chat_repairs.jsonl`. The patterns come from `crew/chat_repairs.json`, which Kris edits:
an unknown error is never guessed at.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.config import load_config  # noqa: E402

REPAIRS_FILE = REPO_ROOT / "crew" / "chat_repairs.json"

# The one pair this fixer knows. `-` is not in the base64 alphabet, so this string can never
# occur inside an inlined payload: replacing it is safe wherever it appears.
BAD_MIME = "image/x-ms-bmp"
GOOD_MIME = "image/bmp"

# Only a part's OWN image fields are rewritten: the mime field, and the data: URL it is inlined
# in. A part that merely mentions the type in its text is left alone (measured 2026-10-27: a
# session's prose counts too, so a whole-blob replace would edit messages).
MIME_KEYS = ("mime", "mediatype", "mimetype")
URL_KEYS = ("url", "source")


def db_default() -> Path:
    """The chat engine's database: OpenCode's own data folder (XDG_DATA_HOME wins)."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"


def flat(text) -> str:
    """Whitespace collapsed and lowercased, so a pattern matches across a line break or case."""
    return " ".join(str(text or "").split()).lower()


def load_repairs(path=None) -> list:
    """The entries from crew/chat_repairs.json that name a pattern and a fixer."""
    path = Path(path) if path else REPAIRS_FILE
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = doc.get("repairs") if isinstance(doc, dict) else doc
    return [e for e in entries or [] if isinstance(e, dict) and e.get("pattern") and e.get("fixer")]


def match(entries, error: str):
    """The first entry whose pattern is found in the engine's error text, or None."""
    text = flat(error)
    for entry in entries:
        try:
            if re.search(flat(entry["pattern"]), text):
                return entry
        except re.error:
            continue                                # a pattern Kris mistyped is skipped, never fatal
    return None


def _connect(db: Path, timeout: float):
    """A writable connection to the engine's database, or None; never blocks beyond `timeout`."""
    if not db.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=rw", uri=True, timeout=max(0.05, timeout))
        con.execute(f"pragma busy_timeout={int(max(0.05, timeout) * 1000)}")
        return con
    except sqlite3.Error:
        return None


def _columns(con, table: str) -> list:
    try:
        return [row[1] for row in con.execute(f"pragma table_info({table})")]
    except sqlite3.Error:
        return []


def _sid_column(columns: list) -> str:
    """The table's own session column, when it has one (older shapes keep it in the JSON only)."""
    return next((c for c in columns if c.lower() in ("sessionid", "session_id")), "")


def session_error(db: Path, session: str, timeout: float = 1.0) -> str:
    """The engine's own error text for that session's newest failed message, when it kept one.

    Read-only, and only ever used to explain a no-match: Kris adds the next pattern from the real
    text, so the tool must be able to show it.
    """
    con = _connect(db, timeout)
    if con is None:
        return ""
    try:
        columns = _columns(con, "message")
        if not columns:
            return ""
        sid_col = _sid_column(columns)
        where = f" where {sid_col} = ?" if sid_col else ""
        rows = con.execute(f"select data from message{where} order by rowid desc limit 200",
                           (session,) if sid_col else ()).fetchall()
        for (data,) in rows:
            try:
                info = json.loads(data) or {}
            except ValueError:
                continue
            if not sid_col and str(info.get("sessionID") or "") != session:
                continue
            err = info.get("error")
            if not err:
                continue
            if isinstance(err, str):
                return err
            data_in = err.get("data") if isinstance(err.get("data"), dict) else {}
            parts = [str(err.get("name") or ""), str(data_in.get("message") or ""),
                     str(err.get("message") or "")]
            return " ".join(p for p in parts if p).strip()
    except sqlite3.Error:
        return ""
    finally:
        con.close()
    return ""


def _parsed(data):
    """The part a row's `data` holds, or None when it does not carry the type at all."""
    if not isinstance(data, str) or BAD_MIME not in data:
        return None
    try:
        info = json.loads(data)
    except ValueError:
        return None
    return info if isinstance(info, dict) else None


def _rewrite(info: dict) -> int:
    """Rewrite the type in a part's own image fields; -> how many fields changed.

    The mime field and the `data:image/...;base64,` URL are the only places that mean "this
    message carries an image of this type". Everything else - a message that talks about the type,
    a filename - is left exactly as it is.
    """
    changed = 0
    for key, value in list(info.items()):
        if not isinstance(value, str) or BAD_MIME not in value:
            continue
        low = key.lower()
        if low in MIME_KEYS and value.strip() == BAD_MIME:
            info[key] = GOOD_MIME
            changed += 1
        elif low in URL_KEYS and value.startswith(f"data:{BAD_MIME}"):
            info[key] = value.replace(BAD_MIME, GOOD_MIME)
            changed += 1
    return changed


def rewrite_bmp_mime(db: Path, session: str, dry: bool, timeout: float) -> dict:
    """Rewrite image/x-ms-bmp to image/bmp in THIS session's stored image parts.

    Only parts that belong to `session` are touched, and only their mime field and the
    `data:image/x-ms-bmp;base64,` URL are rewritten - a message that merely mentions the type
    keeps its words. A database lock we cannot take is reported, never waited on forever.
    """
    out = {"changed": 0, "parts": [], "found": 0, "why": ""}
    con = _connect(db, timeout)
    if con is None:
        out["why"] = f"no writable database at {db}"
        return out
    try:
        columns = _columns(con, "part")
        sid_col = _sid_column(columns)
        rows = con.execute(f"select rowid, {sid_col or 'null'}, data from part where data like ?",
                           (f"%{BAD_MIME}%",)).fetchall()
        for rowid, column_sid, data in rows:
            info = _parsed(data)
            if info is None:
                continue
            sid = str(column_sid or "") or str(info.get("sessionID") or "")
            if not _rewrite(dict(info)):
                continue                            # mentions the type in prose only: untouched
            out["found"] += 1
            if sid != session:
                continue                            # another chat's image: counted, never touched
            _rewrite(info)
            if not dry:
                con.execute("update part set data = ? where rowid = ?",
                            (json.dumps(info, ensure_ascii=False, separators=(",", ":")), rowid))
            out["changed"] += 1
            out["parts"].append(str(rowid))
        if out["changed"] and not dry:
            con.commit()
        if not out["found"]:
            out["why"] = "no stored part carries this image type in its own fields"
        elif not out["changed"]:
            out["why"] = f"{out['found']} part(s) carry it, none in this session"
    except sqlite3.Error as exc:
        out["changed"], out["parts"] = 0, []
        out["why"] = f"the database did not take the write: {exc}"
    finally:
        con.close()
    return out


FIXERS = {"rewrite_bmp_mime": rewrite_bmp_mime}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--session", required=True, help="the chat's session id")
    ap.add_argument("--error", required=True, help="the engine's error text for the failed message")
    ap.add_argument("--db", default="", help="the engine's opencode.db (default: OpenCode's own)")
    ap.add_argument("--log", default="", help="one JSON line per run (default: <state>/chat_repairs.jsonl)")
    ap.add_argument("--apply", action="store_true", help="write the repair (without it: a dry run)")
    ap.add_argument("--timeout", type=float, default=5.0, help="seconds to wait for the database lock")
    a = ap.parse_args(argv)

    db = Path(a.db) if a.db else db_default()
    log = Path(a.log) if a.log else Path(load_config().state_home) / "chat_repairs.jsonl"
    entry = match(load_repairs(), a.error)
    result, detail = "no-match", ""
    if entry is None:
        detail = "no pattern matched"
        known = session_error(db, a.session)
        if known:
            detail = f"no pattern matched; the engine's own error text was: {known[:400]}"
    else:
        fixer = FIXERS.get(str(entry.get("fixer")))
        if fixer is None:
            detail = f"unknown fixer {entry.get('fixer')}"
        else:
            out = fixer(db, a.session, dry=not a.apply, timeout=a.timeout)
            if out["changed"]:
                result = "repaired" if a.apply else f"would-repair {out['changed']}"
                detail = f"{out['changed']} part(s) rewritten to {GOOD_MIME}: {', '.join(out['parts'])}"
            else:
                detail = f"nothing changed: {out['why'] or 'no part matched'}"

    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": a.session, "db": str(db),
            "pattern": (entry or {}).get("name", ""), "fixer": (entry or {}).get("fixer", ""),
            "applied": bool(a.apply), "result": result, "detail": detail,
            "error": flat(a.error)[:300]}
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"could not write {log}: {exc}", file=sys.stderr)

    print(result)
    if detail:
        print(detail, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
