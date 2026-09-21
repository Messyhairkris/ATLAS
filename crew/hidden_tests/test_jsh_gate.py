"""Hidden tests for js_gate.py: rule order, and that tests never run too early."""

import pytest

import js_gate as jg

ALLOWED = {"./three.js"}
API = ["go"]
GOOD = 'import * as T from "./three.js";\nexport function go() { return 1; }'
PASS_TAP = "ok 1 - a\n# pass 1\n# fail 0\n"


class Runner:
    """Records every call so a test can prove the tests were or were not run."""

    def __init__(self, reply=PASS_TAP):
        self.reply = reply
        self.calls = []

    def __call__(self, source):
        self.calls.append(source)
        return self.reply


def test_verdicts():
    assert jg.VERDICTS == ("accepted", "unsafe", "missing_api", "stubs",
                           "tests_failed")


def test_accepted():
    run = Runner()
    assert jg.judge(GOOD, API, ALLOWED, run) == {
        "verdict": "accepted", "problems": [], "counts": {"pass": 1, "fail": 0}}
    assert run.calls == [GOOD]


@pytest.mark.parametrize("source,verdict,problems", [
    ("export function go(){ return fetch(1) }", "unsafe",
     ["forbidden global: fetch"]),
    ('import "fs"; export function go(){ return 1 }', "unsafe",
     ["import not allowed: fs"]),
    ('import "fs"; export function go(){ eval(1) }', "unsafe",
     ["forbidden global: eval", "import not allowed: fs"]),
    ("export function other(){ return 1 }", "missing_api", ["not exported: go"]),
    ("export function go(){}", "stubs", ["stub: go"]),
    ('import "fs"; export function other(){}', "unsafe",
     ["import not allowed: fs"]),
    ("export function other(){}", "missing_api", ["not exported: go"]),
])
def test_static_rejections_never_run_tests(source, verdict, problems):
    run = Runner()
    assert jg.judge(source, API, ALLOWED, run) == {
        "verdict": verdict, "problems": problems, "counts": None}
    assert run.calls == []


@pytest.mark.parametrize("tap,problems", [
    ("not ok 1 - a\n# pass 0\n# fail 1\n", ["1 failed"]),
    ("# pass 2\n# cancelled 1\n", ["1 failed"]),
    ("# pass 0\n# fail 2\n# cancelled 1\n", ["3 failed"]),
    ("", ["no test passed"]),
    ("# pass 0\n# fail 0\n", ["no test passed"]),
])
def test_test_failures(tap, problems):
    run = Runner(tap)
    result = jg.judge(GOOD, API, ALLOWED, run)
    assert result["verdict"] == "tests_failed"
    assert result["problems"] == problems
    assert isinstance(result["counts"], dict)
    assert len(run.calls) == 1


def test_commented_danger_is_not_unsafe():
    source = '// fetch("x"); import "fs"\nexport function go() { return 1; }'
    assert jg.judge(source, API, ALLOWED, Runner())["verdict"] == "accepted"
