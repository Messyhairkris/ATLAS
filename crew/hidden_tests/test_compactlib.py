"""Hidden tests for compactlib.py. The author never sees these.

Kris 2026-10-27: the compact must be a ready built system - the meter's numbers, the stages
thresholds, and what the summary keeps, all decided here.
"""

import json

import compactlib as c


# ---- constants -------------------------------------------------------------------------

def test_the_keeps_and_defaults_are_the_studied_ones():
    assert c.STAGE_ORDER == ("none", "light", "medium", "heavy", "critical")
    assert c.DEFAULT_STAGES == {"light": 0.60, "medium": 0.75, "heavy": 0.85, "critical": 0.95}
    assert c.REASONING_KEEP == 500
    assert c.TOOL_RESULT_KEEP == 2000
    assert c.MESSAGE_KEEP == 10000


# ---- stages_from -----------------------------------------------------------------------

def test_stages_from_a_missing_or_wrong_config_is_the_defaults():
    for bad in (None, "# no stages", [], 7, {}, {"meter": {"amber": 0.7}}):
        assert c.stages_from(bad) == {k: v for k, v in c.DEFAULT_STAGES.items()}


def test_stages_from_takes_a_real_number_and_keeps_the_default_for_the_rest():
    assert c.stages_from({"stages": {"medium": 0.8}}) == {
        "light": 0.60, "medium": 0.8, "heavy": 0.85, "critical": 0.95}


def test_stages_from_ignores_non_numbers_and_bools_and_unknown_names():
    got = c.stages_from({"stages": {"heavy": "big", "light": True, "extra": 0.1, "medium": 0.5}})
    assert got == {"light": 0.60, "medium": 0.5, "heavy": 0.85, "critical": 0.95}
    assert set(got) == {"light", "medium", "heavy", "critical"}


def test_stages_from_accepts_whole_numbers():
    assert c.stages_from({"stages": {"critical": 1}})["critical"] == 1.0


# ---- stage_of --------------------------------------------------------------------------

def test_stage_of_the_whole_table():
    s = dict(c.DEFAULT_STAGES)
    assert c.stage_of(0.0, s) == "none"
    assert c.stage_of(0.59, s) == "none"
    assert c.stage_of(0.60, s) == "light"
    assert c.stage_of(0.74, s) == "light"
    assert c.stage_of(0.75, s) == "medium"
    assert c.stage_of(0.849, s) == "medium"
    assert c.stage_of(0.85, s) == "heavy"
    assert c.stage_of(0.949, s) == "heavy"
    assert c.stage_of(0.95, s) == "critical"
    assert c.stage_of(1.2, s) == "critical"


def test_stage_of_is_none_without_thresholds_to_compare():
    assert c.stage_of(0.8, {}) == "none"
    assert c.stage_of(0.8, {"light": "x", "medium": None}) == "none"


def test_stage_of_skips_a_missing_stage_but_keeps_going():
    # with only light and critical set, 0.9 has passed light but not critical
    assert c.stage_of(0.9, {"light": 0.6, "critical": 0.95}) == "light"


# ---- context_used ----------------------------------------------------------------------

def test_context_used_reads_input_plus_cache_read():
    assert c.context_used({"tokens": {"input": 702, "cache": {"read": 115200}}}) == 115902


def test_context_used_missing_cache_counts_only_input():
    assert c.context_used({"tokens": {"input": 287}}) == 287
    assert c.context_used({"tokens": {"input": 287, "cache": "nope"}}) == 287


def test_context_used_junk_is_zero():
    assert c.context_used({"role": "user"}) == 0
    assert c.context_used(None) == 0
    assert c.context_used("assistant") == 0
    assert c.context_used({"tokens": {"input": True, "cache": {"read": False}}}) == 0
    assert c.context_used({"tokens": {"input": None}}) == 0


def test_context_used_floors_a_float():
    assert c.context_used({"tokens": {"input": 10.9, "cache": {"read": 0.9}}}) == 10


# ---- newest_fill -----------------------------------------------------------------------

def test_newest_fill_skips_the_streaming_last_message():
    messages = [
        {"role": "user", "time": {"created": 1}},
        {"role": "assistant", "time": {"created": 2, "completed": 3},
         "tokens": {"input": 100, "output": 5, "cache": {"read": 900}}},
        {"role": "assistant", "time": {"created": 4},
         "tokens": {"input": 0, "output": 0, "cache": {"read": 0}}},
    ]
    assert c.newest_fill(messages) == 1000


def test_newest_fill_is_the_newest_finished_one():
    messages = [
        {"role": "assistant", "time": {"created": 1, "completed": 2},
         "tokens": {"input": 10, "cache": {"read": 90}}},
        {"role": "assistant", "time": {"created": 3, "completed": 4},
         "tokens": {"input": 20, "cache": {"read": 180}}},
    ]
    assert c.newest_fill(messages) == 200


def test_newest_fill_zero_when_nothing_qualifies():
    assert c.newest_fill([]) == 0
    assert c.newest_fill(None) == 0
    assert c.newest_fill([{"role": "user", "time": {"completed": 1}}]) == 0
    # finished but no usage reported: skipped, so the search keeps going and finds nothing
    assert c.newest_fill([{"role": "assistant", "time": {"completed": 1},
                           "tokens": {"input": 0, "cache": {"read": 0}}}]) == 0


def test_newest_fill_skips_a_finished_message_with_no_usage_for_an_older_one():
    # a finished assistant message that reported zero tokens (an aborted turn) is skipped,
    # and the search continues to the older finished one that carries the real fill
    messages = [
        {"role": "assistant", "time": {"created": 1, "completed": 2},
         "tokens": {"input": 10, "cache": {"read": 90}}},
        {"role": "assistant", "time": {"created": 3, "completed": 4},
         "tokens": {"input": 0, "output": 0, "cache": {"read": 0}}},
    ]
    assert c.newest_fill(messages) == 100


def test_newest_fill_ignores_a_user_message_even_with_usage():
    messages = [
        {"role": "assistant", "time": {"created": 1, "completed": 2},
         "tokens": {"input": 5, "cache": {"read": 5}}},
        {"role": "user", "time": {"created": 3, "completed": 4},
         "tokens": {"input": 999, "cache": {"read": 1000}}},
    ]
    assert c.newest_fill(messages) == 10


# ---- truncate --------------------------------------------------------------------------

def test_truncate_leaves_a_short_string_alone():
    assert c.truncate("abc", 500) == "abc"
    assert c.truncate("x" * 500, 500) == "x" * 500


def test_truncate_cuts_and_marks_exactly():
    got = c.truncate("x" * 600, 500)
    assert got == "x" * 500 + "\n...[trimmed: 600 chars, kept 500]"


def test_truncate_non_string_is_empty():
    assert c.truncate(None, 10) == ""
    assert c.truncate(42, 10) == ""


# ---- summary_input ---------------------------------------------------------------------

def test_summary_input_prepends_the_template_then_a_block_per_message():
    out = c.summary_input([{"role": "user", "text": "Compact this chat."}], "# Summary input")
    assert out == "# Summary input\n\n## user\nCompact this chat."


def test_summary_input_without_template_or_messages():
    assert c.summary_input([], "") == ""
    assert c.summary_input([], None) == ""
    assert c.summary_input([], "# Only a template") == "# Only a template"


def test_summary_input_keeps_the_messages_when_the_template_is_empty():
    # the template and the messages are independent: an empty template is not an empty answer
    assert c.summary_input([{"role": "user", "text": "hi"}], "") == "## user\nhi"
    assert c.summary_input([{"role": "user", "text": "hi"}], None) == "## user\nhi"


def test_summary_input_keeps_tool_names_and_inputs():
    out = c.summary_input(
        [{"role": "assistant", "text": "done", "tools": [{"name": "read", "input": {"b": 1, "a": 2}}]}],
        "")
    assert out.startswith("## assistant\ndone")          # the conclusion, then the tool
    assert 'tool read({"a": 2, "b": 1})' in out          # inputs are stable JSON


def test_summary_input_cuts_reasoning_and_truncates_a_long_result():
    out = c.summary_input(
        [{"role": "assistant", "text": "ok", "reasoning": "r" * 700,
          "results": [{"name": "grep", "output": "y" * 2500}]}], "")
    assert "reasoning: " + "r" * 500 + "\n...[trimmed: 700 chars, kept 500]" in out
    assert "result grep: " + "y" * 2000 + "\n...[trimmed: 2500 chars, kept 2000]" in out


def test_summary_input_omits_empty_reasoning():
    out = c.summary_input([{"role": "assistant", "text": "hi", "reasoning": ""}], "")
    assert "reasoning:" not in out


def test_summary_input_caps_a_very_long_text():
    out = c.summary_input([{"role": "user", "text": "z" * 12000}], "")
    assert "z" * 10000 + "\n...[trimmed: 12000 chars, kept 10000]" in out


def test_summary_input_a_message_with_nothing_still_gets_its_heading():
    out = c.summary_input([{"role": "assistant"}], "")
    assert out == "## assistant"


def test_summary_input_a_non_string_result_output_renders_empty():
    out = c.summary_input([{"role": "assistant", "results": [{"name": "grep", "output": None}]}], "")
    assert out == "## assistant\nresult grep: "


def test_summary_input_drops_empty_lines_but_keeps_a_whitespace_one():
    # only a truly empty line is dropped; a line that is one space is text
    assert c.summary_input([{"role": "user", "text": " "}], "") == "## user\n "
