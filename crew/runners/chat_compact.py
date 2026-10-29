"""Compact a chat's context, the ready built system (Kris, 2026-10-27).

Kris: "I requested a compact and Gordon did it, but it did not seem like a ready built system."
This is that system, run by The Crew's window for one chat. It is the IO half of the compact;
the pure rules (the stages, the meter's numbers, the truncation and the summary input) live in
`crew/compactlib.py`.

The three things it does, in this order:

1. **Back up first.** The session's messages and the whole engine database are copied into
   `runs/crew/pa/chats/<session>/compact/`, with the summary input beside them. Nothing is
   written by the engine until the backup exists, so a compact that fails leaves the chat alone.
2. **Run the engine's own compaction** - `POST /session/{id}/summarize`. Measured 2026-10-28,
   this took **640 seconds** on a full chat; the client that gave up at 540 s looked like a
   failure while the engine went on to finish. So this waits, and polls: the Coffee-break Timer.
   `--wait` is the ceiling (default 1800 s = 30 minutes); `--poll` is how often it says it is
   still working.
3. **Show a before/after line**: `compacted 112k -> 9k, backup saved to <folder>`.

    python crew/runners/chat_compact.py --session ses_x --url http://127.0.0.1:4199 \\
        --secret <engine password> --apply

Without `--apply` it is a dry run: it reads the fill and writes the backup, but does not spend a
model call. Standard output is the one line the caller shows.
"""

import argparse
import base64
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew import compactlib  # noqa: E402
from crew.config import load_config  # noqa: E402

TEMPLATE_FILE = REPO_ROOT / "crew" / "compact_template.md"
DEFAULT_WAIT = 1800.0
DEFAULT_POLL = 15.0


def db_default() -> Path:
    """The chat engine's database: OpenCode's own data folder (XDG_DATA_HOME wins)."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"


def _connect(db: Path, timeout: float = 2.0):
    """A read-only connection to the engine's database, or None. Never blocks past `timeout`."""
    if not db.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=max(0.05, timeout))
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


def _rows(con, table: str, session: str) -> list:
    """This session's rows, oldest first, as `(columns, data)`; empty on any problem.

    The stored JSON is only PART of a row. A part's JSON is `{"type", "text", "time"}`; the
    message it belongs to is the `message_id` COLUMN, and a message's own id is the `id` column -
    the JSON carries neither (measured 2026-10-28). Reading `data` alone loses every link: grouping
    parts by a JSON `messageID` put all 3571 of them in one bucket, and the digest then rescanned
    that bucket once per message, 796 times over.
    """
    columns = _columns(con, table)
    if not columns:
        return []
    sid_col = _sid_column(columns)
    carried = [c for c in ("id", "session_id", "message_id", "time_created", "time_updated") if c in columns]
    select = ", ".join(carried + ["data"])
    try:
        if sid_col:
            rows = con.execute(f"select {select} from {table} where {sid_col} = ? order by rowid", (session,)).fetchall()
        else:
            rows = con.execute(f"select {select} from {table} order by rowid").fetchall()
    except sqlite3.Error:
        return []
    out = []
    for row in rows:
        cols = dict(zip(carried, row[:-1]))
        try:
            info = json.loads(row[-1]) if isinstance(row[-1], str) else None
        except ValueError:
            continue
        if not isinstance(info, dict):
            continue
        if not sid_col and str(cols.get("session_id") or info.get("sessionID") or "") != session:
            continue
        out.append((cols, info))
    return out


def load_messages(db: Path, session: str, timeout: float = 2.0) -> list:
    """The session's message JSONs, oldest first (what the meter reads). Empty when unreadable."""
    con = _connect(db, timeout)
    if con is None:
        return []
    try:
        return [info for _, info in _rows(con, "message", session)]
    finally:
        con.close()


def session_digest(db: Path, session: str, timeout: float = 2.0) -> list:
    """The session's parts, grouped per message, in the small shape compactlib.summary_input wants.

    The grouping key is the `message_id` COLUMN, never a JSON field: parts are joined to their
    message by the table, so each message reads only its own parts (linear, not quadratic).
    """
    con = _connect(db, timeout)
    if con is None:
        return []
    try:
        messages = _rows(con, "message", session)
        parts = _rows(con, "part", session)
    finally:
        con.close()
    by_message = {}
    for cols, part in parts:
        by_message.setdefault(str(cols.get("message_id") or ""), []).append(part)
    digest = []
    for cols, info in messages:
        role = info.get("role") if info.get("role") in ("user", "assistant") else "assistant"
        item = {"role": role, "text": "", "reasoning": "", "tools": [], "results": []}
        texts, reasonings = [], []
        for part in by_message.get(str(cols.get("id") or ""), []):
            kind = part.get("type")
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            if kind == "text" and part.get("text"):
                texts.append(str(part["text"]))
            elif kind == "reasoning" and part.get("text"):
                reasonings.append(str(part["text"]))
            elif kind == "tool":
                item["tools"].append({"name": str(part.get("tool") or ""), "input": state.get("input")})
                if state.get("output"):
                    item["results"].append({"name": str(part.get("tool") or ""), "output": str(state["output"])})
        item["text"] = "\n".join(texts)
        item["reasoning"] = "\n".join(reasonings)
        digest.append(item)
    return digest


def compaction_count(db: Path, session: str, timeout: float = 2.0) -> int:
    """How many compactions the engine has recorded for this session.

    OpenCode writes a part with `type: "compaction"` when it summarises (measured 2026-10-28;
    the summary message also carries a `summary` key). Counting them is how a client that gave up
    tells "the engine failed" from "the engine finished after I stopped listening" - it completed
    at 639,952 ms on 2026-10-28 while the client had timed out at 540 s.
    """
    con = _connect(db, timeout)
    if con is None:
        return 0
    try:
        rows = _rows(con, "part", session)
    finally:
        con.close()
    return sum(1 for _, part in rows if part.get("type") == "compaction")


def model_of(messages: list) -> str:
    """The model the newest assistant message ran on ("" when the engine kept none)."""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            model = message.get("modelID")
            if isinstance(model, str) and model:
                return model
    return ""


def abbrev(n: int) -> str:
    """A token count the way the header shows it: `61k`, `128k`, `1.0M` (compactlib's rounder)."""
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f}M"
    if n >= 1000:
        return f"{round(n / 1000)}k"
    return str(n)


def _stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%S")


def backup(db: Path, session: str, dest: Path, digest: list, stamp: str = "") -> dict:
    """Copy the session's messages and the whole database into `dest`, before anything else.

    Returns the paths written. The messages file is always written (it is the smallest thing we
    would need to put a chat back); the database copy is best-effort - a locked file must not stop
    a compact, because the JSONL already holds this session's history.
    """
    stamp = stamp or _stamp()
    dest.mkdir(parents=True, exist_ok=True)
    written = {"messages": "", "db": "", "summary_input": ""}

    messages = load_messages(db, session, 5.0)
    messages_path = dest / f"{stamp}_messages.jsonl"
    with messages_path.open("w", encoding="utf-8") as fh:
        for info in messages:
            fh.write(json.dumps(info, ensure_ascii=False) + "\n")
    written["messages"] = str(messages_path)

    template = ""
    if TEMPLATE_FILE.is_file():
        try:
            template = TEMPLATE_FILE.read_text(encoding="utf-8")
        except OSError:
            template = ""
    summary_path = dest / f"{stamp}_summary_input.md"
    summary_path.write_text(compactlib.summary_input(digest, template), encoding="utf-8")
    written["summary_input"] = str(summary_path)

    db_path = dest / f"{stamp}_opencode.db"
    try:
        if db.is_file():
            shutil.copyfile(db, db_path)
            written["db"] = str(db_path)
    except OSError:
        written["db"] = ""
    return written


def _post_json(url: str, path: str, body: dict, secret: str, timeout: float):
    """One JSON POST to the engine, with the password as basic auth (user "opencode")."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{url}{path}", data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
    if secret:
        token = base64.b64encode(f"opencode:{secret}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def summarize(url: str, session: str, provider: str, model: str, secret: str = "",
              timeout: float = DEFAULT_WAIT, post=None) -> dict:
    """Run the engine's own compaction. `post` is injected for tests; the default does HTTP.

    The engine's route takes only providerID, modelID and auto - there is no template field, so
    our own summary input is kept beside the backup instead.
    """
    body = {"providerID": provider, "modelID": model, "auto": False}
    post = post or _post_json
    try:
        result = post(url, f"/session/{session}/summarize", body, secret, timeout)
    except Exception as exc:                                  # noqa: BLE001 - report, never crash
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "raw": str(result)[:200]}


def compact(session: str, url: str = "", secret: str = "", provider: str = "synthetic",
            model: str = "", db=None, dest=None, apply: bool = False,
            wait: float = DEFAULT_WAIT, poll: float = DEFAULT_POLL,
            post=None, stamp: str = "", progress=None) -> dict:
    """Back up, then (with `apply`) summarise, then measure. The coffee-break wait lives here.

    Order is the contract: the backup is written before `summarize` is called, so a failed or
    timed-out summarize leaves the chat exactly as it was.
    """
    db = Path(db) if db else db_default()
    dest = Path(dest) if dest else Path(load_config().state_home) / "pa" / "chats" / session / "compact"
    progress = progress or (lambda _msg: None)

    messages = load_messages(db, session)
    before = compactlib.newest_fill(messages)
    compactions_before = compaction_count(db, session)
    digest = session_digest(db, session)
    written = backup(db, session, dest, digest, stamp)
    out = {"session": session, "before": before, "after": before, "backup": written,
           "summarized": False, "applied": bool(apply), "why": ""}

    def late() -> bool:
        """Did the engine finish the summary after we stopped listening?

        A timeout is NOT proof of failure: measured 2026-10-28, the engine completed at 639,952 ms
        while the client had given up at 540 s, and the chat WAS compacted. So before reporting a
        failure, look for a new compaction part; if one is there, report it as done, late.
        """
        if compaction_count(db, session) <= compactions_before:
            return False
        out["summarized"] = True
        out["late"] = True
        out["why"] = ""
        out["after"] = compactlib.newest_fill(load_messages(db, session))
        return True

    if not apply:
        out["why"] = "dry run: backup written, no summarize"
        return out
    if not url:
        out["why"] = "no engine url given"
        return out
    model = model or model_of(messages)
    if not model:
        out["why"] = "no model recorded for this chat"
        return out

    box = {}
    thread = threading.Thread(target=lambda: box.update(summarize(url, session, provider, model, secret, wait, post)), daemon=True)
    thread.start()
    started = time.time()
    while thread.is_alive() and (time.time() - started) < wait:
        thread.join(timeout=poll)
        if thread.is_alive():
            progress(f"still compacting {session} ({int(time.time() - started)}s)")
    if thread.is_alive():
        out["why"] = f"gave up waiting after {int(wait)}s (the chat is unchanged; the backup is kept)"
        late()                     # the engine may still have finished it, after we stopped
        return out

    result = box or {"ok": False, "why": "the summarize call gave no answer"}
    if not result.get("ok"):
        out["why"] = f"the summarize failed: {result.get('why', '')}"
        late()                     # a failed call is not proof the summary did not happen
        return out
    out["summarized"] = True
    out["after"] = compactlib.newest_fill(load_messages(db, session))
    return out


def line_for(out: dict) -> str:
    """The one line the window shows."""
    folder = Path(out["backup"]["messages"]).parent if out["backup"]["messages"] else ""
    if out["summarized"]:
        late = " (late - the engine finished after we stopped listening)" if out.get("late") else ""
        return f"compacted {abbrev(out['before'])} -> {abbrev(out['after'])}, backup saved to {folder}{late}"
    if not out["applied"]:
        return f"would compact {abbrev(out['before'])} (dry run), backup saved to {folder}"
    return f"nothing compacted ({out['why']}), backup saved to {folder}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--session", required=True, help="the chat's session id")
    ap.add_argument("--url", default="", help="the engine base url, e.g. http://127.0.0.1:4199")
    ap.add_argument("--secret", default="", help="the engine's password (basic auth, user opencode)")
    ap.add_argument("--secret-stdin", action="store_true",
                    help="read the password from stdin instead of --secret. A command line is "
                         "visible to every process listing, so the window passes it on the pipe "
                         "(desk::python writes its stdin argument) rather than in argv.")
    ap.add_argument("--provider", default="synthetic")
    ap.add_argument("--model", default="", help="default: the newest assistant message's modelID")
    ap.add_argument("--db", default="", help="the engine's opencode.db (default: OpenCode's own)")
    ap.add_argument("--dir", default="", help="where the backup goes (default: the chat's compact/)")
    ap.add_argument("--wait", type=float, default=DEFAULT_WAIT, help="seconds to wait for the engine")
    ap.add_argument("--poll", type=float, default=DEFAULT_POLL, help="seconds between progress lines")
    ap.add_argument("--apply", action="store_true", help="run the summarize (without it: a dry run)")
    a = ap.parse_args(argv)

    secret = sys.stdin.readline().strip() if a.secret_stdin else a.secret

    out = compact(
        a.session, url=a.url, secret=secret, provider=a.provider, model=a.model,
        db=a.db or None, dest=a.dir or None, apply=a.apply, wait=a.wait, poll=a.poll,
        progress=lambda msg: print(msg, file=sys.stderr, flush=True),
    )
    print(line_for(out))
    return 0 if (out["summarized"] or not out["applied"]) else 1


if __name__ == "__main__":
    sys.exit(main())
