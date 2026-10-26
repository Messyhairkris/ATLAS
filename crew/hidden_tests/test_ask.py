"""Hidden tests for ask.py. Every contract row, plus what a model actually writes."""

import pytest

import ask

U = ask.USAGE
Q2 = {"question": "Which file?", "options": ["a.md", "b.md"]}


def test_constants_verbatim():
    assert (ask.QUESTION_MAX_CHARS, ask.OPTION_MAX_CHARS) == (400, 80)
    assert U == ('ask needs {"question": "...", "options": ["...", "..."]} - options are '
                 'optional: none, or 2 to 4')
    assert ask.HINT == (
        'STUCK? If you cannot tell how to get past this, ask ONE question instead of '
        'repeating yourself: {"tool": "ask", "args": {"question": "...", "options": '
        '["...", "..."]}}. The job pauses until it is answered.')


@pytest.mark.parametrize("args, want", [
    ("why?", (None, U)),
    (None, (None, U)),
    ({}, (None, U)),
    ({"question": 3}, (None, U)),
    ({"question": "  \n "}, (None, "ask: the question is empty")),
    ({"question": "q" * 401}, (None, "ask: keep the question to at most 400 characters")),
    ({"question": "Which file?", "options": "a.md"}, (None, U)),
    ({"question": "Which?", "options": ["a", 2]}, (None, U)),
    ({"question": "Which?", "options": ["a", " "]}, (None, "ask: an option is empty")),
    ({"question": "Which?", "options": ["a", "b" * 81]},
     (None, "ask: keep each option to at most 80 characters")),
    ({"question": "Which?", "options": ["only"]}, (None, "ask: give 2 to 4 options, or none")),
    ({"question": "Which?", "options": ["a", "b", "c", "d", "e"]},
     (None, "ask: give 2 to 4 options, or none")),
    ({"question": "Which?", "options": ["Yes", "yes "]}, (None, "ask: two options are the same")),
    ({"question": " Which\n file? ", "options": [" a.md ", "b.md"]},
     ({"question": "Which file?", "options": ["a.md", "b.md"]}, "")),
    ({"question": "Why?"}, ({"question": "Why?", "options": []}, "")),
    ({"question": "Why?", "options": None, "x": 1}, ({"question": "Why?", "options": []}, "")),
])
def test_parse_question(args, want):
    assert ask.parse_question(args) == want


def test_limits_are_inclusive():
    q, err = ask.parse_question({"question": "q" * 400, "options": ["o" * 80, "p" * 80]})
    assert err == "" and len(q["question"]) == 400
    q, err = ask.parse_question({"question": "Pick", "options": ["a", "b", "c", "d"]})
    assert err == "" and q["options"] == ["a", "b", "c", "d"]


def test_length_is_judged_after_cleaning():
    q, err = ask.parse_question({"question": "  " + "w " * 200 + "  "})
    assert err == "" and len(q["question"]) == 399
    q, err = ask.parse_question({"question": "Q", "options": ["  " + "o" * 80 + "\n", "b"]})
    assert err == "" and q["options"][0] == "o" * 80


def test_rule_order_question_before_options():
    # an empty question is reported even when the options are also wrong
    assert ask.parse_question({"question": "", "options": "x"}) == (
        None, "ask: the question is empty")
    # a non-string option is reported before the count rule
    assert ask.parse_question({"question": "Q", "options": [1]}) == (None, U)
    # an empty option is reported before a duplicate
    assert ask.parse_question({"question": "Q", "options": ["a", "A", ""]}) == (
        None, "ask: an option is empty")


def test_parse_does_not_change_its_input():
    args = {"question": " Q ", "options": [" a ", "b"]}
    ask.parse_question(args)
    assert args == {"question": " Q ", "options": [" a ", "b"]}


@pytest.mark.parametrize("question, reply, want", [
    (Q2, " 2 ", "b.md"),
    (Q2, "1.", "a.md"),
    (Q2, "3", "3"),
    (Q2, "0", "0"),
    (Q2, "2..", "2.."),
    (Q2, "b.md", "b.md"),
    (Q2, "option 2", "option 2"),
    ({"question": "Q", "options": []}, " use the README ", "use the README"),
    ({"question": "Q", "options": []}, "1", "1"),
    # str.isdigit() is True for these and int() then raises or reads them (review, 2026-10-26)
    (Q2, "²", "²"),
    (Q2, "٢", "٢"),
    (Q2, "1²", "1²"),
])
def test_pick_answer(question, reply, want):
    assert ask.pick_answer(question, reply) == want


def test_answer_constraint_with_options():
    assert ask.answer_constraint(Q2, "2") == (
        "ANSWER TO YOUR QUESTION\nYou asked: Which file?\nOptions were: a.md | b.md\n"
        "Answer: b.md\nCarry on with this answer. Do not ask the same question again.")


def test_answer_constraint_without_options():
    assert ask.answer_constraint({"question": "Why?", "options": []}, "because") == (
        "ANSWER TO YOUR QUESTION\nYou asked: Why?\nAnswer: because\n"
        "Carry on with this answer. Do not ask the same question again.")


def test_answer_constraint_free_text_with_options():
    out = ask.answer_constraint(Q2, "  neither - use c.md  ")
    assert out.split("\n")[3] == "Answer: neither - use c.md"


@pytest.mark.parametrize("asked, want", [
    (False, ask.HINT), (True, ""), (0, ask.HINT), (1, ""),
])
def test_stuck_hint(asked, want):
    assert ask.stuck_hint(asked) == want
