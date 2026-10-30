"""Hidden tests for projects_lib.py (Project folders' pure model). The author never sees these."""

import pytest

import projects_lib as pl


def test_unsorted_is_the_name_of_the_main_place():
    assert pl.UNSORTED == "Unsorted"


# make ---------------------------------------------------------------------------------

def test_make_strips_the_name_and_the_description():
    p = pl.make("  The Crew  ", "  the control room  ")
    assert p["name"] == "The Crew" and p["description"] == "the control room"


def test_make_defaults_to_no_description_tags_links_or_chats():
    assert pl.make("x") == {"name": "x", "description": "", "tags": [], "links": [], "chats": []}


def test_make_cleans_tags_keeping_order_and_dropping_empties_and_duplicates():
    p = pl.make("x", tags=["ui", "ui", " harness ", "", "ui"])
    assert p["tags"] == ["ui", "harness"]


def test_make_cleans_links_the_same_way():
    p = pl.make("x", links=[" https://a ", "https://a", "https://b"])
    assert p["links"] == ["https://a", "https://b"]


def test_make_treats_none_tags_and_links_as_empty():
    p = pl.make("x", tags=None, links=None)
    assert p["tags"] == [] and p["links"] == []


@pytest.mark.parametrize("name", ["", "   ", None, 7])
def test_make_rejects_a_missing_name(name):
    with pytest.raises(ValueError):
        pl.make(name)


# place --------------------------------------------------------------------------------

def test_place_appends_the_chat():
    assert pl.place(pl.make("x"), "ses_a")["chats"] == ["ses_a"]


def test_place_is_idempotent():
    once = pl.place(pl.make("x"), "ses_a")
    assert pl.place(once, "ses_a")["chats"] == ["ses_a"]


def test_place_does_not_mutate_the_project_given():
    p = pl.make("x")
    pl.place(p, "ses_a")
    assert p["chats"] == []


def test_place_returns_a_new_dict():
    p = pl.make("x")
    assert pl.place(p, "ses_a") is not p


@pytest.mark.parametrize("chat", ["", None, 3])
def test_place_rejects_a_missing_chat(chat):
    with pytest.raises(ValueError):
        pl.place(pl.make("x"), chat)


# remove -------------------------------------------------------------------------------

def test_remove_drops_the_chat():
    assert pl.remove(pl.place(pl.make("x"), "ses_a"), "ses_a")["chats"] == []


def test_remove_of_a_chat_that_is_not_there_is_not_an_error():
    p = pl.place(pl.make("x"), "ses_a")
    assert pl.remove(p, "ses_b")["chats"] == ["ses_a"]


def test_remove_does_not_mutate_the_project_given():
    p = pl.place(pl.make("x"), "ses_a")
    pl.remove(p, "ses_a")
    assert p["chats"] == ["ses_a"]


# locate and duplicates ------------------------------------------------------------------

def test_locate_finds_the_project_that_holds_the_chat():
    assert pl.locate([pl.place(pl.make("The Crew"), "ses_a")], "ses_a") == "The Crew"


def test_locate_returns_unsorted_when_no_project_holds_it():
    assert pl.locate([pl.place(pl.make("The Crew"), "ses_a")], "ses_z") == pl.UNSORTED


def test_locate_refuses_a_chat_in_two_projects():
    with pytest.raises(ValueError):
        pl.locate([pl.place(pl.make("A"), "ses_a"), pl.place(pl.make("B"), "ses_a")], "ses_a")


def test_duplicates_is_empty_when_no_chat_is_twice():
    assert pl.duplicates([pl.place(pl.make("A"), "ses_a"), pl.place(pl.make("B"), "ses_b")]) == []


def test_duplicates_names_a_chat_held_twice_once():
    assert pl.duplicates([pl.place(pl.make("A"), "ses_a"), pl.place(pl.make("B"), "ses_a")]) == ["ses_a"]


# groups -------------------------------------------------------------------------------

def test_groups_follows_the_callers_chat_order_not_the_placement_order():
    projects = [pl.place(pl.place(pl.make("The Crew"), "ses_b"), "ses_a")]
    got = pl.groups(projects, ["ses_a", "ses_b"])
    assert got[0]["chats"] == ["ses_a", "ses_b"]
    assert pl.groups(projects, ["ses_b", "ses_a"])[0]["chats"] == ["ses_b", "ses_a"]


def test_groups_puts_unsorted_last_with_the_unclaimed_chats():
    projects = [pl.place(pl.make("The Crew"), "ses_b")]
    got = pl.groups(projects, ["ses_a", "ses_b", "ses_c"])
    assert [g["name"] for g in got] == ["The Crew", "Unsorted"]
    assert got[-1]["chats"] == ["ses_a", "ses_c"]
    assert got[-1]["description"] == "Not in a project"
    assert got[-1]["tags"] == [] and got[-1]["links"] == []


def test_groups_gives_a_project_with_no_chats_an_entry():
    got = pl.groups([pl.make("The Crew")], ["ses_a"])
    assert [g["name"] for g in got] == ["The Crew", "Unsorted"]
    assert got[0]["chats"] == []


def test_groups_with_no_projects_is_only_unsorted():
    got = pl.groups([], ["ses_a", "ses_b"])
    assert len(got) == 1 and got[0]["name"] == "Unsorted" and got[0]["chats"] == ["ses_a", "ses_b"]


def test_groups_shows_a_duplicated_chat_once_in_the_first_project():
    projects = [pl.place(pl.make("A"), "ses_a"), pl.place(pl.make("B"), "ses_a")]
    got = pl.groups(projects, ["ses_a"])
    assert got[0]["chats"] == ["ses_a"]
    assert got[1]["chats"] == []
    assert got[-1]["chats"] == []


def test_groups_carries_the_description_tags_and_links_through():
    p = pl.make("The Crew", "the control room", ["ui"], ["https://x"])
    got = pl.groups([p], [])
    assert got[0]["description"] == "the control room"
    assert got[0]["tags"] == ["ui"] and got[0]["links"] == ["https://x"]


def test_groups_keeps_the_projects_in_the_order_given():
    got = pl.groups([pl.make("B"), pl.make("A")], [])
    assert [g["name"] for g in got] == ["B", "A", "Unsorted"]
