"""Mine the jobs for failure shapes, and propose catalogue entries (Claude's design, 2026-10-28).

Read-only. It reads every build folder and the engine's database, groups every failed, refused
and failed-check call by the shape it has, and reports:

- **KNOWN** - the shapes `crew/fixes.json` already matches, with how often each fired, for which
  member, and in which jobs. This is how you tell a catalogue entry that works from one that
  never fires.
- **CANDIDATES** - failures NO entry matches, grouped by a normalised signature and ranked by how
  often they happen. Each is printed as a ready-to-paste JSON entry for Kris to approve.

It never writes anything: not the catalogue, not a job folder. `--json` prints the machine view
for the next tool to use.

    python crew/runners/mine_failures.py [--builds DIR] [--db PATH] [--fixes PATH] [--top N] [--json]
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew import guard  # noqa: E402

DEFAULT_BUILDS = REPO_ROOT / "runs" / "crew" / "pa" / "builds"
DEFAULT_FIXES = REPO_ROOT / "crew" / "fixes.json"


def db_default() -> Path:
    """The chat engine's database (XDG_DATA_HOME wins, as the engine itself honours it)."""
    import os
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"


def load_entries(path=DEFAULT_FIXES) -> list:
    """The catalogue's entries; an unreadable or broken file is an empty catalogue, not a crash."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = data.get("entries")
        return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    except (OSError, ValueError):
        return []


def match_entry(entry: dict, record: dict):
    """The entry whose pattern matches this failure, or None.

    A pattern is matched against the command AND the error, because the shapes differ: a refused
    `dir /s /b` is recognised by its command, an outside-worktree refusal only by its error text.
    A `record` entry still matches - it is counted, never acted on.
    """
    try:
        pattern = re.compile(entry.get("pattern") or "")
    except re.error:
        return None
    for text in (record.get("command") or "", record.get("error") or "", record.get("output") or ""):
        if text and pattern.search(text):
            return entry
    return None


def _mask(text: str) -> str:
    """Strip what differs between two instances of the SAME failure.

    A long id, a drive path, a file name and a number all change from one call to the next, and
    none of them make it a different kind of failure - so an edit on `a.rs` and an edit on `b.rs`
    count as one shape, which is what a catalogue entry is for.
    """
    text = re.sub(r"\b[0-9a-fA-F]{8,}\b", "<id>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s\"]+", "<path>", text)
    text = re.sub(r"(?<![\w])(?:[\w.-]+[\\/])*[\w-]+\.[A-Za-z0-9]{1,6}\b", "<file>", text)
    return re.sub(r"\b\d+\b", "N", text)


def _norm_error(text: str) -> str:
    """A signature for an error: the wording that stays once the noise is gone."""
    return _mask(" ".join(str(text or "").split()))[:160]


def _norm_command(text: str) -> str:
    """A signature for a command: the first two words of each stage it pipes into.

    Two words, not one, so `cargo test` and `cargo build` do not collapse into one shape - while
    a different file or a different number still lands on the same one.
    """
    text = _mask(" ".join(str(text or "").split()))
    stages = [" ".join(stage.strip().split()[:2]) for stage in text.split("|")]
    return " | ".join(s for s in stages if s)[:80]


def signature(record: dict) -> str:
    """One string that says "this is the same failure again"."""
    if record.get("where") == "check_output":
        return "check | " + _norm_error(record.get("output"))
    return " | ".join(part for part in
                      (record.get("tool") or "", _norm_command(record.get("command") or ""),
                       _norm_error(record.get("error") or "")) if part)


def _build_parts(db: Path) -> list:
    """A build's parts, or nothing. `guard._parts` is the one reader, but it lets a bad row
    through as a ValueError, and the miner must never fall over on one corrupt job."""
    try:
        return guard._parts(db)
    except (ValueError, OSError, sqlite3.Error):
        return []


def records_from_build(home: Path) -> list:
    """Every failure in one build folder: its own database's tool errors, and its check output."""
    out = []
    member = ""
    try:
        member = str(json.loads((home / "status.json").read_text(encoding="utf-8")).get("pa") or "")
    except (OSError, ValueError):
        member = ""
    job = home.name
    db = guard.db_path(home)
    for part in _build_parts(db):
        state = part.get("state") or {}
        if part.get("type") != "tool" or state.get("status") != "error":
            continue
        error = " ".join(str(state.get("error") or "").split())
        command = ""
        inp = state.get("input")
        if isinstance(inp, dict):
            command = str(inp.get("command") or inp.get("filePath") or inp.get("pattern") or "")
        out.append({"source": "build", "job": job, "member": member, "tool": part.get("tool"),
                    "command": command, "error": error,
                    "where": "tool_refusal" if guard.is_refusal(error) else "tool_error"})
    checks = home / "checks.txt"
    if checks.is_file():
        text = checks.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            out.append({"source": "build", "job": job, "member": member, "tool": "checks",
                        "command": "", "error": "", "output": text, "where": "check_output"})
    return out


def records_from_chats(db: Path) -> list:
    """Every failure the chats recorded: tool errors from parts, engine errors from messages."""
    db = Path(db)
    if not db.is_file():
        return []
    out = []
    con = None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        con.execute("pragma busy_timeout=5000")
        agents = {}
        for mid, data in con.execute("select id, data from message"):
            try:
                message = json.loads(data) if isinstance(data, str) else {}
            except ValueError:
                continue
            agent = str(message.get("agent") or "")
            if agent:
                agents[mid] = agent
            error = message.get("error")
            if error:
                out.append({"source": "chat", "job": str(message.get("sessionID") or ""),
                            "member": agent.split("-")[0], "tool": "engine", "command": "",
                            "error": " ".join(str(error).split()), "where": "engine_error"})
        for mid, sid, data in con.execute("select message_id, session_id, data from part"):
            try:
                part = json.loads(data) if isinstance(data, str) else {}
            except ValueError:
                continue
            state = part.get("state") or {}
            if part.get("type") != "tool" or state.get("status") != "error":
                continue
            error = " ".join(str(state.get("error") or "").split())
            inp = state.get("input")
            command = ""
            if isinstance(inp, dict):
                command = str(inp.get("command") or "")
            out.append({"source": "chat", "job": str(sid), "member": agents.get(mid, "").split("-")[0],
                        "tool": part.get("tool"), "command": command, "error": error,
                        "where": "tool_refusal" if guard.is_refusal(error) else "tool_error"})
    except sqlite3.Error:
        return out
    finally:
        if con is not None:
            con.close()
    return out


def known_members() -> set:
    """The people a proposal may name: personnel.json's members and approved PAs.

    A record's "member" is whatever the job or the message called its agent, which for a crew
    agent is `build` or `general` - not a person. Those names must never reach a proposal: a
    per-member brief rule for a member that does not exist would be silently useless, and
    tests/test_fixes.py refuses them.
    """
    try:
        staff = json.loads((REPO_ROOT / "crew" / "personnel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(staff.get("members") or {}) | set((staff.get("pa") or {}).get("approved") or [])


def mine(records: list, entries: list) -> dict:
    """Split the failures into the shapes the catalogue knows and the shapes it does not."""
    people = known_members()
    known = defaultdict(lambda: {"name": "", "where": "", "kind": "", "status": "",
                                 "count": 0, "members": set(), "jobs": set()})
    unknown = defaultdict(lambda: {"where": "", "count": 0, "members": set(), "jobs": set(),
                                   "example": ""})
    for record in records:
        entry = match_entry_of(entries, record)
        member = record.get("member") if record.get("member") in people else ""
        if entry:
            bucket = known[entry["name"]]
            bucket.update(name=entry["name"], where=entry.get("where", ""),
                          kind=entry.get("kind", ""), status=entry.get("status", ""))
            bucket["count"] += 1
            if member:
                bucket["members"].add(member)
            if record.get("job"):
                bucket["jobs"].add(record["job"])
        else:
            key = signature(record)
            bucket = unknown[key]
            bucket["count"] += 1
            bucket["where"] = record.get("where") or ""
            if member:
                bucket["members"].add(member)
            if record.get("job"):
                bucket["jobs"].add(record["job"])
            if not bucket["example"]:
                bucket["example"] = (record.get("command") or record.get("error")
                                     or record.get("output") or "")[:200]
    for name, bucket in known.items():
        bucket["members"] = sorted(bucket["members"])
        bucket["jobs"] = sorted(bucket["jobs"])
    for key, bucket in unknown.items():
        bucket["members"] = sorted(bucket["members"])
        bucket["jobs"] = sorted(bucket["jobs"])
        bucket["signature"] = key
    return {
        "known": sorted(known.values(), key=lambda b: -b["count"]),
        "candidates": sorted(unknown.values(), key=lambda b: (-b["count"], b["signature"])),
        "records": len(records),
    }


def match_entry_of(entries, record):
    """The first matching entry. Split out so the miner and its tests use one rule."""
    for entry in entries:
        if match_entry(entry, record):
            return entry
    return None


def _proposal(bucket: dict) -> dict:
    """A candidate, in the exact shape `crew/fixes.json` wants - for Kris to approve."""
    is_refusal = bucket["where"] == "tool_refusal"
    return {
        "name": "proposed_" + re.sub(r"[^a-z0-9]+", "_", bucket["signature"].lower())[:40].strip("_"),
        "where": bucket["where"],
        "pattern": "TODO: a regex that matches this and nothing else",
        "kind": "plugin" if is_refusal else "after_run_hint",
        "status": "active",
        "fixer": "",
        "members": bucket["members"],
        "jobs": bucket["jobs"][:4],
        "hits": bucket["count"],
        "_seen": bucket["example"],
    }


def report(mined: dict, top: int = 10) -> str:
    """The human view: what the catalogue caught, then what it did not."""
    lines = [f"{mined['records']} failure(s) read; {len(mined['known'])} known shape(s), "
             f"{len(mined['candidates'])} candidate(s). Nothing was written.",
             "", "KNOWN (matched in crew/fixes.json)"]
    if not mined["known"]:
        lines.append("  (nothing - either the jobs are clean, or the catalogue is not matching)")
    for b in mined["known"][:top]:
        lines.append(f"  {b['count']:>4}  {b['name']:<26} {b['where']:<13} "
                     f"{','.join(b['members']) or '-':<12} status={b['status']} "
                     f"jobs={','.join(b['jobs'][:3]) or '-'}")
    lines += ["", f"CANDIDATES (no entry matches; top {top})"]
    if not mined["candidates"]:
        lines.append("  (none - every failure this run has a shape in the catalogue)")
    for b in mined["candidates"][:top]:
        lines.append(f"  {b['count']:>4}  {b['where']:<13} {','.join(b['members']) or '-':<12} "
                     f"{b['signature'][:96]}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--builds", default=str(DEFAULT_BUILDS), help="the folder of build runs")
    ap.add_argument("--db", default="", help="the chat engine's database (default: OpenCode's own)")
    ap.add_argument("--fixes", default=str(DEFAULT_FIXES), help="the catalogue to match against")
    ap.add_argument("--top", type=int, default=10, help="how many of each list to print")
    ap.add_argument("--json", action="store_true", help="print the machine view instead")
    a = ap.parse_args(argv)

    entries = load_entries(a.fixes)
    records = []
    builds = Path(a.builds)
    if builds.is_dir():
        for home in sorted(p for p in builds.iterdir() if p.is_dir()):
            records += records_from_build(home)
    records += records_from_chats(Path(a.db) if a.db else db_default())

    mined = mine(records, entries)
    if a.json:
        print(json.dumps({"entries": len(entries), **mined,
                          "proposals": [_proposal(b) for b in mined["candidates"]]}, indent=1,
                         default=list))
    else:
        print(report(mined, a.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
