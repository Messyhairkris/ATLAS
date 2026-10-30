"""Hidden tests for project_search.py (finding inside a project folder). The author never sees these."""

import pytest

import project_search as ps


# terms ---------------------------------------------------------------------------------

def test_stopwords_has_the_words_the_contract_names():
    for word in ("the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is",
                 "are", "was", "were", "be", "been", "that", "this", "it", "its", "with",
                 "from", "as"):
        assert word in ps.STOPWORDS


def test_terms_lowercases_and_drops_stopwords():
    assert ps.terms("The Engine") == ["engine"]


def test_terms_splits_on_punctuation():
    assert ps.terms("a.py:42 - boom") == ["py", "42", "boom"]


def test_terms_keeps_the_order_and_drops_repeats():
    assert ps.terms("engine chat engine") == ["engine", "chat"]


def test_terms_of_only_stopwords_is_empty():
    assert ps.terms("the a of") == []


@pytest.mark.parametrize("query", [None, "", 7])
def test_terms_of_nothing_is_empty(query):
    assert ps.terms(query) == []


# score ---------------------------------------------------------------------------------

def test_score_counts_distinct_terms():
    assert ps.score("the engine log and the chat", ["engine", "chat"]) == 2


def test_score_counts_a_repeated_term_once():
    assert ps.score("the engine log", ["engine", "engine"]) == 1


def test_score_is_case_insensitive():
    assert ps.score("The ENGINE log", ["engine"]) == 1


def test_score_is_zero_when_nothing_matches():
    assert ps.score("nothing here", ["engine"]) == 0


def test_score_with_no_terms_is_zero():
    assert ps.score("the engine log", []) == 0


def test_score_can_never_exceed_the_terms_given():
    assert ps.score("engine engine engine", ["engine", "engine"]) == 1


# snippet -------------------------------------------------------------------------------

def test_snippet_returns_a_short_line_unchanged():
    assert ps.snippet("short line", ["line"]) == "short line"


def test_snippet_collapses_the_text_to_one_line():
    assert ps.snippet("a\n b\tc", ["b"]) == "a b c"


def test_snippet_is_empty_when_no_term_is_in_the_text():
    assert ps.snippet("short line", ["engine"]) == ""


def test_snippet_is_empty_with_no_terms():
    assert ps.snippet("short line", []) == ""


def test_snippet_windows_a_long_line_and_marks_both_ends():
    text = "aaaaaMMMMMaaaaa"
    got = ps.snippet(text, ["MMMMM"], width=8)
    assert "MMMMM" in got
    assert got.startswith("...") and got.endswith("...")
    assert len(got) == 8 + 6, "the window is exactly `width` characters between the marks"


def test_snippet_marks_the_end_only_when_it_starts_at_the_beginning():
    got = ps.snippet("yyyyy" + "z" * 100, ["yyyyy"], width=10)
    assert not got.startswith("...") and got.endswith("...")


def test_snippet_does_not_go_past_the_end_of_the_text():
    got = ps.snippet("z" * 100 + "MMMMM", ["MMMMM"], width=10)
    assert got.startswith("...") and not got.endswith("...")
    assert got.endswith("MMMMM")


def test_snippet_finds_the_earliest_match():
    got = ps.snippet("engine " + "x" * 300 + " chat", ["chat", "engine"], width=20)
    assert got.startswith("engine")


# rank ----------------------------------------------------------------------------------

def three_docs():
    return [{"id": "b", "kind": "chat", "text": "engine chat"},
            {"id": "a", "kind": "chat", "text": "engine"},
            {"id": "c", "kind": "file", "text": "nothing"}]


def test_rank_puts_the_better_match_first_and_drops_the_rest():
    got = ps.rank(three_docs(), ["engine", "chat"])
    assert [r["id"] for r in got] == ["b", "a"]
    assert got[0]["score"] == 2 and got[1]["score"] == 1


def test_rank_breaks_ties_by_id_ascending():
    docs = [{"id": "z", "kind": "chat", "text": "engine"},
            {"id": "a", "kind": "chat", "text": "engine"}]
    assert [r["id"] for r in ps.rank(docs, ["engine"])] == ["a", "z"]


def test_rank_carries_the_kind_and_a_snippet():
    got = ps.rank(three_docs(), ["engine", "chat"])[0]
    assert got["kind"] == "chat" and got["snippet"] == "engine chat"


def test_rank_uses_an_empty_kind_when_the_doc_has_none():
    got = ps.rank([{"id": "a", "text": "engine"}], ["engine"])
    assert got[0]["kind"] == ""


def test_rank_honours_the_limit():
    assert len(ps.rank(three_docs(), ["engine", "chat"], limit=1)) == 1


def test_rank_with_a_limit_of_zero_or_less_is_empty():
    assert ps.rank(three_docs(), ["engine"], limit=0) == []
    assert ps.rank(three_docs(), ["engine"], limit=-3) == []


def test_rank_of_no_docs_is_empty():
    assert ps.rank([], ["engine"]) == []
