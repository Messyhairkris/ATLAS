"""js_lex contract tests: segmentation rules and the round-trip rule."""

import js_lex


def test_round_trip_unterminated_string():
    """Round trip: an unterminated string runs to the end of the source."""
    source = '"open'
    parts = js_lex.segments(source)
    assert parts == [("string", '"open')]
    assert "".join(t for _, t in parts) == source


def test_round_trip_unterminated_comment():
    """Round trip: a /* comment with no */ runs to the end of the source."""
    source = "/* open"
    parts = js_lex.segments(source)
    assert parts == [("comment", "/* open")]
    assert "".join(t for _, t in parts) == source


def test_round_trip_unterminated_template():
    """Round trip: a template with no closing backtick runs to the end."""
    source = "`open"
    parts = js_lex.segments(source)
    assert parts == [("template", "`open")]
    assert "".join(t for _, t in parts) == source


def test_round_trip_escaped_quote():
    """Round trip: a backslash skips the next char, so \\' does not end."""
    source = "'it\\'s'"
    parts = js_lex.segments(source)
    assert parts == [("string", "'it\\'s'")]
    assert "".join(t for _, t in parts) == source


def test_round_trip_escaped_backslash_before_closing_quote():
    """Round trip: \\\\ is one escaped backslash; the quote still closes."""
    source = '"a\\\\" b'
    parts = js_lex.segments(source)
    assert parts == [("string", '"a\\\\"'), ("code", " b")]
    assert "".join(t for _, t in parts) == source


def test_round_trip_comment_marker_inside_string():
    """Round trip: // inside a string is string text, not a comment."""
    source = '"// not a comment"'
    parts = js_lex.segments(source)
    assert parts == [("string", '"// not a comment"')]
    assert "".join(t for _, t in parts) == source


def test_adjacent_code_merged_into_one_segment():
    """Consecutive code characters merge into one ("code", text) segment."""
    assert js_lex.segments("a = 1") == [("code", "a = 1")]


def test_adjacent_strings_are_separate_segments():
    """Every string is its own segment, even when two are adjacent."""
    assert js_lex.segments('"a""b"') == [("string", '"a"'), ("string", '"b"')]


def test_adjacent_comments_are_separate_segments():
    """Every comment is its own segment, even when two are adjacent."""
    assert js_lex.segments("/* a *//* b */") == [
        ("comment", "/* a */"),
        ("comment", "/* b */"),
    ]


def test_empty_source_has_no_segments():
    """segments("") is [] - there are never empty segments."""
    assert js_lex.segments("") == []


def test_code_between_strings_is_one_segment():
    """Code between two strings is one merged code segment."""
    assert js_lex.segments('"a" + \'b\'') == [
        ("string", '"a"'),
        ("code", " + "),
        ("string", "'b'"),
    ]


def test_string_marker_inside_comment_stays_comment():
    """// wins first: a quote inside a comment is not a string."""
    assert js_lex.segments('// "not a string"') == [
        ("comment", '// "not a string"')
    ]


def test_template_dollar_brace_not_special():
    """${...} is not special: everything to the backtick is template."""
    assert js_lex.segments('`x ${"y"} z`') == [("template", '`x ${"y"} z`')]


def test_lone_slash_is_code():
    """Known limitation: /ab+c/ is not recognised; a lone / is code."""
    assert js_lex.segments("a / b") == [("code", "a / b")]


def test_code_only_comment_is_one_space():
    """code_only: a comment becomes exactly one space."""
    assert js_lex.code_only("a /* b */ c") == "a   c"


def test_code_only_string_is_empty_quotes():
    """code_only: a string becomes two double-quote characters."""
    assert js_lex.code_only('"a" + \'b\'') == '"" + ""'


def test_code_only_template_is_two_backticks():
    """code_only: a template becomes two backticks."""
    assert js_lex.code_only("f(`t`, 'u')") == 'f(``, "")'


def test_code_only_import_line():
    """code_only: the string and the trailing comment are both replaced."""
    assert js_lex.code_only('import x from "fs" // note') == 'import x from ""  '
