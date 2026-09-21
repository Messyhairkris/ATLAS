import node_tap
import pytest


def test_parse_tap_empty_text():
    """parse_tap returns empty results for empty input."""
    text = ""
    result = node_tap.parse_tap(text)
    assert result["tests"] == []
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_simple_ok():
    """parse_tap parses a simple ok line."""
    text = "ok 1 - adds"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "adds",
        "ok": True,
        "skip": False,
        "todo": False,
        "depth": 0
    }]
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_simple_not_ok():
    """parse_tap parses a simple not ok line."""
    text = "not ok 2 - fails here"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "fails here",
        "ok": False,
        "skip": False,
        "todo": False,
        "depth": 0
    }]
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_ok_with_name_and_skip_directive():
    """parse_tap sets skip=True for ok line with SKIP directive."""
    text = "ok 3 - skipped one # SKIP"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "skipped one",
        "ok": True,
        "skip": True,
        "todo": False,
        "depth": 0
    }]
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_ok_with_name_and_todo_directive():
    """parse_tap sets todo=True for ok line with TODO directive."""
    text = "ok 4 - later # todo not yet"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "later",
        "ok": True,
        "skip": False,
        "todo": True,
        "depth": 0
    }]
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_not_ok_with_skip_directive():
    """parse_tap sets skip=True for not ok line with SKIP directive."""
    text = "not ok 5 - failed but marked skip # SKIP"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "failed but marked skip",
        "ok": False,
        "skip": True,
        "todo": False,
        "depth": 0
    }]
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_depth_indentation():
    """parse_tap computes depth from leading spaces (4 spaces per level)."""
    text = "    ok 1 - inner ok"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "inner ok",
        "ok": True,
        "skip": False,
        "todo": False,
        "depth": 1
    }]
    text2 = "        not ok 7 - deep"
    result2 = node_tap.parse_tap(text2)
    assert result2["tests"] == [{
        "name": "deep",
        "ok": False,
        "skip": False,
        "todo": False,
        "depth": 2
    }]


def test_parse_tap_ignores_non_matching_lines():
    """parse_tap ignores lines that are not result or count lines."""
    text = "# Subtest: adds\nokay 1 - no\n  yaml: value\n"
    result = node_tap.parse_tap(text)
    assert result["tests"] == []
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_parse_tap_count_line_tests():
    """parse_tap sets tests count from # tests line."""
    text = "# tests 7"
    result = node_tap.parse_tap(text)
    assert result["tests"] == []
    assert result["counts"] == {"tests": 7}
    assert result["duration_ms"] is None


def test_parse_tap_count_line_duration_ms():
    """parse_tap sets duration_ms from # duration_ms line."""
    text = "# duration_ms 239.6107"
    result = node_tap.parse_tap(text)
    assert result["tests"] == []
    assert result["counts"] == {}
    assert result["duration_ms"] == 239.6107


def test_parse_tap_multiple_lines_full_example():
    """parse_tap parses the full example from the contract."""
    text = """TAP version 13
# Subtest: adds
ok 1 - adds
# Subtest: fails here
not ok 2 - fails here
  ---
  duration_ms: 0.6
  ...
ok 3 - skipped one # SKIP
ok 4 - todo one # TODO
# Subtest: group
    # Subtest: inner ok
    ok 1 - inner ok
    not ok 2 - inner bad
    1..2
not ok 5 - group
1..5
# tests 7
# suites 0
# pass 2
# fail 3
# cancelled 0
# skipped 1
# todo 1
# duration_ms 239.6107"""
    result = node_tap.parse_tap(text)
    expected_tests = [
        {"name": "adds", "ok": True, "skip": False, "todo": False, "depth": 0},
        {"name": "fails here", "ok": False, "skip": False, "todo": False, "depth": 0},
        {"name": "skipped one", "ok": True, "skip": True, "todo": False, "depth": 0},
        {"name": "todo one", "ok": True, "skip": False, "todo": True, "depth": 0},
        {"name": "inner ok", "ok": True, "skip": False, "todo": False, "depth": 1},
        {"name": "inner bad", "ok": False, "skip": False, "todo": False, "depth": 1},
        {"name": "group", "ok": False, "skip": False, "todo": False, "depth": 0}
    ]
    assert result["tests"] == expected_tests
    assert result["counts"] == {
        "tests": 7,
        "suites": 0,
        "pass": 2,
        "fail": 3,
        "cancelled": 0,
        "skipped": 1,
        "todo": 1
    }
    assert result["duration_ms"] == 239.6107


def test_parse_tap_counts_only_appeared_keys():
    """parse_tap counts dict includes only keys that appeared in input."""
    text = "# pass 5\n# todo 3"
    result = node_tap.parse_tap(text)
    assert result["tests"] == []
    assert result["counts"] == {"pass": 5, "todo": 3}
    assert result["duration_ms"] is None


def test_parse_tap_not_ok_with_comment_not_directive():
    """parse_tap treats non-directive # as part of the name."""
    text = "not ok 5 - test name # this is a comment"
    result = node_tap.parse_tap(text)
    assert result["tests"] == [{
        "name": "test name # this is a comment",
        "ok": False,
        "skip": False,
        "todo": False,
        "depth": 0
    }]
    assert result["counts"] == {}
    assert result["duration_ms"] is None


def test_summary_line_basic():
    """summary_line formats counts and duration_ms correctly."""
    result = {
        "tests": [],
        "counts": {"pass": 2, "fail": 3, "skipped": 1},
        "duration_ms": 239.6107
    }
    assert node_tap.summary_line(result) == "3 failed, 2 passed, 1 skipped in 0.24s"


def test_summary_line_only_passed():
    """summary_line handles only passed tests."""
    result = {
        "tests": [],
        "counts": {"pass": 29},
        "duration_ms": 1200.0
    }
    assert node_tap.summary_line(result) == "29 passed in 1.20s"


def test_summary_line_only_failed():
    """summary_line handles only failed tests with None duration."""
    result = {
        "tests": [],
        "counts": {"fail": 1, "pass": 0},
        "duration_ms": None
    }
    assert node_tap.summary_line(result) == "1 failed in 0.00s"


def test_summary_line_no_tests():
    """summary_line handles empty counts."""
    result = {
        "tests": [],
        "counts": {},
        "duration_ms": None
    }
    assert node_tap.summary_line(result) == "no tests ran in 0.00s"


def test_summary_line_with_skipped():
    """summary_line includes skipped tests when present."""
    result = {
        "tests": [],
        "counts": {"skipped": 2},
        "duration_ms": 500
    }
    assert node_tap.summary_line(result) == "2 skipped in 0.50s"


def test_summary_line_duration_zero():
    """summary_line formats zero duration correctly."""
    result = {
        "tests": [],
        "counts": {"pass": 1},
        "duration_ms": 0
    }
    assert node_tap.summary_line(result) == "1 passed in 0.00s"
