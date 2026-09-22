"""Hidden tests for ahk_api.py - the author never sees these."""

import ahk_api as A

EXAMPLE = """Greeting := "hello"            ; line 1

Add(a, b := 1) {               ; line 3
    return a + b
}

Stub(x)                        ; line 7
{
    return
}
MsgBox, done                   ; line 11
"""


def test_keywords_are_lowercase_and_complete():
    for word in ("if", "while", "for", "loop", "switch", "catch", "return", "else",
                 "until", "try", "throw", "finally", "and", "or", "not"):
        assert word in A.KEYWORDS
    assert all(w == w.lower() for w in A.KEYWORDS)


def test_the_contract_example():
    f = A.functions(EXAMPLE)
    assert set(f) == {"add", "stub"}
    assert f["add"] == {"name": "Add", "params": ["a", "b"], "line": 3, "end": 5,
                        "body": ["return a + b"]}
    assert (f["stub"]["line"], f["stub"]["end"], f["stub"]["body"]) == (7, 10, ["return"])
    assert A.missing(EXAMPLE, ["ADD", "Wrap"]) == ["Wrap"]
    assert A.stubs(EXAMPLE) == ["Stub"]
    assert A.top_level(EXAMPLE) == [11]


def test_parameters_lose_byref_defaults_and_stars():
    f = A.functions("Wrap(ByRef text, b := 1, c = 2, rest*) {\n  return text\n}")
    assert f["wrap"]["params"] == ["text", "b", "c", "rest"]
    assert A.functions("None() {\n return 1\n}")["none"]["params"] == []


def test_keyword_lines_are_not_functions():
    src = "Outer(x) {\n    if (x) {\n        return 1\n    }\n    while (x) {\n    }\n}"
    f = A.functions(src)
    assert list(f) == ["outer"]
    assert f["outer"]["end"] == 7


def test_a_call_is_not_a_definition():
    assert A.functions("Add(1, 2)\nx := 3") == {}
    assert A.functions("Add(1, 2)\n{\n}") != {}      # brace on the next line: a definition


def test_nested_braces_find_the_right_end():
    src = "F(x) {\n  if (x)\n  {\n    y := {a: 1}\n  }\n  return y\n}\nG() {\n  return 2\n}"
    f = A.functions(src)
    assert f["f"]["end"] == 7
    assert f["f"]["body"] == ["if (x)", "{", "y := {a: 1}", "}", "return y"]
    assert f["g"]["line"] == 8


def test_braces_inside_strings_and_comments_do_not_count():
    src = 'F() {\n  s := "}"  ; }\n  return s\n}'
    f = A.functions(src)
    assert f["f"]["end"] == 4
    assert f["f"]["body"] == ['s := " "', "return s"]


def test_unbalanced_braces_run_to_the_end():
    f = A.functions("F() {\n  x := 1\n  y := 2")
    assert f["f"]["end"] == 3
    assert f["f"]["body"] == ["x := 1", "y := 2"]


def test_names_are_case_insensitive_keys_but_kept_as_written():
    f = A.functions("TitleCase(s) {\n  return s\n}")
    assert "titlecase" in f and f["titlecase"]["name"] == "TitleCase"
    assert A.missing("titlecase(s) {\n return s\n}", ["TitleCase"]) == []


def test_missing_keeps_the_api_order_and_spelling():
    assert A.missing("", ["Zed", "Alpha"]) == ["Zed", "Alpha"]


def test_stubs():
    src = ("Empty() {\n}\nOnlyReturn() {\n  RETURN\n}\nReal() {\n  return 1\n}\n"
           "Braced()\n{\n  {\n  }\n}")
    assert A.stubs(src) == ["Empty", "OnlyReturn", "Braced"]


def test_top_level_ignores_constants_and_directives_but_not_calls():
    src = '#Include lib.ahk\nLimit := 80\nDoThing()\nF() {\n  return 1\n}\nx++'
    assert A.top_level(src) == [3, 7]


def test_comment_only_and_blank_files():
    assert A.functions("; nothing\n\n/*\nF() {\n}\n*/") == {}
    assert A.top_level("") == []
    assert A.stubs("") == []
