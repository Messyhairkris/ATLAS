"""Hidden tests for review_index.py. The author never sees these."""

import pytest

import review_index as ix


def test_constants():
    assert ix.STATES == ("pending", "decided", "answered", "closed")
    assert ix.DECISIONS == ("approve", "reject", "question", "defer")
    assert ix.FIELDS[0] == "item_id"
    for field in ("title", "path", "origin", "state", "decision", "note",
                  "anchor", "decided_at"):
        assert field in ix.FIELDS


def test_new_item_is_complete_and_pending():
    item = ix.new_item("job-1:a.py", "review a.py", r"C:\work\a.py",
                       origin="crew:code_task:Hoss", anchor="L1-L3#abc123abc123")
    assert item["state"] == "pending"
    assert item["decision"] == "" and item["note"] == "" and item["decided_at"] == ""
    assert item["origin"] == "crew:code_task:Hoss"
    assert item["anchor"] == "L1-L3#abc123abc123"
    for field in ix.FIELDS:
        assert field in item


def test_new_item_requires_an_id_and_a_title():
    with pytest.raises(ValueError):
        ix.new_item("", "title", "p")
    with pytest.raises(ValueError):
        ix.new_item("id", "", "p")


def test_render_empty_is_empty():
    assert ix.render([]) == ""


def test_parse_empty_is_empty():
    assert ix.parse("") == []
    assert ix.parse("   \n\n") == []


def test_render_writes_a_section_per_item_with_every_field():
    a = ix.new_item("one", "first", "p1")
    b = ix.new_item("two", "second", "p2")
    text = ix.render([a, b])
    assert "[one]" in text and "[two]" in text
    for field in ix.FIELDS:
        if field != "item_id":
            assert f"{field} = " in text or f"{field} =" in text


def test_round_trip_survives_an_awkward_note():
    item = ix.new_item("job-1:a.py", "review a.py", r"C:\work\a.py")
    item["decision"] = "reject"
    item["state"] = "decided"
    item["note"] = ("two problems:\nthe ids skip = a number; also the note "
                    "handling is wrong")
    item["decided_at"] = "2026-09-20T06:00:00"
    back = ix.parse(ix.render([item]))
    assert back == [item]
    assert "\n" in back[0]["note"]


def test_round_trip_of_several_items_preserves_order():
    items = [ix.new_item(f"id-{n}", f"title {n}", f"path{n}") for n in range(4)]
    assert [i["item_id"] for i in ix.parse(ix.render(items))] == \
        ["id-0", "id-1", "id-2", "id-3"]


def test_render_refuses_a_bad_state_or_decision():
    item = ix.new_item("one", "first", "p")
    item["state"] = "melted"
    with pytest.raises(ValueError):
        ix.render([item])
    item = ix.new_item("two", "second", "p")
    item["decision"] = "maybe"
    with pytest.raises(ValueError):
        ix.render([item])


def test_parse_defaults_a_missing_state_to_pending():
    items = ix.parse("[one]\ntitle = first\npath = p\n")
    assert items[0]["state"] == "pending"
    assert items[0]["decision"] == ""
    assert items[0]["item_id"] == "one"


def test_parse_ignores_a_key_a_human_added():
    items = ix.parse("[one]\ntitle = first\nscribble = my own note to self\n")
    assert items[0]["title"] == "first"
    assert "scribble" not in items[0]


def test_parse_rejects_unreadable_text():
    with pytest.raises(ValueError):
        ix.parse("this is not ini at all\njust words\n")


def test_merge_adds_new_items_after_the_existing_ones():
    existing = [ix.new_item("a", "A", "pa")]
    incoming = [ix.new_item("b", "B", "pb"), ix.new_item("a", "A", "pa")]
    merged = ix.merge(existing, incoming)
    assert [i["item_id"] for i in merged] == ["a", "b"]


def test_merge_never_overwrites_a_human_decision():
    decided = ix.new_item("a", "A", "pa")
    decided.update(decision="reject", note="the ids skip a number",
                   state="decided", decided_at="2026-09-20T06:00:00")
    incoming = [ix.new_item("a", "A REWRITTEN", "pa-new")]
    merged = ix.merge([decided], incoming)
    assert merged[0]["decision"] == "reject"
    assert merged[0]["note"] == "the ids skip a number"
    assert merged[0]["title"] == "A"          # the whole record wins, not just the note
    assert merged[0]["path"] == "pa"


def test_merge_updates_an_undecided_item_but_keeps_its_state():
    existing = [ix.new_item("a", "A", "pa")]
    incoming = [{"item_id": "a", "title": "A better title", "path": "",
                 "origin": "crew:code_task:Qwen", "state": "", "decision": "",
                 "note": "", "anchor": "", "decided_at": ""}]
    merged = ix.merge(existing, incoming)
    assert merged[0]["title"] == "A better title"
    assert merged[0]["path"] == "pa"          # empty incoming value does not erase
    assert merged[0]["origin"] == "crew:code_task:Qwen"
    assert merged[0]["state"] == "pending"


def test_merge_does_not_modify_either_input():
    existing = [ix.new_item("a", "A", "pa")]
    incoming = [ix.new_item("b", "B", "pb")]
    before_existing = [dict(i) for i in existing]
    before_incoming = [dict(i) for i in incoming]
    ix.merge(existing, incoming)
    assert existing == before_existing
    assert incoming == before_incoming


def test_pending_and_find():
    a = ix.new_item("a", "A", "pa")
    b = ix.new_item("b", "B", "pb")
    b["state"] = "closed"
    assert [i["item_id"] for i in ix.pending([a, b])] == ["a"]
    assert ix.pending([]) == []
    assert ix.find([a, b], "b")["title"] == "B"
    assert ix.find([a, b], "nope") is None
