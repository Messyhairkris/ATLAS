"""Tests for quirk_indent, written from the contract in quirk_indent.md.

The contract's worked example is reused as the main fixture: its verbatim
lines give the keys <head> -> 0, <title> -> 2, var MODULES = -> 2.
"""

import quirk_indent

CONTRACT = (
    "```html\n"
    "<head>\n"
    "  <title>{escaped title}</title>\n"
    "  var MODULES = {S(modules)};\n"
    "}\n"
    "```\n"
    "```js\n"
    "    not verbatim, wrong tag\n"
    "```\n"
)

LINES = quirk_indent.verbatim_lines(CONTRACT)


def test_verbatim_lines_worked_example():
    """Only the html block counts, the short '}' line is dropped, leading
    spaces are kept, order of appearance (contract worked example)."""
    assert quirk_indent.verbatim_lines(CONTRACT) == [
        "<head>",
        "  <title>{escaped title}</title>",
        "  var MODULES = {S(modules)};",
    ]


def test_verbatim_lines_each_distinct_line_once():
    """Contract rule 3: each distinct line is returned once, in order."""
    contract = "```text\n  <head>\n  <head>\n    <head>\n```\n"
    assert quirk_indent.verbatim_lines(contract) == ["  <head>", "    <head>"]


def test_verbatim_tag_is_matched_stripped_and_lowercased():
    """Contract rule 1: the info string is stripped and lowercased before
    being checked against VERBATIM_TAGS."""
    contract = "``` HTML \n  <head>\n```\n"
    assert quirk_indent.verbatim_lines(contract) == ["  <head>"]


def test_placeholder_css_makes_key_text_before_it():
    """Contract: {css} is a placeholder, so the key of
    '  <style>{css}</style>' is '<style>' with indent 2."""
    contract = "```html\n  <style>{css}</style>\n```\n"
    lines = quirk_indent.verbatim_lines(contract)
    src = "s = '    <style>'"
    assert quirk_indent.indent_drift(src, lines) == [
        {"line": 1, "text": "<style>", "expected": 2, "found": 4},
    ]


def test_spaced_brace_is_not_a_placeholder():
    """Contract: '{ type: "x" }' (space after the brace) is not a
    placeholder, so the key is the whole line, not '<div>'."""
    contract = '```html\n  <div>{ type: "x" }</div>\n```\n'
    lines = quirk_indent.verbatim_lines(contract)
    src = 's = \'    <div>{ type: "x" }</div>\''
    assert quirk_indent.indent_drift(src, lines) == [
        {"line": 1, "text": '<div>{ type: "x" }</div>', "expected": 2, "found": 4},
    ]
    assert quirk_indent.indent_drift("s = '  <div>'", lines) == []


def test_literal_ending_in_backslash_n_is_reported():
    """Contract: contents ending with backslash-n drop those two chars
    before the key check; worked example '"  <head>\\n"' -> found 2."""
    src = 'x = "  <head>\\n";'
    assert quirk_indent.indent_drift(src, LINES) == [
        {"line": 1, "text": "<head>", "expected": 0, "found": 2},
    ]


def test_fix_keeps_trailing_backslash_n():
    """Contract worked example: x = "  <head>\\n"; becomes
    x = "<head>\\n"; with count 1 - backslash-n and quotes unchanged."""
    src = 'x = "  <head>\\n";'
    fixed, count = quirk_indent.fix_indent_drift(src, LINES)
    assert fixed == 'x = "<head>\\n";'
    assert count == 1


def test_two_drifted_literals_on_one_line_reported_in_source_order():
    """Contract: every drifting literal is reported, in source order."""
    src = "a = ['  <head>', \"    <title>\"];"
    assert quirk_indent.indent_drift(src, LINES) == [
        {"line": 1, "text": "<head>", "expected": 0, "found": 2},
        {"line": 1, "text": "<title>", "expected": 2, "found": 4},
    ]


def test_fix_two_drifted_literals_on_one_line():
    """Contract worked example: both literals re-indented, count 2,
    nothing else in the source changes."""
    src = "a = ['  <head>', \"    <title>\"];"
    fixed, count = quirk_indent.fix_indent_drift(src, LINES)
    assert fixed == "a = ['<head>', \"  <title>\"];"
    assert count == 2


def test_fixing_twice_changes_nothing_the_second_time():
    """Contract: fixing twice changes nothing the second time."""
    src = "a = ['  <head>', \"    <title>\"];"
    fixed_once, count_once = quirk_indent.fix_indent_drift(src, LINES)
    fixed_twice, count_twice = quirk_indent.fix_indent_drift(fixed_once, LINES)
    assert count_once == 2
    assert fixed_twice == fixed_once
    assert count_twice == 0


def test_fix_no_drift_returns_source_unchanged_with_zero():
    """Contract: fixing a source with no drift returns it unchanged and 0."""
    src = "y = '<head>';"
    fixed, count = quirk_indent.fix_indent_drift(src, LINES)
    assert fixed == src
    assert count == 0


def test_first_occurrence_indent_wins_for_duplicate_keys():
    """Contract: if two lines have the same key, the FIRST one's indent
    is used."""
    contract = "```text\n  <head>\n    <head>\n```\n"
    lines = quirk_indent.verbatim_lines(contract)
    src = "s = '    <head>'"
    assert quirk_indent.indent_drift(src, lines) == [
        {"line": 1, "text": "<head>", "expected": 2, "found": 4},
    ]


def test_key_shorter_than_min_chars_is_ignored():
    """Contract: keys shorter than MIN_CHARS are ignored, even when the
    whole line is long enough to be a verbatim line."""
    contract = "```text\n  a {css}\n```\n"
    lines = quirk_indent.verbatim_lines(contract)
    assert lines == ["  a {css}"]
    assert quirk_indent.indent_drift("s = '    a'", lines) == []


def test_line_numbers_are_one_based():
    """Contract: source lines are numbered from 1."""
    src = "first = 1\nx = '  <head>'"
    assert quirk_indent.indent_drift(src, LINES) == [
        {"line": 2, "text": "<head>", "expected": 0, "found": 2},
    ]


def test_literal_that_is_not_a_key_is_not_reported():
    """Contract worked example: 'const s = "  hello there";' has no
    finding because the core is not a key."""
    src = 'const s = "  hello there";'
    assert quirk_indent.indent_drift(src, LINES) == []
