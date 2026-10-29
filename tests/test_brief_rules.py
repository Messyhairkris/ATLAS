"""D: the fix catalogue's `brief_rule` entries become each member's OWN standing lines.

A rule learned from Gordon's refusals must reach Gordon's brief and no one else's - that is the
whole point of generating them per member from `crew/fixes.json` instead of pasting one shared
list into every brief. The last two tests check the real catalogue and a real rendered brief.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew import pa_brief

CATALOGUE = {
    "entries": [
        {"name": "for_gordon", "kind": "brief_rule", "status": "active",
         "members": ["Gordon"], "rule": "  One command per call;\n no `&`.  "},
        {"name": "for_two", "kind": "brief_rule", "status": "active",
         "members": ["Kimi", "Qwen"], "rule": "Read the file again before the next edit."},
        {"name": "already_fixed", "kind": "brief_rule", "status": "record",
         "members": ["Gordon"], "rule": "Must never appear: this one is only a record."},
        {"name": "not_a_rule", "kind": "plugin", "status": "active",
         "members": ["Gordon"], "rule": "Must never appear: it is not a brief_rule."},
        {"name": "blank_rule", "kind": "brief_rule", "status": "active",
         "members": ["Gordon"], "rule": "   \n  "},
        {"name": "nobody", "kind": "brief_rule", "status": "active",
         "members": [], "rule": "Must reach no one - it names no member."},
    ]
}


def test_a_member_gets_only_its_own_active_brief_rules():
    assert pa_brief.member_rules("Gordon", CATALOGUE) == ["One command per call; no `&`."]


def test_a_member_with_no_rule_gets_nothing():
    assert pa_brief.member_rules("Nemotron", CATALOGUE) == []


def test_a_rule_that_names_two_members_reaches_both():
    for who in ("Kimi", "Qwen"):
        assert pa_brief.member_rules(who, CATALOGUE) == [
            "Read the file again before the next edit."]


def test_a_broken_or_empty_catalogue_gives_no_rules_and_never_raises():
    assert pa_brief.member_rules("Gordon", {}) == []
    assert pa_brief.member_rules("Gordon", {"entries": [None, 42, {"kind": "brief_rule"}]}) == []
    assert pa_brief.member_rules("Gordon", {"entries": "not a list"}) == []


def test_every_active_brief_rule_in_the_real_catalogue_names_a_member_and_says_something():
    data = pa_brief._read_json(pa_brief.FIXES)
    active = [e for e in (data or {}).get("entries") or []
              if e.get("kind") == "brief_rule" and e.get("status") == "active"]
    assert active, "the catalogue lost every active brief_rule entry"
    for entry in active:
        assert entry.get("members"), f"{entry['name']} names no member, so it reaches nobody"
        assert str(entry.get("rule") or "").strip(), f"{entry['name']} carries no rule text"


def test_the_real_catalogue_gives_gordon_habits_and_an_unmentioned_member_none():
    gordon = pa_brief.member_rules("Gordon")
    assert any("PowerShell" in rule for rule in gordon), gordon
    assert pa_brief.member_rules("Hoss") == []


def test_a_rendered_brief_carries_the_members_own_habits_only():
    head = "## Your own habits"
    brief = pa_brief.render("Gordon")
    assert head in brief, "Gordon's own habits must appear in his brief"
    assert "PowerShell" in brief, brief[:400]
    # Claude is named by no brief_rule, so the section is absent for it entirely.
    assert head not in pa_brief.render("Claude")
