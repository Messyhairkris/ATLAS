"""Hidden tests for inbox.py. Every contract row, the order, and the edges."""

from datetime import datetime

import inbox as ib

NOW = datetime(2026, 10, 26, 12, 0)
SEEN = "2026-10-26T08:00"


def one(**kw):
    args = {"desk": [], "jobs": [], "campaigns": [], "fired": [], "night": None, "now": NOW,
            "seen_at": SEEN}
    args.update(kw)
    return ib.cards(**args)


def test_ranks_verbatim():
    assert ib.RANKS == {"question": 0, "decide": 1, "reminder": 2, "failed": 3,
                        "stale_campaign": 4, "fixer": 5, "try": 6, "finished": 7, "read": 8}


def test_question_card():
    job = {"task_id": "j1", "title": "Digest", "status": "review",
           "question": {"question": "Which run?", "options": ["a", "b"]},
           "finished_at": "2026-10-25T10:00"}
    assert one(jobs=[job]) == [{"kind": "question", "title": "Digest",
                                "detail": "Which run? | a / b", "ref": "j1",
                                "when": "2026-10-25T10:00"}]


def test_question_without_options_and_answered_question():
    job = {"task_id": "j1", "status": "review", "question": {"question": "Why?", "options": []}}
    assert one(jobs=[job])[0]["detail"] == "Why?"
    assert one(jobs=[job])[0]["title"] == "j1"
    asked = {"task_id": "j1", "title": "Digest", "status": "review", "asked": True,
             "question": {"question": "Which run?", "options": ["a"]},
             "finished_at": "2026-10-26T09:00"}
    assert one(jobs=[asked]) == [{"kind": "finished", "title": "Digest", "detail": "? - review",
                                  "ref": "j1", "when": "2026-10-26T09:00"}]


def test_failed_cards():
    job = {"task_id": "j2", "status": "failed", "assigned_to": "Qwen",
           "result": {"stop_reason": "budget_tokens"}, "finished_at": "2026-10-26T09:30"}
    assert one(jobs=[job]) == [{"kind": "failed", "title": "j2", "detail": "Qwen: budget_tokens",
                                "ref": "j2", "when": "2026-10-26T09:30"}]
    assert one(jobs=[{**job, "finished_at": "2026-10-26T07:00"}]) == []
    assert one(jobs=[{**job, "finished_at": ""}]) == []
    bare = {"task_id": "j3", "status": "failed", "finished_at": "2026-10-26T09:00"}
    assert one(jobs=[bare])[0]["detail"] == "?: failed"
    none_result = {**bare, "result": None}
    assert one(jobs=[none_result])[0]["detail"] == "?: failed"


def test_finished_and_other_statuses():
    done = {"task_id": "j4", "title": "T", "status": "completed", "assigned_to": "Hoss",
            "finished_at": "2026-10-26T10:00"}
    assert one(jobs=[done])[0] == {"kind": "finished", "title": "T", "detail": "Hoss - completed",
                                   "ref": "j4", "when": "2026-10-26T10:00"}
    for status in ("ready", "in_progress", "blocked", "rejected"):
        assert one(jobs=[{**done, "status": status}]) == []


def test_desk_cards():
    assert one(desk=[{"item_id": "d1", "title": "TRY - pass", "kind": "try",
                      "decision": ""}]) == [{"kind": "try", "title": "TRY - pass", "detail": "",
                                             "ref": "d1", "when": ""}]
    assert one(desk=[{"item_id": "d2", "title": "x", "kind": "decide",
                      "decision": "approve"}]) == []
    assert one(desk=[{"item_id": "d3", "title": "y", "kind": "odd", "state": "open"}])[0][
        "kind"] == "decide"
    assert one(desk=[{"item_id": "d4", "title": "z", "kind": "read", "state": "closed"}]) == []
    assert one(desk=[{"item_id": "d5", "title": "r", "kind": "read", "added": "2026-10-01"}]) == [
        {"kind": "read", "title": "r", "detail": "", "ref": "d5", "when": "2026-10-01"}]


def test_reminders():
    f = {"id": "s-1", "title": "Stand-up", "kind": "reminder", "fired_at": "2026-10-26T09:00:00"}
    assert one(fired=[f]) == [{"kind": "reminder", "title": "Stand-up", "detail": "at 09:00",
                               "ref": "s-1", "when": "2026-10-26T09:00:00"}]
    assert one(fired=[{**f, "fired_at": "2026-10-26T07:59:59"}]) == []
    assert one(fired=[{**f, "kind": "job"}]) == []


def test_stale_campaigns():
    c = {"name": "outline", "state": "active", "updated": "2026-10-23T11:30:00"}
    assert one(campaigns=[c]) == [{"kind": "stale_campaign", "title": "outline",
                                   "detail": "no change for 72 h", "ref": "outline",
                                   "when": "2026-10-23T11:30:00"}]
    assert one(campaigns=[{"name": "fresh", "state": "active", "updated": "2026-10-26T11:00"}]) == []
    assert one(campaigns=[{**c, "state": "done"}]) == []
    assert one(campaigns=[{**c, "updated": "garbage"}]) == []
    assert one(campaigns=[{"name": "n", "state": "active"}]) == []
    exactly = {"name": "e", "state": "active", "updated": "2026-10-24T12:00"}
    assert one(campaigns=[exactly]) == []           # exactly 48 h is not "more than"
    assert one(campaigns=[exactly], stale_hours=47)[0]["detail"] == "no change for 48 h"


def test_fixer_cards():
    night = {"at": "2026-10-26T03:00", "fixer_candidates": [
        {"signature": "budget_tokens x3", "count": 3, "example_job": "j7"}]}
    assert one(night=night, seen_at="2026-10-25T20:00") == [
        {"kind": "fixer", "title": "budget_tokens x3", "detail": "3 failures, e.g. j7",
         "ref": "j7", "when": "2026-10-26T03:00"}]
    assert one(night=night) == []                   # seen after the night report
    assert one(night={"at": "2026-10-26T09:00"}) == []


def test_seen_never_makes_everything_new():
    job = {"task_id": "j", "status": "completed", "finished_at": "2020-01-01T00:00"}
    assert one(jobs=[job], seen_at="")[0]["kind"] == "finished"


def test_order_rank_then_newest_then_title():
    jobs = [{"task_id": "f1", "title": "b", "status": "completed", "finished_at": "2026-10-26T09:00"},
            {"task_id": "f2", "title": "a", "status": "completed", "finished_at": "2026-10-26T09:00"},
            {"task_id": "f3", "title": "c", "status": "completed", "finished_at": "2026-10-26T11:00"},
            {"task_id": "x", "title": "z", "status": "failed", "finished_at": "2026-10-26T09:00"},
            {"task_id": "q", "title": "q", "status": "review", "question": {"question": "?"}}]
    desk = [{"item_id": "d", "title": "dd", "kind": "decide"},
            {"item_id": "t1", "title": "t-old", "kind": "try", "added": "2026-10-01"},
            {"item_id": "t2", "title": "t-none", "kind": "try"},
            {"item_id": "t3", "title": "t-new", "kind": "try", "added": "2026-10-20"},
            {"item_id": "r", "title": "rr", "kind": "read"}]
    out = one(jobs=jobs, desk=desk)
    assert [c["ref"] for c in out] == ["q", "d", "x", "t3", "t1", "t2", "f3", "f2", "f1", "r"]


def test_counts():
    out = one(jobs=[{"task_id": "q", "status": "review", "question": {"question": "?"}}],
              desk=[{"item_id": "a", "kind": "try"}, {"item_id": "b", "kind": "try"}])
    assert ib.counts(out) == {"question": 1, "try": 2}
    assert ib.counts([]) == {}
