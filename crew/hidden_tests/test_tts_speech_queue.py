"""Hidden tests for speech_queue.py. It must use the accepted verbalize module,
not its own copy of the punctuation rules."""

import pytest

import speech_queue as sq
import verbalize


def test_priorities_and_defaults():
    assert sq.PRIORITIES == ("alert", "normal")
    q = sq.SpeechQueue()
    assert q.level == "normal"
    assert q.current is None
    assert q.pending == []
    assert q.dropped == 0 and q.cancelled == 0


def test_it_uses_the_accepted_verbalize_module():
    q = sq.SpeechQueue(level="verbatim")
    u = q.enqueue("Hello, world.")
    assert u.text == verbalize.verbalize("Hello, world.", "verbatim")
    assert u.text == "Hello comma world period"


def test_ids_start_at_one_and_never_repeat():
    q = sq.SpeechQueue()
    a, b = q.enqueue("first"), q.enqueue("second")
    assert (a.id, b.id) == (1, 2)
    q.cancel_all()
    assert q.enqueue("third").id == 3


def test_unknown_priority_raises():
    q = sq.SpeechQueue()
    with pytest.raises(ValueError):
        q.enqueue("hello", "shouty")


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        sq.SpeechQueue(level="whisper").enqueue("hello")


def test_level_off_queues_nothing():
    q = sq.SpeechQueue(level="off")
    assert q.enqueue("something") is None
    assert q.pending == []


def test_whitespace_only_text_queues_nothing():
    q = sq.SpeechQueue()
    assert q.enqueue("   \n  ") is None
    assert q.pending == []


def test_normal_is_first_in_first_out():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two"), q.enqueue("three")
    assert [u.text for u in q.pending] == ["one", "two", "three"]


def test_an_alert_overtakes_normal_speech():
    q = sq.SpeechQueue()
    q.enqueue("long read back")
    alert = q.enqueue("headset lost", "alert")
    assert [u.id for u in q.pending] == [alert.id, 1]


def test_alerts_keep_their_own_order():
    q = sq.SpeechQueue()
    q.enqueue("normal one")
    a1 = q.enqueue("first alert", "alert")
    a2 = q.enqueue("second alert", "alert")
    assert [u.id for u in q.pending] == [a1.id, a2.id, 1]


def test_next_utterance_walks_the_queue_then_returns_none():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two")
    first = q.next_utterance()
    assert first.text == "one" and q.current is first
    assert q.next_utterance().text == "two"
    assert q.next_utterance() is None
    assert q.current is None


def test_cancel_current_only_stops_what_is_speaking():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two")
    q.next_utterance()
    assert q.cancel_current() is True
    assert q.current is None
    assert [u.text for u in q.pending] == ["two"]
    assert q.cancelled == 1
    assert q.cancel_current() is False


def test_cancel_all_clears_everything_and_counts_it():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two"), q.enqueue("three")
    q.next_utterance()
    assert q.cancel_all() == 3           # two pending plus the current one
    assert q.pending == [] and q.current is None
    assert q.cancelled == 3


def test_speak_all_speaks_in_order_and_empties_the_queue():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two"), q.enqueue("three")
    said = []
    ids = q.speak_all(lambda u: said.append(u.text))
    assert said == ["one", "two", "three"]
    assert ids == [1, 2, 3]
    assert q.pending == [] and q.current is None


def test_returning_false_stops_the_run_and_keeps_the_rest():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two"), q.enqueue("three")
    ids = q.speak_all(lambda u: False if u.text == "two" else True)
    assert ids == [1, 2]
    assert [u.text for u in q.pending] == ["three"]


def test_only_exactly_false_stops_it():
    q = sq.SpeechQueue()
    q.enqueue("one"), q.enqueue("two")
    assert q.speak_all(lambda u: None) == [1, 2]      # None is falsy but not False
    assert q.pending == []


def test_the_queue_has_a_ceiling_and_drops_the_oldest_normal():
    q = sq.SpeechQueue(max_pending=3)
    q.enqueue("one"), q.enqueue("two"), q.enqueue("three")
    q.enqueue("four")
    assert [u.text for u in q.pending] == ["two", "three", "four"]
    assert q.dropped == 1


def test_alerts_are_never_dropped():
    q = sq.SpeechQueue(max_pending=2)
    a1 = q.enqueue("alert one", "alert")
    a2 = q.enqueue("alert two", "alert")
    assert q.enqueue("normal") is None
    assert [u.id for u in q.pending] == [a1.id, a2.id]
    assert q.dropped == 0
