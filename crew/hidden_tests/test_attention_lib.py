"""Hidden tests for attention_lib.py (which conversations need you). The author never sees these."""

import pytest

import attention_lib as al


def test_states_are_the_four_in_order():
    assert al.STATES == ("needs_attention", "finished", "working", "idle")


def test_default_quiet_is_two_minutes():
    assert al.DEFAULT_QUIET_S == 120


# state_for ------------------------------------------------------------------------------

@pytest.mark.parametrize("now,last_activity,last_read,running,alive,finished_at,quiet_s,expected", [
    (1000, 988, 900, True, True, None, 120, "working"),
    (1000, 880, 900, True, True, None, 120, "needs_attention"),
    (1000, 900, 900, True, True, None, 120, "working"),
    (1000, None, None, True, True, None, 120, "working"),
    (1000, 988, None, True, False, None, 120, "needs_attention"),
    (1000, 980, 900, False, None, 990, 120, "finished"),
    (1000, 998, 995, False, None, 990, 120, "needs_attention"),
    (1000, 980, None, False, None, None, 120, "needs_attention"),
    (1000, 1000, 999, False, None, None, 120, "needs_attention"),
    (1000, 980, 980, False, None, None, 120, "idle"),
    (1000, None, None, False, None, None, 120, "idle"),
    (1000, 880, 900, True, True, None, 0, "needs_attention"),
])
def test_the_contract_table(now, last_activity, last_read, running, alive, finished_at, quiet_s, expected):
    assert al.state_for(now, last_activity=last_activity, last_read=last_read, running=running,
                        alive=alive, finished_at=finished_at, quiet_s=quiet_s) == expected


def test_a_dead_run_needs_attention_even_when_it_looks_busy():
    got = al.state_for(1000, last_activity=999, last_read=900, running=True, alive=False)
    assert got == "needs_attention", "the process is gone; it will never finish"


def test_an_unknown_alive_does_not_count_as_dead():
    assert al.state_for(1000, last_activity=988, last_read=900, running=True, alive=None) == "working"


def test_activity_exactly_quiet_seconds_old_is_already_needy():
    assert al.state_for(1120, last_activity=1000, running=True, quiet_s=120) == "needs_attention"
    assert al.state_for(1119, last_activity=1000, running=True, quiet_s=120) == "working"


def test_a_run_that_just_started_has_nothing_to_read_yet():
    assert al.state_for(1000, running=True, quiet_s=120) == "working"


def test_a_finish_since_the_read_reads_as_finished():
    assert al.state_for(1000, last_activity=980, last_read=900, finished_at=990) == "finished"


def test_a_finish_older_than_the_read_falls_through():
    assert al.state_for(1000, last_activity=980, last_read=995, finished_at=990) == "idle"


def test_a_finish_beats_earlier_plain_activity():
    got = al.state_for(1000, last_activity=985, last_read=900, finished_at=990)
    assert got == "finished"


def test_never_read_with_any_activity_is_needy():
    assert al.state_for(1000, last_activity=1, last_read=None) == "needs_attention"


def test_never_read_with_a_finish_reads_as_finished():
    assert al.state_for(1000, last_activity=1, finished_at=2, last_read=None) == "finished"


def test_nothing_ever_happened_is_idle():
    assert al.state_for(1000) == "idle"


def test_reading_exactly_when_it_happened_is_idle():
    assert al.state_for(1000, last_activity=1000, last_read=1000) == "idle"


# label ----------------------------------------------------------------------------------

@pytest.mark.parametrize("state,expected", [
    ("needs_attention", "needs attention"),
    ("finished", "finished"),
    ("working", "working"),
    ("idle", "idle"),
])
def test_label_phrases(state, expected):
    assert al.label(state) == expected


@pytest.mark.parametrize("state", [None, "", "nonsense", 7])
def test_an_unknown_state_labels_as_idle(state):
    assert al.label(state) == "idle"


# folder_state --------------------------------------------------------------------------

def test_a_needing_conversation_marks_the_folder():
    assert al.folder_state(["idle", "needs_attention", "working"]) == "needs_attention"


def test_a_finished_conversation_marks_the_folder_when_none_needs_attention():
    assert al.folder_state(["idle", "finished", "working"]) == "finished"


def test_working_marks_the_folder_when_nothing_is_finished():
    assert al.folder_state(["idle", "working"]) == "working"


def test_an_idle_folder_is_idle():
    assert al.folder_state(["idle", "idle"]) == "idle"


def test_an_empty_or_missing_folder_is_idle():
    assert al.folder_state([]) == "idle"
    assert al.folder_state(None) == "idle"


def test_only_unknown_states_are_idle():
    assert al.folder_state(["nonsense", ""]) == "idle"
