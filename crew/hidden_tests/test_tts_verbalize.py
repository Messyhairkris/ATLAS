"""Hidden tests for verbalize.py. Every case is in the contract's table."""

import pytest

import verbalize as v


def test_levels_are_the_five_from_the_spec():
    assert v.LEVELS == ("off", "brief", "normal", "full", "verbatim")


@pytest.mark.parametrize("char,name", [
    (",", "comma"), (".", "period"), ("?", "question mark"),
    ("!", "exclamation mark"), ("'", "apostrophe"), ('"', "quote"),
    (";", "semicolon"), (":", "colon"), ("-", "dash"),
    ("(", "open parenthesis"), (")", "close parenthesis"),
    ("\n", "line break"), ("\t", "tab"),
])
def test_punctuation_table(char, name):
    assert v.PUNCTUATION[char] == name


@pytest.mark.parametrize("text,expected", [
    ("a  \n b\t", "a b"), ("", ""), ("   ", ""), ("one", "one"),
    ("  padded  ", "padded"),
])
def test_collapse_whitespace(text, expected):
    assert v.collapse_whitespace(text) == expected


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        v.verbalize("hello", "shouty")


@pytest.mark.parametrize("level", ["off", "brief", "normal", "full", "verbatim"])
def test_empty_text_is_empty_at_every_level(level):
    assert v.verbalize("", level) == ""


def test_off_says_nothing():
    assert v.verbalize("Hello, world.", "off") == ""
    assert v.verbalize("anything at all", "off") == ""


@pytest.mark.parametrize("level", ["brief", "normal", "full"])
def test_ordinary_levels_keep_the_text_as_written(level):
    assert v.verbalize("Hello, world.", level) == "Hello, world."
    assert v.verbalize("two   spaces", level) == "two spaces"
    assert v.verbalize("line one\nline two", level) == "line one line two"


@pytest.mark.parametrize("text,expected", [
    ("Hello, world.", "Hello comma world period"),
    ("don't", "don apostrophe t"),
    ("What?!", "What question mark exclamation mark"),
    ("line one\nline two", "line one line break line two"),
    ("wait...", "wait ellipsis"),
    ("a (b) c", "a open parenthesis b close parenthesis c"),
    ('say "this"', "say quote this quote"),
    ("a;b:c-d", "a semicolon b colon c dash d"),
    ("tab\there", "tab tab here"),
])
def test_verbatim_names_every_mark(text, expected):
    assert v.verbalize(text, "verbatim") == expected


def test_ellipsis_beats_three_separate_periods():
    assert v.verbalize("hold on....", "verbatim") == "hold on ellipsis"
    assert v.verbalize("a.b", "verbatim") == "a period b"


def test_verbatim_result_is_single_spaced_and_trimmed():
    out = v.verbalize("  Hello ,  world .  ", "verbatim")
    assert out == "Hello comma world period"
    assert "  " not in out and out == out.strip()


def test_characters_outside_the_table_are_untouched():
    assert v.verbalize("café #1", "verbatim") == "café #1"
    assert v.verbalize("100% done", "verbatim") == "100% done"


def test_a_mark_on_its_own_is_still_named():
    assert v.verbalize(",", "verbatim") == "comma"
    assert v.verbalize("\n", "verbatim") == "line break"


def test_default_level_is_normal():
    assert v.verbalize("Hello, world.") == "Hello, world."
