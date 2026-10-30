"""Hidden tests for problems_lib.py (IDE Phase 1, the Problems pane). The author never sees these."""

import pytest

import problems_lib as pl

CARGO = (
    "error[E0308]: mismatched types\n"
    "  --> src/main.rs:12:5\n"
    "   |\n"
    "12 |     let x: i32 = \"s\";\n"
    "   |            ^^^ expected `i32`, found `&str`\n"
    "   |\n"
    "   = note: expected type `i32`\n"
    "warning: unused variable: `x`\n"
    "  --> src/main.rs:5:9\n"
)


def test_kinds_are_cargo_then_pytest():
    assert [k["name"] for k in pl.KINDS] == ["cargo", "pytest"]


def test_loc_within_is_three():
    assert pl.LOC_WITHIN == 3


def test_cargo_error_with_its_position():
    p = pl.parse(CARGO)[0]
    assert p == {"kind": "cargo", "severity": "error", "file": "src/main.rs", "line": 12,
                 "col": 5, "code": "E0308", "message": "mismatched types"}


def test_cargo_warning_has_no_code():
    p = pl.parse(CARGO)[1]
    assert p["severity"] == "warning"
    assert p["code"] is None
    assert p["file"] == "src/main.rs" and p["line"] == 5 and p["col"] == 9
    assert p["message"] == "unused variable: `x`"


def test_line_and_col_are_ints():
    p = pl.parse(CARGO)[0]
    assert isinstance(p["line"], int) and isinstance(p["col"], int)


def test_a_cargo_error_with_no_position_keeps_none():
    p = pl.parse("error: could not compile `crew_control` (bin)")[0]
    assert p["file"] is None and p["line"] is None and p["col"] is None and p["code"] is None
    assert p["severity"] == "error"
    assert p["message"] == "could not compile `crew_control` (bin)"


def test_the_gutter_and_note_lines_are_not_problems():
    assert len(pl.parse(CARGO)) == 2


def test_a_position_line_alone_is_not_a_problem():
    assert pl.parse("  --> src/main.rs:12:5") == []


def test_a_note_line_alone_is_not_a_problem():
    assert pl.parse("   = note: expected type `i32`") == []


def test_problems_keep_their_order():
    got = [p["severity"] for p in pl.parse(CARGO)]
    assert got == ["error", "warning"]


def test_a_position_beyond_the_window_is_not_used():
    text = "error: oops\nfiller one\nfiller two\nfiller three\n  --> a.py:9:1"
    p = pl.parse(text)[0]
    assert p["file"] is None and p["line"] is None


def test_a_position_inside_the_window_is_used():
    text = "error: oops\nfiller one\nfiller two\n  --> a.py:9:1"
    p = pl.parse(text)[0]
    assert p["file"] == "a.py" and p["line"] == 9 and p["col"] == 1


def test_pytest_location_line_is_a_problem():
    p = pl.parse("tests/test_foo.py:42: AssertionError: assert 1 == 2")[0]
    assert p == {"kind": "pytest", "severity": "error", "file": "tests/test_foo.py", "line": 42,
                 "col": None, "code": None, "message": "AssertionError: assert 1 == 2"}


def test_pytest_line_carries_no_column():
    assert pl.parse("tests/test_foo.py:42: AssertionError: assert 1 == 2")[0]["col"] is None


def test_duplicate_problems_collapse_to_one():
    two = ("tests/test_foo.py:42: AssertionError: assert 1 == 2\n"
           "tests/test_foo.py:42: AssertionError: assert 1 == 2")
    assert len(pl.parse(two)) == 1


def test_different_lines_are_not_collapsed():
    two = ("tests/a.py:1: AssertionError\n"
           "tests/a.py:2: AssertionError")
    assert len(pl.parse(two)) == 2


def test_empty_and_none_give_nothing():
    assert pl.parse("") == []
    assert pl.parse(None) == []


def test_text_without_any_problem_gives_nothing():
    assert pl.parse("linking\n   Compiling crew_control v0.1.0\n    Finished release") == []


def test_a_kind_without_a_head_raises():
    with pytest.raises(ValueError):
        pl.parse("x", kinds=[{"name": "broken"}])


def test_a_kind_without_a_name_raises():
    with pytest.raises(ValueError):
        pl.parse("x", kinds=[{"head": "^x"}])


def test_a_fixed_level_is_used_when_the_head_has_none():
    kind = {"name": "k", "head": r"^X: (?P<message>.*)$", "loc": None, "level": "warning"}
    assert pl.parse("X: hi", kinds=[kind])[0]["severity"] == "warning"


def test_a_missing_level_becomes_error():
    kind = {"name": "k", "head": r"^X: (?P<message>.*)$", "loc": None}
    assert pl.parse("X: hi", kinds=[kind])[0]["severity"] == "error"


def test_an_unknown_fixed_level_becomes_error():
    kind = {"name": "k", "head": r"^X: (?P<message>.*)$", "loc": None, "level": "fatal"}
    assert pl.parse("X: hi", kinds=[kind])[0]["severity"] == "error"


def test_the_heads_own_position_beats_loc():
    kind = {"name": "k", "head": r"^(?P<file>\S+):(?P<line>\d+): (?P<message>.*)$",
            "loc": r"^\s*--> (?P<file>.+?):(?P<line>\d+):(?P<col>\d+)$", "level": "error"}
    p = pl.parse("a.py:3: boom\n  --> b.py:9:2", kinds=[kind])[0]
    assert p["file"] == "a.py" and p["line"] == 3 and p["col"] is None


def test_load_without_a_path_gives_the_builtins_in_a_new_list():
    out = pl.load()
    assert out == pl.KINDS
    assert out is not pl.KINDS


def test_load_replaces_a_builtin_in_its_own_place():
    settings = {"kinds": [{"name": "cargo", "head": r"^C: (?P<message>.*)$", "loc": None,
                           "level": "error"}]}
    out = pl.load(settings)
    assert [k["name"] for k in out] == ["cargo", "pytest"]
    assert out[0]["head"] == r"^C: (?P<message>.*)$"
    assert out[1]["head"] == pl.KINDS[1]["head"]


def test_load_appends_a_new_kind_in_settings_order():
    settings = {"kinds": [{"name": "msvc", "head": r"^M: (?P<message>.*)$", "loc": None},
                          {"name": "mypy", "head": r"^Y: (?P<message>.*)$", "loc": None}]}
    assert [k["name"] for k in pl.load(settings)] == ["cargo", "pytest", "msvc", "mypy"]


def test_load_without_a_kinds_key_gives_the_builtins():
    assert [k["name"] for k in pl.load({"note": "nothing here yet"})] == ["cargo", "pytest"]


def test_load_with_kinds_that_are_not_a_list_raises():
    with pytest.raises(ValueError):
        pl.load({"kinds": {"name": "cargo"}})


def test_load_takes_a_dict_not_a_path():
    """The crew's airlock bans open(); load() must work from an already-parsed dict."""
    assert [k["name"] for k in pl.load({"kinds": []})] == ["cargo", "pytest"]


def test_load_does_not_touch_the_builtins():
    pl.load({"kinds": [{"name": "msvc", "head": r"^M: (?P<message>.*)$", "loc": None}]})
    assert [k["name"] for k in pl.KINDS] == ["cargo", "pytest"]


# format_problem ------------------------------------------------------------------------

def test_format_a_full_cargo_problem():
    assert pl.format_problem({"kind": "cargo", "severity": "error", "file": "src/main.rs",
                              "line": 12, "col": 5, "code": "E0308",
                              "message": "mismatched types"}) == \
        "src/main.rs:12:5: error[E0308]: mismatched types"


def test_format_a_warning_without_a_code():
    assert pl.format_problem({"kind": "cargo", "severity": "warning", "file": "src/main.rs",
                              "line": 5, "col": 9, "code": None,
                              "message": "unused variable: `x`"}) == \
        "src/main.rs:5:9: warning: unused variable: `x`"


def test_format_a_problem_with_no_position():
    assert pl.format_problem({"kind": "cargo", "severity": "error", "file": None, "line": None,
                              "col": None, "code": None,
                              "message": "could not compile `crew_control` (bin)"}) == \
        "error: could not compile `crew_control` (bin)"


def test_format_a_pytest_problem():
    assert pl.format_problem({"kind": "pytest", "severity": "error", "file": "tests/test_foo.py",
                              "line": 42, "col": None, "code": None,
                              "message": "AssertionError: assert 1 == 2"}) == \
        "tests/test_foo.py:42: error: AssertionError: assert 1 == 2"


def test_format_drops_an_empty_message():
    assert pl.format_problem({"kind": "cargo", "severity": "warning", "file": None, "line": None,
                              "col": None, "code": None, "message": ""}) == "warning"


def test_format_shows_a_line_without_a_column():
    assert pl.format_problem({"kind": "pytest", "severity": "error", "file": "a.py", "line": 7,
                              "col": None, "code": None, "message": "boom"}) == \
        "a.py:7: error: boom"
