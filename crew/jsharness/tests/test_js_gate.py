import pytest
import js_gate

# Constants used in many tests
ALLOWED_IMPORTS = {"./three.js"}
API = ["go"]
GOOD_SOURCE = 'import * as T from "./three.js";\nexport function go() { return 1; }'

class RunRecorder:
    """Callable that records how many times it is invoked and with what args."""
    def __init__(self, return_value: str):
        self.return_value = return_value
        self.calls = []

    def __call__(self, source: str) -> str:
        self.calls.append(source)
        return self.return_value

def test_unsafe_forbidden_global():
    """unsafe - forbidden global should block and run_tests not called."""
    src = 'export function go(){ return fetch(1) }'  # fetch is a forbidden global
    recorder = RunRecorder("should not be used")
    result = js_gate.judge(src, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "unsafe"
    assert result["problems"] == ["forbidden global: fetch"]
    assert result["counts"] is None
    assert len(recorder.calls) == 0

def test_unsafe_import_not_allowed():
    """unsafe - disallowed import should block and run_tests not called."""
    src = 'import "fs"; export function go(){ return 1 }'  # fs not in allowed set
    recorder = RunRecorder("should not be used")
    result = js_gate.judge(src, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "unsafe"
    assert result["problems"] == ["import not allowed: fs"]
    assert result["counts"] is None
    assert len(recorder.calls) == 0

def test_unsafe_multiple_issues():
    """unsafe - both forbidden global and bad import reported in order, no run_tests."""
    src = 'import "fs"; export function go(){ return eval(1) }'  # eval + fs
    recorder = RunRecorder("should not be used")
    result = js_gate.judge(src, API, ALLOWED_IMPORTS, recorder)

    # Order: forbidden globals first, then imports
    assert result["verdict"] == "unsafe"
    assert result["problems"] == [
        "forbidden global: eval",
        "import not allowed: fs",
    ]
    assert result["counts"] is None
    assert len(recorder.calls) == 0

def test_missing_api():
    """missing_api - exported name missing from API, no run_tests."""
    src = 'export function other(){ return 1 }'  # does not export "go"
    recorder = RunRecorder("should not be used")
    result = js_gate.judge(src, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "missing_api"
    assert result["problems"] == ["not exported: go"]
    assert result["counts"] is None
    assert len(recorder.calls) == 0

def test_stubs():
    """stubs - exported function body empty, no run_tests."""
    src = 'export function go(){ }'  # stub function
    recorder = RunRecorder("should not be used")
    result = js_gate.judge(src, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "stubs"
    assert result["problems"] == ["stub: go"]
    assert result["counts"] is None
    assert len(recorder.calls) == 0

def test_accepted_passed():
    """accepted - good source passes tests, run_tests called exactly once."""
    tap = "ok 1 - a\n# pass 1\n# fail 0\n"
    recorder = RunRecorder(tap)
    result = js_gate.judge(GOOD_SOURCE, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "accepted"
    assert result["problems"] == []
    # counts should contain at least pass and fail as parsed from TAP
    assert isinstance(result["counts"], dict)
    assert result["counts"].get("pass") == 1
    assert result["counts"].get("fail") == 0
    assert len(recorder.calls) == 1
    assert recorder.calls[0] == GOOD_SOURCE

def test_tests_failed_with_failures():
    """tests_failed - TAP reports failures, run_tests called once."""
    tap = "not ok 1 - a\n# pass 0\n# fail 1\n"
    recorder = RunRecorder(tap)
    result = js_gate.judge(GOOD_SOURCE, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "tests_failed"
    assert result["problems"] == ["1 failed"]
    assert isinstance(result["counts"], dict)
    assert result["counts"].get("fail") == 1
    assert len(recorder.calls) == 1

def test_tests_failed_no_pass():
    """tests_failed - TAP empty (no pass), run_tests called once."""
    tap = ""  # empty TAP text
    recorder = RunRecorder(tap)
    result = js_gate.judge(GOOD_SOURCE, API, ALLOWED_IMPORTS, recorder)

    assert result["verdict"] == "tests_failed"
    assert result["problems"] == ["no test passed"]
    # counts may be empty dict or None; contract says counts is parsed counts (empty)
    assert isinstance(result["counts"], dict)
    assert len(result["counts"]) == 0
    assert len(recorder.calls) == 1

def test_rule_order_unsafe_precedes_missing_api():
    """Rule order - unsafe should win over missing_api, run_tests never called."""
    src = 'import "fs"; export function other(){ return 1 }'  # unsafe import + missing go
    recorder = RunRecorder("should not be used")
    result = js_gate.judge(src, API, ALLOWED_IMPORTS, recorder)

    # unsafe verdict takes precedence
    assert result["verdict"] == "unsafe"
    # only the import problem is reported (no missing_api problems)
    assert result["problems"] == ["import not allowed: fs"]
    assert result["counts"] is None
    assert len(recorder.calls) == 0
