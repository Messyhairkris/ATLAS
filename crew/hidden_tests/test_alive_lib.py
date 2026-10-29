"""Hidden tests for alive_lib.py. The author never sees these.

Kris after the crash: "there is no way for me to tell if it's still processing or just appears to
be." The rule the crash taught: a turn that started before the engine now running can never finish.
"""

import alive_lib as a


# ---- constants -------------------------------------------------------------------------

def test_states_and_default_quiet():
    assert a.STATES == ("WORKING", "QUIET", "DEAD", "STEPS")
    assert a.DEFAULT_QUIET_S == 120
    assert a.MAX_STEPS_MARKER == "CRITICAL - MAXIMUM STEPS REACHED"


# ---- state_of --------------------------------------------------------------------------

def test_a_recent_activity_is_working():
    assert a.state_of(1000, activity=988, alive=True) == "WORKING"
    assert a.state_of(1000, activity=881, alive=True) == "WORKING"      # 119 s, under the line


def test_an_activity_exactly_at_the_quiet_line_is_quiet():
    assert a.state_of(1000, activity=880, alive=True) == "QUIET"        # the line is strict
    assert a.state_of(1000, activity=879, alive=True) == "QUIET"
    assert a.state_of(1000, activity=60, alive=True) == "QUIET"


def test_no_activity_yet_is_quiet():
    assert a.state_of(1000, alive=True) == "QUIET"


def test_a_gone_process_is_dead():
    assert a.state_of(1000, activity=988, alive=False) == "DEAD"


def test_a_turn_that_started_before_the_engine_is_dead():
    assert a.state_of(1000, started=100, activity=900, engine_start=500, alive=True) == "DEAD"


def test_starting_with_the_engine_is_not_before_it():
    assert a.state_of(1000, started=500, activity=900, engine_start=500, alive=True) == "WORKING"


def test_without_an_engine_start_the_rule_cannot_fire():
    assert a.state_of(1000, started=100, activity=900, alive=True) == "WORKING"


def test_an_unknown_process_is_not_dead():
    assert a.state_of(1000, activity=999, alive=None) == "WORKING"


def test_a_gone_process_wins_over_starting_before_the_engine():
    assert a.state_of(1000, started=100, activity=900, engine_start=500, alive=False) == "DEAD"


def test_a_quiet_s_of_zero_or_less_is_never_working():
    assert a.state_of(1000, activity=999, alive=True, quiet_s=0) == "QUIET"
    assert a.state_of(1000, activity=999, alive=True, quiet_s=-5) == "QUIET"
    # even a future timestamp (a negative age) does not make a zero threshold "working"
    assert a.state_of(1000, activity=1010, alive=True, quiet_s=0) == "QUIET"


def test_a_quiet_s_of_one_works_at_zero_age():
    assert a.state_of(1000, activity=1000, alive=True, quiet_s=1) == "WORKING"   # age 0
    assert a.state_of(1000, activity=999, alive=True, quiet_s=1) == "QUIET"      # age 1


def test_a_custom_quiet_s_is_used():
    assert a.state_of(1000, activity=940, alive=True, quiet_s=30) == "QUIET"
    assert a.state_of(1000, activity=980, alive=True, quiet_s=30) == "WORKING"


def test_junk_times_do_not_crash():
    assert a.state_of(None, activity=None, alive=True) == "QUIET"
    assert a.state_of(1000, activity="x", alive=True) == "QUIET"
    assert a.state_of(1000, started=True, engine_start=0, activity=999, alive=True) == "WORKING"


# ---- STEPS: the step ceiling ended the turn --------------------------------------------

def test_steps_beats_every_other_state():
    # the engine's max-steps notice means the turn answered in text and stopped using tools
    assert a.state_of(1000, activity=988, alive=True, steps=True) == "STEPS"
    assert a.state_of(1000, activity=60, alive=True, steps=True) == "STEPS"
    assert a.state_of(1000, activity=900, alive=False, steps=True) == "STEPS"
    assert a.state_of(1000, started=100, engine_start=500, alive=True, steps=True) == "STEPS"


def test_steps_false_is_not_the_steps_state():
    assert a.state_of(1000, activity=988, alive=True, steps=False) == "WORKING"
    assert a.state_of(1000, activity=988, alive=True) == "WORKING"


def test_steps_notice_only_an_opening_echo():
    assert a.steps_notice({"type": "text", "text": "CRITICAL - MAXIMUM STEPS REACHED\n\nI reached the ceiling."}) is True
    assert a.steps_notice({"type": "text", "text": "   CRITICAL - MAXIMUM STEPS REACHED"}) is True


def test_steps_notice_false_for_a_quote_the_tail_alone_or_another_part():
    assert a.steps_notice({"type": "text", "text": "I read about MAXIMUM STEPS REACHED earlier."}) is False
    assert a.steps_notice({"type": "text", "text": "MAXIMUM STEPS REACHED"}) is False
    assert a.steps_notice({"type": "tool", "tool": "read"}) is False
    # a non-text part is never the notice, even when it carries such a text
    assert a.steps_notice({"type": "tool", "text": "CRITICAL - MAXIMUM STEPS REACHED"}) is False
    assert a.steps_notice({"type": "text"}) is False
    assert a.steps_notice({}) is False
    assert a.steps_notice(None) is False
    assert a.steps_notice("CRITICAL - MAXIMUM STEPS REACHED") is False


def test_hit_ceiling_reaching_the_limit_counts():
    assert a.hit_ceiling(60, 60) is True
    assert a.hit_ceiling(61, 60) is True
    assert a.hit_ceiling(59, 60) is False
    assert a.hit_ceiling(0, 60) is False


def test_hit_ceiling_junk_is_false():
    assert a.hit_ceiling(None, 60) is False
    assert a.hit_ceiling(60, None) is False
    assert a.hit_ceiling(60, 0) is False
    assert a.hit_ceiling(True, 60) is False


def test_the_steps_line():
    assert a.line(1000, activity=988, alive=True, steps=True) == \
        "STEPS    the step ceiling ended this turn (text only); send the next message to continue"
    assert a.line(1000, activity=900, alive=False, steps=True) == \
        "STEPS    the step ceiling ended this turn (text only); send the next message to continue"


# ---- age_of ----------------------------------------------------------------------------

def test_age_of_is_floored_seconds():
    assert a.age_of(1000, 988) == 12
    assert a.age_of(1000.9, 988.0) == 12


def test_age_of_is_none_without_both_times():
    assert a.age_of(1000, None) is None
    assert a.age_of(None, 988) is None
    assert a.age_of("soon", 0) is None


def test_age_of_can_be_negative_and_says_so():
    assert a.age_of(1000, 1010) == -10


# ---- doing_of --------------------------------------------------------------------------

def test_doing_of_names_a_tool():
    assert a.doing_of({"type": "tool", "tool": "read"}) == "tool read"


def test_doing_of_tool_without_a_name():
    assert a.doing_of({"type": "tool", "tool": ""}) == "tool"
    assert a.doing_of({"type": "tool"}) == "tool"


def test_doing_of_other_types_is_the_type():
    assert a.doing_of({"type": "text", "text": "hi"}) == "text"
    assert a.doing_of({"type": "reasoning"}) == "reasoning"
    assert a.doing_of({"type": "step-start"}) == "step-start"


def test_doing_of_nothing_is_empty():
    assert a.doing_of({}) == ""
    assert a.doing_of(None) == ""
    assert a.doing_of({"type": ""}) == ""


# ---- line ------------------------------------------------------------------------------

def test_the_working_line():
    assert a.line(1000, activity=988, alive=True) == "WORKING  last activity 12s ago"
    assert a.line(1000, activity=988, alive=True, doing="tool read") == \
        "WORKING  last activity 12s ago (tool read)"


def test_the_quiet_line():
    assert a.line(1000, activity=60, alive=True) == \
        "QUIET    no activity for 940s, but the process is alive"
    assert a.line(1000, alive=True) == "QUIET    no activity yet, but the process is alive"


def test_the_quiet_line_with_a_junk_activity_says_no_activity_yet():
    assert a.line(1000, activity="x", alive=True) == \
        "QUIET    no activity yet, but the process is alive"


def test_the_dead_lines():
    assert a.line(1000, activity=900, alive=False) == \
        "DEAD     its process is gone; it will never finish - resend"
    assert a.line(1000, started=100, engine_start=500, alive=True) == \
        "DEAD     started before this engine; it will never finish - resend"


def test_the_gone_process_reason_wins_when_both_apply():
    got = a.line(1000, started=100, activity=900, engine_start=500, alive=False)
    assert got == "DEAD     its process is gone; it will never finish - resend"


def test_the_state_word_is_padded_to_one_column():
    # every state is followed by two or more spaces so the header lines up in a fixed-width font
    assert a.line(1000, activity=988, alive=True)[:9] == "WORKING  "
    assert a.line(1000, activity=60, alive=True)[:9] == "QUIET    "
    assert a.line(1000, activity=900, alive=False)[:9] == "DEAD     "
    assert a.line(1000, activity=988, alive=True, steps=True)[:9] == "STEPS    "
