"""Hidden tests for js_lex.py. Every table row, plus the round-trip rule."""

import pytest

import js_lex as lx

SEGMENT_ROWS = [
    ("a = 1", [("code", "a = 1")]),
    ("x // hi\ny", [("code", "x "), ("comment", "// hi"), ("code", "\ny")]),
    ("a /* b */ c", [("code", "a "), ("comment", "/* b */"), ("code", " c")]),
    ("/* open", [("comment", "/* open")]),
    ("'it\\'s'", [("string", "'it\\'s'")]),
    ("\"a\" + 'b'", [("string", '"a"'), ("code", " + "), ("string", "'b'")]),
    ('"a""b"', [("string", '"a"'), ("string", '"b"')]),
    ('`x ${"y"} z`', [("template", '`x ${"y"} z`')]),
    ('"// not a comment"', [("string", '"// not a comment"')]),
    ('// "not a string"', [("comment", '// "not a string"')]),
    ("a / b", [("code", "a / b")]),
    ('"open', [("string", '"open')]),
    ('"a\\\\" b', [("string", '"a\\\\"'), ("code", " b")]),
    ("", []),
]


REGEX_ROWS = [
    ('x.replace(/"/g, "&q;")', [("code", "x.replace("), ("regex", '/"/g'),
                                ("code", ", "), ("string", '"&q;"'), ("code", ")")]),
    ("a = b / c / d", [("code", "a = b / c / d")]),
    ("return /a[/]b/gi.test(s)", [("code", "return "), ("regex", "/a[/]b/gi"),
                                  ("code", ".test(s)")]),
    ("(a+b)/2", [("code", "(a+b)/2")]),
    ("f(/\\//)", [("code", "f("), ("regex", "/\\//"), ("code", ")")]),
    ("/^x$/.test(s)", [("regex", "/^x$/"), ("code", ".test(s)")]),
    ("const r = /ab\nc/", [("code", "const r = /ab\nc/")]),
    ('"a" / 2', [("string", '"a"'), ("code", " / 2")]),
    ("x = a /* c */ / b", [("code", "x = a "), ("comment", "/* c */"),
                           ("code", " / b")]),
    ("typeof /x/", [("code", "typeof "), ("regex", "/x/")]),
    ("mytypeof /x/ 2", [("code", "mytypeof /x/ 2")]),
    ("a = [/'/, /`/]", [("code", "a = ["), ("regex", "/'/"), ("code", ", "),
                        ("regex", "/`/"), ("code", "]")]),
    ("x = /[\\]/]/", [("code", "x = "), ("regex", "/[\\]/]/")]),
]


def test_kinds():
    assert lx.KINDS == ("code", "comment", "string", "template", "regex")


@pytest.mark.parametrize("source,expected", REGEX_ROWS)
def test_regex_table(source, expected):
    assert lx.segments(source) == expected


def test_code_only_masks_regexes():
    assert lx.code_only('s.split(/"/)') == "s.split(/_/)"


def test_a_quote_inside_a_regex_does_not_hide_later_code():
    source = 'const q = s.replace(/"/g, "&quot;"); document.title = q;'
    assert "document" in lx.code_only(source)
    assert lx.segments(source)[-1] == ("code", "); document.title = q;")


@pytest.mark.parametrize("source,expected", SEGMENT_ROWS)
def test_segments_table(source, expected):
    assert lx.segments(source) == expected


def test_a_double_quote_does_not_end_a_single_quoted_string():
    assert lx.segments("'say \"hi\"' x") == [("string", "'say \"hi\"'"),
                                            ("code", " x")]


def test_escaped_backtick_does_not_end_a_template():
    assert lx.segments("`a\\`b` c") == [("template", "`a\\`b`"), ("code", " c")]


def test_line_comment_leaves_the_newline_to_code():
    assert lx.segments("// a\n// b") == [("comment", "// a"), ("code", "\n"),
                                        ("comment", "// b")]


@pytest.mark.parametrize("source", [s for s, _ in SEGMENT_ROWS] + [
    "import x from 'y'; /* c */ `t ${1}` // end\n", "a/*b*/c//d\n'e'\"f\"`g`",
    "unterminated `template", "'\\",
])
def test_joining_segments_gives_the_source_back(source):
    parts = lx.segments(source)
    assert "".join(text for _, text in parts) == source
    assert all(text for _, text in parts)
    assert all(kind in lx.KINDS for kind, _ in parts)


def test_no_two_code_segments_are_adjacent():
    parts = lx.segments("a b /* c */ d e 'f' g")
    kinds = [k for k, _ in parts]
    assert all(not (a == b == "code") for a, b in zip(kinds, kinds[1:]))


@pytest.mark.parametrize("source,expected", [
    ('import x from "fs" // note', 'import x from ""  '),
    ("f(`t`, 'u')", 'f(``, "")'),
    ("a /* b */ c", "a   c"),
    ("/* a\nb */x", " x"),
    ("plain", "plain"),
    ("", ""),
])
def test_code_only_table(source, expected):
    assert lx.code_only(source) == expected
