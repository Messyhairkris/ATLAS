"""Search over past work: crew jobs, the PA chats' artifacts, digests, night reports, playbooks.

Round 3 (2026-10-26; the ATLAS study's "search past jobs and chats", Gordon's "persistent
project memory"). One SQLite FTS5 index at <state_home>/index/history.db, updated
incrementally by file time; the records and the query come from crew/history_docs.py
(crew-built). Transcripts are never indexed - they hold hidden-test output - and a crew member
sees only hits whose source it may read (jobs are denied to members), so the index widens what
a PA or Kris can find, never what a member can read.

  python -m crew search "token budget" [--kind job] [--limit 20] [--json] [--rebuild]
"""

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

from . import history_docs

REPO = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 300_000
TEXT = (".md", ".txt", ".json", ".py", ".js", ".mjs", ".rs", ".ahk", ".html")
KINDS = ("job", "chat", "doc", "night", "playbook")

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
    key UNINDEXED, kind, title, body, path UNINDEXED, when_ UNINDEXED, who, tags,
    tokenize = 'unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, mtime REAL NOT NULL);
"""


def db_path(cfg) -> Path:
    return Path(cfg.state_home) / "index" / "history.db"


def connect(cfg) -> sqlite3.Connection:
    path = db_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    db.executescript(SCHEMA)
    return db


def _read(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _mtime(*paths: Path) -> float:
    out = 0.0
    for p in paths:
        try:
            out = max(out, p.stat().st_mtime)
        except OSError:
            pass
    return out


def _jobs(state: Path) -> Iterator[Tuple[str, float, callable]]:
    for jdir in sorted((state / "jobs").glob("*")):
        job_file = jdir / "job.json"
        if not job_file.is_file():
            continue
        outs = [p for p in (jdir / "output").rglob("*")
                if p.is_file() and p.suffix.lower() in TEXT] if (jdir / "output").is_dir() else []

        def build(jdir=jdir, job_file=job_file, outs=outs):
            job = json.loads(job_file.read_text(encoding="utf-8"))
            texts = {p.relative_to(jdir / "output").as_posix(): _read(p) or "" for p in outs}
            return history_docs.job_record(job, texts, str(jdir))
        yield f"job:{jdir.name}", _mtime(job_file, *outs), build


def _docs(cfg, folder: Path, kind: str, pattern: str = "**/*.md") -> Iterator[Tuple[str, float, callable]]:
    if not folder.is_dir():
        return
    for path in sorted(folder.glob(pattern)):
        if not path.is_file() or cfg.denied(path):
            continue

        def build(path=path):
            return history_docs.doc_record(str(path), _read(path) or "", kind,
                                           _when(path))
        yield f"{kind}:{str(path).replace(chr(92), '/')}", _mtime(path), build


def _when(path: Path) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(_mtime(path)).isoformat(timespec="seconds")


def sources(cfg) -> Iterator[Tuple[str, float, callable]]:
    """(key, mtime, build) for everything the index holds."""
    state = Path(cfg.state_home)
    yield from _jobs(state)
    yield from _docs(cfg, state / "pa" / "chats", "chat")
    yield from _docs(cfg, state / "pa" / "studies", "doc")
    yield from _docs(cfg, state / "outbox", "doc")
    yield from _docs(cfg, state / "night", "night", "NIGHT_REPORT-*.md")  # not the latest's copy
    yield from _docs(cfg, REPO / "crew" / "playbooks", "playbook", "*.md")


def update(cfg, rebuild: bool = False) -> dict:
    """Bring the index up to date: changed and new sources in, vanished ones out."""
    db = connect(cfg)
    if rebuild:
        db.execute("DELETE FROM docs")
        db.execute("DELETE FROM seen")
    known = dict(db.execute("SELECT key, mtime FROM seen"))
    present, added, changed = set(), 0, 0
    for key, mtime, build in sources(cfg):
        present.add(key)
        if known.get(key) == mtime:
            continue
        try:
            rec = build()
        except (OSError, ValueError, KeyError):
            continue
        db.execute("DELETE FROM docs WHERE key = ?", (key,))
        db.execute("INSERT INTO docs (key, kind, title, body, path, when_, who, tags) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (rec["key"], rec["kind"], rec["title"], rec["body"], rec["path"],
                    rec["when"], rec["who"], rec["tags"]))
        db.execute("INSERT OR REPLACE INTO seen (key, mtime) VALUES (?, ?)", (key, mtime))
        if key in known:
            changed += 1
        else:
            added += 1
    gone = [k for k in known if k not in present]
    for key in gone:
        db.execute("DELETE FROM docs WHERE key = ?", (key,))
        db.execute("DELETE FROM seen WHERE key = ?", (key,))
    db.commit()
    total = db.execute("SELECT count(*) FROM seen").fetchone()[0]
    db.close()
    return {"added": added, "changed": changed, "removed": len(gone), "total": total}


def search(cfg, text: str, kind: str = "", limit: int = 20, refresh: bool = True,
           readable_only: bool = False, roots: Optional[Iterable[Path]] = None) -> List[dict]:
    """Best matches first. readable_only: keep only hits whose source the crew may read
    (the member tool), judged by cfg.readable against `roots`."""
    query = history_docs.fts_query(text)
    if not query:
        return []
    if refresh:
        update(cfg)
    db = connect(cfg)
    sql = ("SELECT key, kind, title, path, when_, who, tags, "
           "snippet(docs, 3, '[', ']', ' ... ', 14) "
           "FROM docs WHERE docs MATCH ?" + (" AND kind = ?" if kind else "")
           + " ORDER BY bm25(docs, 0, 0, 6.0, 1.0, 0, 0, 1.0, 3.0) LIMIT ?")
    args = [query] + ([kind] if kind else []) + [max(1, limit) * (4 if readable_only else 1)]
    rows = db.execute(sql, args).fetchall()
    db.close()
    out = []
    for key, k, title, path, when, who, tags, snip in rows:
        if readable_only and not cfg.readable(Path(path), list(roots) if roots else None):
            continue
        out.append({"key": key, "kind": k, "title": title, "path": path, "when": when,
                    "who": who, "tags": tags, "snippet": " ".join(snip.split())})
        if len(out) >= limit:
            break
    return out


def render(hits: List[dict]) -> str:
    """The plain-text form a member or a terminal reads."""
    if not hits:
        return "(no matches)"
    lines = []
    for h in hits:
        meta = " · ".join(x for x in (h["kind"], h["when"][:16], h["who"]) if x)
        lines.append(f"{h['title']}  ({meta})\n  {h['path']}\n  {h['snippet']}")
    return "\n".join(lines)
