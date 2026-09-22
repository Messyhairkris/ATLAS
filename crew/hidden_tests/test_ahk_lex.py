"""Hidden tests for ahk_lex.py - the author never sees these."""

import ahk_lex as L


def test_mask_keeps_shape_exactly():
    src = "Add(a, b) {  ; sum\r\n    s := \"x; y\"\r\n}\r\n"
    out = L.mask(src)
    assert len(out) == len(src)
    assert out.count("\n") == src.count("\n")
    assert out.count("\r") == src.count("\r")


def test_the_contract_table():
    assert L.mask("Add(a, b) {  ; sum") == "Add(a, b) {       "
    assert L.mask('s := "x; not a comment" ; real') == 's := "' + " " * 16 + '"' + " " * 7
    assert L.mask('t := "say ""hi"""') == 't := "' + " " * 10 + '"'
    assert L.mask("u := a`;b") == "u := a`;b"


def test_a_semicolon_needs_whitespace_before_it_to_be_a_comment():
    assert L.mask("x := a;b") == "x := a;b"
    assert L.mask("x := a\t; note") == "x := a\t" + " " * 6
    assert L.mask("; whole line") == " " * 12
    assert L.mask("    ; indented") == " " * 14


def test_a_semicolon_inside_a_string_is_not_a_comment():
    assert L.mask('Run("a ; b")') == 'Run("     ")'


def test_code_after_a_string_is_still_code():
    assert L.mask('x := "run" Run') == 'x := "   " Run'


def test_escapes_inside_strings_are_masked():
    assert L.mask('x := "a`"b"') == 'x := "    "'
    assert L.mask('x := "tab`there"') == 'x := "         "'


def test_block_comments_are_whole_lines():
    src = "a := 1\n/*\nRun, notepad.exe\n*/ trailing\nb := 2"
    assert L.mask(src).split("\n") == ["a := 1", "  ", " " * 16, " " * 11, "b := 2"]


def test_a_one_line_block_comment_still_opens_a_block():
    src = "/* note */\nRun, x\n*/\nc := 3"
    assert L.mask(src).split("\n") == [" " * 10, " " * 6, "  ", "c := 3"]


def test_block_markers_must_start_the_line():
    assert L.mask("x := 1 /* not a block") == "x := 1 /* not a block"
    assert L.mask("  /*\nhidden\n  */\nshown") == "    \n      \n    \nshown"


def test_an_unclosed_block_runs_to_the_end():
    assert L.mask("/*\nRun\nSend").split("\n") == ["  ", "   ", "    "]


def test_strings_never_span_lines():
    src = 'a := "open\nb := 1 ; c'
    assert L.mask(src).split("\n") == ['a := "    ', "b := 1    "]


def test_unterminated_lists_lines_in_order():
    assert L.unterminated('ok := "fine"\nbad := "open') == [2]
    assert L.unterminated('x := "a"" b"') == []
    assert L.unterminated('x := "a""') == [1]
    assert L.unterminated('/*\n"open\n*/\ny := "z') == [4]
    assert L.unterminated("") == []


def test_code_lines_skips_blank_and_comment_lines():
    src = "; header\r\nAdd(a) {\r\n\r\n    return a ; out\r\n}\r\n"
    assert L.code_lines(src) == [(2, "Add(a) {"), (4, "    return a      "), (5, "}")]


def test_code_lines_numbers_are_one_based_and_ordered():
    src = "/*\nx\n*/\n\n  y := 1\nz := 2"
    assert [n for n, _t in L.code_lines(src)] == [5, 6]


def test_empty_source():
    assert L.mask("") == ""
    assert L.code_lines("") == []
