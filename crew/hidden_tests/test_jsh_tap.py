"""Hidden tests for node_tap.py, including a real Node 25 run."""

import pytest

import node_tap as nt

REAL_RUN = """TAP version 13
# Subtest: adds
ok 1 - adds
  ---
  duration_ms: 0.4501
  type: 'test'
  ...
# Subtest: fails here
not ok 2 - fails here
  ---
  duration_ms: 0.6
  failureType: 'testCodeFailure'
  error: |-
    Expected values to be strictly equal:
    1 !== 2
  ...
# Subtest: skipped one
ok 3 - skipped one # SKIP
# Subtest: todo one
ok 4 - todo one # TODO
# Subtest: group
    # Subtest: inner ok
    ok 1 - inner ok
    # Subtest: inner bad
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
# duration_ms 239.6107
"""


def _one(line):
    tests = nt.parse_tap(line)["tests"]
    assert len(tests) == 1
    return tests[0]


def test_count_keys():
    assert nt.COUNT_KEYS == ("tests", "suites", "pass", "fail", "cancelled",
                             "skipped", "todo")


def test_plain_pass():
    assert _one("ok 1 - adds") == {"name": "adds", "ok": True, "skip": False,
                                   "todo": False, "depth": 0}


def test_plain_fail():
    t = _one("not ok 2 - fails here")
    assert (t["name"], t["ok"], t["depth"]) == ("fails here", False, 0)


def test_skip_keeps_ok_and_strips_directive():
    t = _one("ok 3 - skipped one # SKIP")
    assert (t["name"], t["ok"], t["skip"], t["todo"]) == ("skipped one", True,
                                                          True, False)


def test_todo_any_case_with_trailing_text():
    t = _one("ok 4 - later # todo not yet")
    assert (t["name"], t["ok"], t["skip"], t["todo"]) == ("later", True, False, True)


def test_skipped_failure_is_still_not_ok():
    t = _one("not ok 5 - flaky # SKIP network")
    assert (t["ok"], t["skip"]) == (False, True)


@pytest.mark.parametrize("line,depth", [
    ("    ok 1 - inner ok", 1), ("        not ok 7 - deep", 2), ("      ok 2 - x", 1),
])
def test_depth_is_spaces_over_four(line, depth):
    assert _one(line)["depth"] == depth


def test_no_name():
    assert _one("ok 9")["name"] == ""


def test_hash_inside_a_name_that_is_not_a_directive():
    assert _one("ok 1 - handles # symbols")["name"] == "handles # symbols"


@pytest.mark.parametrize("line", ["# Subtest: adds", "okay 1 - no", "1..5",
                                  "  duration_ms: 0.6", "TAP version 13"])
def test_lines_that_are_not_results(line):
    assert nt.parse_tap(line)["tests"] == []


def test_real_run():
    result = nt.parse_tap(REAL_RUN)
    assert [t["name"] for t in result["tests"]] == [
        "adds", "fails here", "skipped one", "todo one", "inner ok", "inner bad",
        "group"]
    assert [t["ok"] for t in result["tests"]] == [True, False, True, True, True,
                                                  False, False]
    assert result["counts"] == {"tests": 7, "suites": 0, "pass": 2, "fail": 3,
                                "cancelled": 0, "skipped": 1, "todo": 1}
    assert result["duration_ms"] == pytest.approx(239.6107)


def test_counts_only_keys_that_appeared_and_ignores_unknown():
    result = nt.parse_tap("# pass 4\n# widgets 9\n")
    assert result["counts"] == {"pass": 4}
    assert result["duration_ms"] is None


def test_empty_text():
    assert nt.parse_tap("") == {"tests": [], "counts": {}, "duration_ms": None}


@pytest.mark.parametrize("counts,duration,expected", [
    ({"pass": 2, "fail": 3, "skipped": 1}, 239.6107,
     "3 failed, 2 passed, 1 skipped in 0.24s"),
    ({"pass": 29}, 1200.0, "29 passed in 1.20s"),
    ({"fail": 1, "pass": 0}, None, "1 failed in 0.00s"),
    ({}, None, "no tests ran in 0.00s"),
    ({"skipped": 2, "todo": 5}, 5.0, "2 skipped in 0.01s"),
])
def test_summary_line_table(counts, duration, expected):
    result = {"tests": [], "counts": counts, "duration_ms": duration}
    assert nt.summary_line(result) == expected


def test_summary_line_of_the_real_run():
    assert nt.summary_line(nt.parse_tap(REAL_RUN)) == (
        "3 failed, 2 passed, 1 skipped in 0.24s")
