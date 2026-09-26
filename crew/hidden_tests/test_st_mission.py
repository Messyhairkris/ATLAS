"""Hidden tests for st_mission.py - the author never sees these."""

import pytest
import st_mission as sm

W = "file:///C:/work/"


@pytest.mark.parametrize("url, ok", [
    ("file:///C:/work/a.html", True),
    ("file:///c:/WORK/A.html", True),                 # file paths: case-insensitive
    ("file:///C:/workshop/x.html", False),            # folder prefix ends in /
    ("file:///C:/work/../secret.txt", False),
    ("file:///C:/work/%2e%2e/secret.txt", False),     # encoded .. is still ..
    ("file:///C:/work/a.html?x=1#top", True),
    ("javascript:alert(1)", False),
    ("ftp://host/work/", False),
    ("", False), (None, False), (42, False),
])
def test_url_allowed_file(url, ok):
    assert sm.url_allowed(url, [W]) is ok


def test_url_allowed_http_rules():
    pre = ["http://localhost:8000/app/"]
    assert sm.url_allowed("http://LOCALHOST:8000/app/page", pre)       # host lowercased
    assert not sm.url_allowed("http://localhost:8000/App/page", pre)   # path case-sensitive
    assert not sm.url_allowed("http://localhost:80001/app/page", pre)  # netloc must match
    assert not sm.url_allowed("https://localhost:8000/app/page", pre)  # scheme must match
    assert not sm.url_allowed("http://localhost:8000/app/x", [])


def m(**kw):
    base = dict(allowed_tools=["nav", "click", "snap"], acting_tools=["click"],
                url_prefixes=[W], max_steps=10, max_actions=2)
    base.update(kw)
    return sm.Mission(**base)


def test_starts_at_zero():
    x = m()
    assert (x.steps, x.actions, x.errors_in_a_row, x.refused) == (0, 0, 0, 0)
    assert x.stop_reason() is None


def test_contract_example():
    x = sm.Mission(["browser_navigate", "browser_click"], ["browser_click"],
                   ["file:///C:/work/"], max_steps=10, max_actions=1)
    assert x.check("browser_navigate", {"url": "file:///C:/work/a.html"}) is None
    x.record("browser_navigate", {"url": "file:///C:/work/a.html"}, True)
    assert x.check("browser_type", {}) == "tool 'browser_type' is not part of this mission"
    assert x.check("browser_click", {"ref": "e1"}) is None
    x.record("browser_click", {"ref": "e1"}, True)
    assert x.check("browser_click", {"ref": "e2"}) == "action budget spent (1 actions)"
    assert x.summary()["by_tool"] == {"browser_navigate": 1, "browser_click": 1}


def test_url_refusal():
    x = m()
    assert x.check("nav", {"url": "https://evil.example/"}) == \
        "url 'https://evil.example/' is outside this mission's allowlist"
    assert x.refused == 1


def test_repeats_counted_on_recorded_calls_with_sorted_args():
    x = m(max_repeats=2)
    for _ in range(2):
        assert x.check("snap", {"a": 1, "b": 2}) is None
        x.record("snap", {"b": 2, "a": 1}, True)
    assert x.check("snap", {"a": 1, "b": 2}) == \
        "repeated call: 'snap' with the same arguments 2 times already"
    assert x.check("snap", {"a": 1, "b": 3}) is None


def test_refusal_order_step_budget_first():
    x = m(max_steps=1)
    x.record("snap", {}, True)
    assert x.check("not_a_tool", {"url": "bad"}) == "step budget spent (1 steps)"


def test_refusal_order_tool_before_url():
    assert m().check("zap", {"url": "bad"}) == "tool 'zap' is not part of this mission"


def test_action_budget_before_url():
    x = m(max_actions=0)
    assert x.check("click", {"url": "bad"}) == "action budget spent (0 actions)"


def test_record_counts():
    x = m()
    x.record("click", {"ref": "a"}, True)
    x.record("snap", {}, False)
    x.record("snap", {"z": 1}, False)
    assert (x.steps, x.actions, x.errors_in_a_row) == (3, 1, 2)
    x.record("nav", {"url": W}, True)
    assert x.errors_in_a_row == 0


def test_stop_reasons_in_order():
    x = m(max_steps=2, max_errors_in_a_row=2)
    x.record("snap", {}, False)
    x.record("snap", {"a": 1}, False)
    assert x.stop_reason() == "max_steps"          # steps checked before errors
    y = m(max_errors_in_a_row=2)
    y.record("snap", {}, False)
    assert y.stop_reason() is None
    y.record("snap", {"a": 1}, False)
    assert y.stop_reason() == "errors_in_a_row"


def test_refused_in_a_row_stops_and_record_resets_it():
    x = m()
    for _ in range(2):
        x.check("zap", {})
    assert x.stop_reason() is None
    x.record("snap", {}, True)                     # an allowed call resets the run
    for _ in range(2):
        x.check("zap", {})
    assert x.stop_reason() is None
    x.check("zap", {})
    assert x.stop_reason() == "refused_in_a_row"
    assert x.refused == 5


def test_allowed_check_changes_nothing():
    x = m()
    for _ in range(5):
        assert x.check("snap", {}) is None
    assert (x.steps, x.refused) == (0, 0)


def test_summary_shape():
    x = m()
    x.record("click", {"ref": "a"}, True)
    x.check("zap", {})
    assert x.summary() == {"steps": 1, "actions": 1, "refused": 1, "errors_in_a_row": 0,
                           "by_tool": {"click": 1}, "stop_reason": None}
