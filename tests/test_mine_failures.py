"""crew/runners/mine_failures.py - the failure miner (Claude's design, 2026-10-28).

Read-only, and it only ever PROPOSES. Every test builds its own job folders and database; the
live engine database is never read and nothing is ever written.

The two things that matter: a shape the catalogue knows is counted against its entry, and a shape
it does not know comes out as a ranked candidate - which is how the catalogue grows.
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "crew" / "runners" / "mine_failures.py"
REFUSAL = "The user has specified a rule which prevents you from using this specific tool call."

MEMBER = "Gordon"


def _load():
    spec = importlib.util.spec_from_file_location("mine_failures", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


miner = _load()


# ---- fixtures ---------------------------------------------------------------------------

def _parts(rows):
    """`rows` as part rows: either part dicts, or (tool, error, input) tuples for a failed call."""
    return [r if isinstance(r, dict) else
            {"type": "tool", "tool": r[0],
             "state": {"status": "error", "error": r[1], "input": r[2]}}
            for r in rows]


def _build(home, status, rows, checks=""):
    home.mkdir(parents=True, exist_ok=True)
    (home / "status.json").write_text(json.dumps(status), encoding="utf-8")
    db = home / "data" / "opencode" / "opencode.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("create table part (id text, data text)")
    con.executemany("insert into part values (?, ?)",
                    [(f"p{i}", json.dumps(p)) for i, p in enumerate(_parts(rows))])
    con.commit()
    con.close()
    if checks:
        (home / "checks.txt").write_text(checks, encoding="utf-8")
    return home


def _catalogue(tmp_path, entries):
    p = tmp_path / "fixes.json"
    p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return p


# ---- the shapes ------------------------------------------------------------------------

def test_a_known_refusal_is_counted_against_its_entry(tmp_path):
    entries = [{"name": "drop_stderr_redirect", "where": "tool_refusal",
                "pattern": r"\s+2>(&1|nul)\s*$", "kind": "plugin", "status": "active",
                "fixer": "", "members": ["Gordon"], "jobs": [], "hits": 1}]
    _build(tmp_path / "b1", {"pa": MEMBER},
           [("bash", "Error: refused", {"command": "cargo test 2>&1"}),
            ("bash", "Error: refused", {"command": "cargo build 2>nul"})])
    records = miner.records_from_build(tmp_path / "b1")
    mined = miner.mine(records, entries)
    assert len(mined["known"]) == 1 and mined["candidates"] == []
    got = mined["known"][0]
    assert got["name"] == "drop_stderr_redirect" and got["count"] == 2
    assert got["members"] == [MEMBER] and got["jobs"] == ["b1"]


def test_a_refusal_is_recognised_by_its_error_and_a_command_by_its_text(tmp_path):
    # outside_worktree only shows in the error text; drop_stderr_redirect only in the command
    entries = [{"name": "outside_worktree", "where": "tool_refusal",
                "pattern": '"permission":"external_directory"', "kind": "brief_rule",
                "status": "active", "fixer": "", "members": [], "jobs": [], "hits": 1}]
    _build(tmp_path / "b1", {"pa": MEMBER},
           [("bash", '{"permission":"external_directory"} refused', {"command": "dir C:\\elsewhere"})])
    mined = miner.mine(miner.records_from_build(tmp_path / "b1"), entries)
    assert [k["name"] for k in mined["known"]] == ["outside_worktree"]
    assert mined["candidates"] == []


def test_a_shape_no_entry_matches_becomes_a_ranked_candidate(tmp_path):
    entries = [{"name": "something_else", "where": "tool_error", "pattern": "never-matches-this",
                "kind": "after_run_hint", "status": "active", "fixer": "", "members": [],
                "jobs": [], "hits": 1}]
    _build(tmp_path / "b1", {"pa": MEMBER},
           [("edit", "Error: ENOENT 1234 while opening", {"filePath": "a.rs"}),
            ("edit", "Error: ENOENT 5678 while opening", {"filePath": "b.rs"})])
    mined = miner.mine(miner.records_from_build(tmp_path / "b1"), entries)
    assert mined["known"] == []
    assert len(mined["candidates"]) == 1, "the two are the same shape once the numbers are masked"
    cand = mined["candidates"][0]
    assert cand["count"] == 2 and cand["members"] == [MEMBER]


def test_different_shapes_are_ranked_by_how_often_they_happen(tmp_path):
    entries = []
    _build(tmp_path / "b1", {"pa": MEMBER},
           [("bash", "Error: one kind of thing", {"command": "aa"}),
            ("bash", "Error: one kind of thing", {"command": "aa"}),
            ("bash", "Error: another kind", {"command": "bb"})])
    mined = miner.mine(miner.records_from_build(tmp_path / "b1"), entries)
    assert [c["count"] for c in mined["candidates"]] == [2, 1]


def test_a_failed_check_is_a_check_output_shape(tmp_path):
    _build(tmp_path / "b1", {"pa": MEMBER}, [],
           checks="error[E0004]: non-exhaustive patterns: `Z` not covered\n")
    records = miner.records_from_build(tmp_path / "b1")
    assert [r["where"] for r in records] == ["check_output"]
    entries = [{"name": "non_exhaustive_match", "where": "check_output",
                "pattern": r"error\[E0004\]", "kind": "after_run_hint", "status": "active",
                "fixer": "", "members": [], "jobs": [], "hits": 1}]
    assert miner.mine(records, entries)["known"][0]["name"] == "non_exhaustive_match"


def test_a_record_entry_is_counted_but_does_not_act(tmp_path):
    entries = [{"name": "bmp_mime", "where": "engine_error", "pattern": "image/x-ms-bmp",
                "kind": "chat_repair", "status": "record", "fixer": "", "members": [],
                "jobs": [], "hits": 1}]
    _build(tmp_path / "b1", {"pa": MEMBER},
           [("bash", "Error: Image type image/x-ms-bmp not supported", {"command": "x"})])
    got = miner.mine(miner.records_from_build(tmp_path / "b1"), entries)["known"][0]
    assert got["status"] == "record" and got["count"] == 1


def test_an_empty_or_broken_build_folder_is_survivable(tmp_path):
    _build(tmp_path / "ok", {"pa": MEMBER}, [])
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "status.json").write_text("{not json", encoding="utf-8")
    db = tmp_path / "broken" / "data" / "opencode" / "opencode.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("create table part (id text, data text)")
    con.execute("insert into part values ('p', 'not json either')")
    con.commit()
    con.close()
    records = miner.records_from_build(tmp_path / "broken")
    assert records == [], "a broken job contributes nothing rather than crashing the miner"


def test_a_crew_agent_name_never_reaches_a_proposal(tmp_path):
    # a record's member is whatever the job called its agent; for a crew agent that is `build` or
    # `general`, not a person. A per-member brief rule for a member that does not exist would be
    # silently useless - and tests/test_fixes.py refuses the name if it is pasted in.
    _build(tmp_path / "b1", {"pa": "build"}, [("bash", "Error: odd", {"command": "zzz"})])
    mined = miner.mine(miner.records_from_build(tmp_path / "b1"), [])
    assert mined["candidates"][0]["members"] == [], "`build` is not a member"
    assert miner._proposal(mined["candidates"][0])["members"] == []
    assert "Gordon" in miner.known_members() and "build" not in miner.known_members()


# ---- the proposal ----------------------------------------------------------------------

def test_the_proposal_is_paste_ready_for_the_catalogue(tmp_path):
    _build(tmp_path / "b1", {"pa": MEMBER}, [("bash", REFUSAL + " 2>&1", {"command": "cargo test 2>&1"})])
    mined = miner.mine(miner.records_from_build(tmp_path / "b1"), [])
    proposal = miner._proposal(mined["candidates"][0])
    for field in ("name", "where", "pattern", "kind", "status", "fixer", "members", "jobs", "hits"):
        assert field in proposal, field
    assert proposal["members"] == [MEMBER] and proposal["hits"] == 1
    assert proposal["where"] == "tool_refusal"


# ---- the CLI ---------------------------------------------------------------------------

def test_the_cli_reports_and_writes_nothing(tmp_path):
    _build(tmp_path / "b1", {"pa": MEMBER}, [("bash", REFUSAL + " 2>&1", {"command": "cargo test 2>&1"})])
    fixes = _catalogue(tmp_path, [])
    before = fixes.read_text(encoding="utf-8")
    import subprocess
    run = subprocess.run([sys.executable, str(TOOL), "--builds", str(tmp_path),
                          "--fixes", str(fixes), "--db", str(tmp_path / "no.db")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         cwd=str(REPO), timeout=180)
    assert run.returncode == 0, run.stderr
    assert "CANDIDATES" in run.stdout and "KNOWN" in run.stdout
    assert fixes.read_text(encoding="utf-8") == before, "the miner must never touch the catalogue"


def test_the_json_view_carries_the_proposals(tmp_path):
    import subprocess
    _build(tmp_path / "b1", {"pa": MEMBER}, [("bash", "Error: odd", {"command": "zzz"})])
    fixes = _catalogue(tmp_path, [])
    run = subprocess.run([sys.executable, str(TOOL), "--builds", str(tmp_path), "--fixes", str(fixes),
                          "--db", str(tmp_path / "no.db"), "--json"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         cwd=str(REPO), timeout=180)
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["records"] == 1 and data["proposals"]
    assert data["proposals"][0]["hits"] == 1
