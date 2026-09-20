"""Hidden tests for review_rules.py. The author never sees these.

Kris's rule under test: approval needs no explanation, rejections and questions
do.
"""

import review_rules as r


def test_constants():
    assert r.DECISIONS == ("approve", "reject", "question", "defer")
    assert set(r.NEEDS_NOTE) == {"reject", "question", "defer"}
    assert r.MIN_NOTE_CHARS == 12


def test_approve_needs_no_note():
    assert r.validate("approve", "") == []
    assert r.validate("approve", "   ") == []


def test_approve_may_still_carry_a_note():
    assert r.validate("approve", "nicely done, ship it") == []


def test_reject_and_question_and_defer_need_words():
    for decision in ("reject", "question", "defer"):
        problems = r.validate(decision, "")
        assert len(problems) == 1, decision
        assert "note" in problems[0].lower(), problems
        assert r.validate(decision, "no") != []
        assert r.validate(decision, "           ") != []
        assert r.validate(decision, "this drops alerts") == []


def test_a_whitespace_note_counts_as_absent():
    assert r.validate("reject", "\n\t   \n") != []


def test_unknown_decision_is_reported():
    problems = r.validate("maybe", "a perfectly good long note")
    assert len(problems) == 1
    assert "decision" in problems[0].lower()


def test_an_unknown_decision_yields_only_the_decision_problem():
    """The note rule covers reject/question/defer; an unrecognised decision is not
    one of them, so there is nothing to say about its note."""
    problems = r.validate("maybe", "")
    assert len(problems) == 1
    assert "decision" in problems[0].lower()


def test_a_problem_reads_as_a_sentence_a_person_can_act_on():
    """The first version returned bare "note", which is true and useless: the
    desk had to write its own wording. A problem string is shown to a human."""
    for decision in ("reject", "question", "defer"):
        problem = r.validate(decision, "")[0]
        assert len(problem) >= 30, f"{decision}: {problem!r} is not a sentence"
        assert decision in problem.lower(), f"{decision}: {problem!r}"
        assert str(r.MIN_NOTE_CHARS) in problem or "character" in problem.lower(),             f"{decision}: say how much is needed - {problem!r}"
    bad = r.validate("maybe", "a perfectly good long note")[0]
    assert len(bad) >= 30 and "maybe" in bad, bad


def test_is_complete():
    assert r.is_complete({"decision": "approve", "note": ""}) is True
    assert r.is_complete({"decision": "reject", "note": "the ids skip a number"}) is True
    assert r.is_complete({"decision": "reject", "note": "no"}) is False
    assert r.is_complete({"decision": "", "note": ""}) is False
    assert r.is_complete({}) is False


def test_next_action_for_each_decision():
    assert r.next_action({"decision": "", "note": ""}) == "wait for the human"
    assert r.next_action({"decision": "approve", "note": ""}) == "apply the work"
    assert r.next_action({"decision": "reject", "note": "alerts are dropped"}) \
        == "revise the work using the note"
    assert r.next_action({"decision": "question", "note": "why two endpoints?"}) \
        == "answer the question, then ask again"
    assert r.next_action({"decision": "defer", "note": "after the release"}) \
        == "leave it queued"


def test_incomplete_beats_the_decision():
    assert r.next_action({"decision": "reject", "note": "no"}) \
        == "ask the human for a reason"
    assert r.next_action({"decision": "question", "note": ""}) \
        == "ask the human for a reason"


def test_summarize_counts_every_key_even_at_zero():
    out = r.summarize([])
    assert out == {"total": 0, "pending": 0, "approve": 0, "reject": 0,
                   "question": 0, "defer": 0, "incomplete": 0}


def test_summarize_a_real_queue():
    items = [{"item_id": "a", "decision": "approve", "note": ""},
             {"item_id": "b", "decision": "reject", "note": "the queue drops alerts"},
             {"item_id": "c", "decision": "reject", "note": "no"},
             {"item_id": "d", "decision": "", "note": ""},
             {"item_id": "e", "decision": "defer", "note": "after the release"}]
    out = r.summarize(items)
    assert out["total"] == 5
    assert out["pending"] == 1
    assert out["approve"] == 1
    assert out["reject"] == 2
    assert out["defer"] == 1
    assert out["question"] == 0
    assert out["incomplete"] == 1


def test_agent_digest_worked_example():
    items = [{"item_id": "a", "decision": "approve", "note": ""},
             {"item_id": "b", "decision": "reject", "note": "the queue drops alerts"},
             {"item_id": "c", "decision": "reject", "note": "no"},
             {"item_id": "d", "decision": "", "note": ""},
             {"item_id": "e", "decision": "defer", "note": "after the release"}]
    assert r.agent_digest(items) == {
        "needs_agent": True,
        "waiting_on_human": 1,
        "waiting_on_agent": ["a", "b"],
        "needs_human_again": ["c"],
        "actions": {"a": "apply the work",
                    "b": "revise the work using the note",
                    "c": "ask the human for a reason",
                    "d": "wait for the human",
                    "e": "leave it queued"}}


def test_a_defer_never_wakes_the_agent():
    items = [{"item_id": "e", "decision": "defer", "note": "after the release"}]
    digest = r.agent_digest(items)
    assert digest["needs_agent"] is False
    assert digest["waiting_on_agent"] == []


def test_empty_queue_digest():
    assert r.agent_digest([]) == {"needs_agent": False, "waiting_on_human": 0,
                                 "waiting_on_agent": [], "needs_human_again": [],
                                 "actions": {}}
