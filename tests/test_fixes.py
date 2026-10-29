"""crew/fixes.json: the fix catalogue.

Kris edits this file, so it needs the same guard as the other settings (context.json,
limits.json): a typo in a regex or a member's name must fail here, not silently in a build. The
miner (crew/runners/mine_failures.py) only proposes new entries; this checks that what is in the
file is usable.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXES = REPO / "crew" / "fixes.json"

WHERES = {"engine_error", "tool_refusal", "tool_error", "check_output"}
KINDS = {"plugin", "after_run_hint", "chat_repair", "brief_rule"}
STATUSES = {"active", "record"}
FIELDS = ("name", "where", "pattern", "kind", "status", "fixer", "members", "jobs", "hits")


def _catalogue():
    return json.loads(FIXES.read_text(encoding="utf-8"))


def test_the_catalogue_loads_and_says_what_its_fields_mean():
    d = _catalogue()
    assert d["entries"], "the catalogue is empty"
    assert set(d["_kinds"]) == KINDS
    assert set(d["_statuses"]) == STATUSES
    assert tuple(d["_entry_fields"]) == FIELDS


def test_every_entry_has_the_declared_fields():
    for e in _catalogue()["entries"]:
        for field in FIELDS:
            assert field in e, f"{e.get('name')} has no {field}"


def test_names_are_unique():
    names = [e["name"] for e in _catalogue()["entries"]]
    assert len(names) == len(set(names))


def test_every_pattern_compiles():
    for e in _catalogue()["entries"]:
        try:
            re.compile(e["pattern"])
        except re.error as exc:                       # pragma: no cover - the failure path
            raise AssertionError(f"{e['name']}: pattern does not compile: {exc}") from exc


def test_every_entry_uses_a_known_where_kind_and_status():
    for e in _catalogue()["entries"]:
        assert e["where"] in WHERES, e["name"]
        assert e["kind"] in KINDS, e["name"]
        assert e["status"] in STATUSES, e["name"]
        assert isinstance(e["hits"], int) and e["hits"] >= 0, e["name"]
        assert isinstance(e["members"], list) and isinstance(e["jobs"], list), e["name"]


def test_every_member_named_is_a_real_one():
    staff = json.loads((REPO / "crew" / "personnel.json").read_text(encoding="utf-8"))
    known = set(staff.get("members") or {}) | set((staff.get("pa") or {}).get("approved") or [])
    for e in _catalogue()["entries"]:
        for member in e["members"]:
            assert member in known, f"{e['name']} names an unknown member: {member}"


def test_an_active_brief_rule_carries_the_rule_it_adds():
    # a brief_rule with nothing to add would silently do nothing in that member's brief
    for e in _catalogue()["entries"]:
        if e["kind"] == "brief_rule" and e["status"] == "active":
            assert e.get("rule"), f"{e['name']} is an active brief_rule with no rule"


def test_a_record_entry_does_not_claim_a_plugin_fix():
    # `record` means "already fixed at the source, keep counting only"
    for e in _catalogue()["entries"]:
        if e["status"] == "record":
            assert e["kind"] != "plugin", f"{e['name']} is a record but would still rewrite calls"
