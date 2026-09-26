"""Hidden tests for st_schema.py - the author never sees these."""

import json

import st_schema as s

SCHEMA = {"type": "object",
          "properties": {"ref": {"type": "string"}, "n": {"type": "integer"},
                         "x": {"type": "number"}, "on": {"type": "boolean"},
                         "items": {"type": "array"}, "opts": {"type": "object"},
                         "mode": {"type": "string", "enum": ["a", "b"]}, "any": {}},
          "required": ["ref"], "additionalProperties": False}


def call(args, name="t", cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}


# -- parse_tool_calls -----------------------------------------------------------------

def test_no_tool_calls_is_empty():
    assert s.parse_tool_calls({"content": "hi"}) == []
    assert s.parse_tool_calls({"tool_calls": None}) == []


def test_string_arguments_parsed_in_order():
    out = s.parse_tool_calls({"tool_calls": [call('{"ref": "e1"}', "a", "1"),
                                             call('{"n": 2}', "b", "2")]})
    assert out == [{"id": "1", "name": "a", "args": {"ref": "e1"}, "error": None},
                   {"id": "2", "name": "b", "args": {"n": 2}, "error": None}]


def test_dict_arguments_used_as_is():
    assert s.parse_tool_calls({"tool_calls": [call({"ref": "e1"})]})[0]["args"] == {"ref": "e1"}


def test_empty_or_missing_arguments_mean_no_args():
    for raw in ("", None):
        r = s.parse_tool_calls({"tool_calls": [call(raw)]})[0]
        assert r["args"] == {} and r["error"] is None
    r = s.parse_tool_calls({"tool_calls": [{"id": "c", "function": {"name": "t"}}]})[0]
    assert r["args"] == {} and r["error"] is None


def test_invalid_json_reports_the_decoder_message():
    r = s.parse_tool_calls({"tool_calls": [call("{bad")]})[0]
    try:
        json.loads("{bad")
    except json.JSONDecodeError as e:
        expected = f"arguments are not valid JSON: {e}"
    assert r["args"] == {} and r["error"] == expected


def test_non_object_json_is_an_error():
    for raw in ("[1, 2]", "3", '"x"'):
        r = s.parse_tool_calls({"tool_calls": [call(raw)]})[0]
        assert r == {"id": "c1", "name": "t", "args": {}, "error": "arguments must be a JSON object"}


def test_missing_id_and_name():
    r = s.parse_tool_calls({"tool_calls": [{"function": {"arguments": "{}"}}]})[0]
    assert r == {"id": "", "name": "", "args": {}, "error": "tool call has no function name"}


def test_first_error_is_kept_when_name_also_missing():
    r = s.parse_tool_calls({"tool_calls": [{"function": {"arguments": "{bad"}}]})[0]
    assert r["error"].startswith("arguments are not valid JSON: ")


# -- validate_args ----------------------------------------------------------------------

def test_valid_args_give_no_errors():
    assert s.validate_args(SCHEMA, {"ref": "e1", "n": 3, "x": 1.5, "on": True,
                                    "items": [], "opts": {}, "mode": "a", "any": None}) == []


def test_number_accepts_int_but_not_bool():
    assert s.validate_args(SCHEMA, {"ref": "r", "x": 2}) == []
    assert s.validate_args(SCHEMA, {"ref": "r", "x": False}) == \
        ["argument 'x' must be number, got bool"]


def test_integer_refuses_bool_and_float():
    assert s.validate_args(SCHEMA, {"ref": "r", "n": True}) == \
        ["argument 'n' must be integer, got bool"]
    assert s.validate_args(SCHEMA, {"ref": "r", "n": 1.0}) == \
        ["argument 'n' must be integer, got float"]


def test_boolean_refuses_int():
    assert s.validate_args(SCHEMA, {"ref": "r", "on": 1}) == \
        ["argument 'on' must be boolean, got int"]


def test_required_first_then_args_in_order_all_reported():
    errs = s.validate_args(SCHEMA, {"zzz": 1, "n": "3", "mode": "c"})
    assert errs == ["missing required argument 'ref'", "unknown argument 'zzz'",
                    "argument 'n' must be integer, got str",
                    "argument 'mode' must be one of ['a', 'b']"]


def test_enum_only_checked_when_type_right():
    assert s.validate_args(SCHEMA, {"ref": "r", "mode": 5}) == \
        ["argument 'mode' must be string, got int"]


def test_unknown_args_allowed_when_additional_properties_absent_or_true():
    loose = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert s.validate_args(loose, {"b": 1, "a": "x"}) == []
    assert s.validate_args({**loose, "additionalProperties": True}, {"b": [1]}) == []


def test_contract_examples():
    assert s.validate_args({"type": "object", "properties": {"n": {"type": "integer"}},
                            "required": ["n"], "additionalProperties": False},
                           {"n": True, "x": 1}) == \
        ["argument 'n' must be integer, got bool", "unknown argument 'x'"]
    assert s.validate_args({"type": "object",
                            "properties": {"mode": {"type": "string", "enum": ["a", "b"]}},
                            "required": ["mode", "ref"]}, {"mode": "c"}) == \
        ["missing required argument 'ref'", "argument 'mode' must be one of ['a', 'b']"]


# -- check_call -------------------------------------------------------------------------

TOOLS = [{"type": "function", "function": {"name": "browser_click", "parameters": SCHEMA}},
         {"type": "function", "function": {"name": "browser_snapshot"}},
         {"type": "function", "function": {"name": "browser_navigate",
                                           "parameters": {"type": "object",
                                                          "properties": {"url": {"type": "string"}},
                                                          "required": ["url"]}}}]


def test_unknown_tool_lists_available_sorted():
    assert s.check_call(TOOLS, "apply_patch", {}) == \
        ["unknown tool 'apply_patch'; available: browser_click, browser_navigate, browser_snapshot"]


def test_known_tool_validates_against_its_schema():
    assert s.check_call(TOOLS, "browser_click", {"ref": "e3"}) == []
    assert s.check_call(TOOLS, "browser_navigate", {}) == ["missing required argument 'url'"]


def test_tool_without_parameters_accepts_only_empty():
    assert s.check_call(TOOLS, "browser_snapshot", {}) == []
    assert s.check_call(TOOLS, "browser_snapshot", {"a": 1, "b": 2}) == \
        ["unknown argument 'a'", "unknown argument 'b'"]
