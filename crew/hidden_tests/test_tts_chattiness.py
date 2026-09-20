"""Hidden tests for chattiness.py."""

import pytest

import chattiness as c

ALL_EVENTS = ("error", "mode_change", "read_back", "command_applied",
              "block_created", "dictation_word", "edit_applied",
              "punctuation", "whitespace")


def test_levels_and_events():
    assert c.LEVELS == ("off", "brief", "normal", "full", "verbatim")
    assert set(c.EVENTS) == set(ALL_EVENTS)
    assert len(c.EVENTS) == 9


@pytest.mark.parametrize("event,quietest", [
    ("error", "brief"), ("mode_change", "brief"), ("read_back", "brief"),
    ("command_applied", "normal"), ("block_created", "normal"),
    ("dictation_word", "full"), ("edit_applied", "full"),
    ("punctuation", "verbatim"), ("whitespace", "verbatim"),
])
def test_speaks_from_table(event, quietest):
    assert c.SPEAKS_FROM[event] == quietest


@pytest.mark.parametrize("level,index", [
    ("off", 0), ("brief", 1), ("normal", 2), ("full", 3), ("verbatim", 4)])
def test_level_index(level, index):
    assert c.level_index(level) == index


def test_level_index_rejects_nonsense():
    with pytest.raises(ValueError):
        c.level_index("loud")


@pytest.mark.parametrize("event", ALL_EVENTS)
def test_off_says_nothing_at_all(event):
    assert c.should_speak(event, "off") is False


@pytest.mark.parametrize("event", ALL_EVENTS)
def test_verbatim_says_everything(event):
    assert c.should_speak(event, "verbatim") is True


def test_normal_level_boundary():
    assert c.should_speak("error", "normal") is True
    assert c.should_speak("command_applied", "normal") is True
    assert c.should_speak("dictation_word", "normal") is False
    assert c.should_speak("punctuation", "normal") is False


def test_brief_level_boundary():
    assert c.should_speak("error", "brief") is True
    assert c.should_speak("read_back", "brief") is True
    assert c.should_speak("command_applied", "brief") is False


def test_full_level_boundary():
    assert c.should_speak("dictation_word", "full") is True
    assert c.should_speak("edit_applied", "full") is True
    assert c.should_speak("whitespace", "full") is False


def test_each_level_includes_the_quieter_ones():
    for event in ALL_EVENTS:
        spoken = [lvl for lvl in c.LEVELS if c.should_speak(event, lvl)]
        # once an event starts speaking it never goes quiet again
        assert spoken == list(c.LEVELS)[c.level_index(c.SPEAKS_FROM[event]):], event


def test_unknown_event_or_level_raises():
    with pytest.raises(ValueError):
        c.should_speak("telepathy", "normal")
    with pytest.raises(ValueError):
        c.should_speak("error", "whisper")


@pytest.mark.parametrize("event,payload,said", [
    ("error", {"message": "microphone lost"}, "error: microphone lost"),
    ("mode_change", {"mode": "command"}, "command mode"),
    ("read_back", {"text": "the quick brown fox"}, "the quick brown fox"),
    ("command_applied", {"command": "heading two"}, "heading two applied"),
    ("block_created", {"block": "bullet list"}, "new bullet list"),
    ("dictation_word", {"word": "hello"}, "hello"),
    ("edit_applied", {"what": "colour", "to": "color"}, "colour changed to color"),
    ("punctuation", {"name": "comma"}, "comma"),
    ("whitespace", {"name": "line break"}, "line break"),
])
def test_describe(event, payload, said):
    assert c.describe(event, payload) == said


def test_describe_rejects_an_unknown_event():
    with pytest.raises(ValueError):
        c.describe("telepathy", {})


def test_describe_refuses_to_invent_a_missing_value():
    with pytest.raises(KeyError):
        c.describe("error", {})
    with pytest.raises(KeyError):
        c.describe("edit_applied", {"what": "colour"})
