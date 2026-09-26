"""Hidden tests for outline.py - one contract rule per test."""

import dataclasses

import pytest

from outline import Entry, outline, render


def test_rule_top_level_defs_have_depth_zero():
    text = "def parse():\n    pass\n\n\ndef main():\n    pass\n"
    assert outline(text, "python") == [
        Entry(1, 0, "def", "parse"),
        Entry(5, 0, "def", "main"),
    ]


def test_rule_async_def_gets_its_own_kind():
    text = "async def fetch(url):\n    pass\n"
    assert outline(text, "python") == [Entry(1, 0, "async def", "fetch")]


def test_rule_class_and_method_depths():
    text = (
        "class App:\n"
        "    def start(self):\n"
        "        pass\n"
        "\n"
        "    def stop(self):\n"
        "        pass\n"
    )
    assert outline(text, "python") == [
        Entry(1, 0, "class", "App"),
        Entry(2, 1, "def", "start"),
        Entry(5, 1, "def", "stop"),
    ]


def test_rule_function_nested_in_method_is_depth_two():
    text = (
        "class A:\n"
        "    def m(self):\n"
        "        def helper():\n"
        "            pass\n"
    )
    assert outline(text, "python") == [
        Entry(1, 0, "class", "A"),
        Entry(2, 1, "def", "m"),
        Entry(3, 2, "def", "helper"),
    ]


def test_rule_dedent_back_to_top_level():
    text = (
        "class C:\n"
        "    def m(self):\n"
        "        pass\n"
        "def top():\n"
        "    pass\n"
    )
    assert outline(text, "python") == [
        Entry(1, 0, "class", "C"),
        Entry(2, 1, "def", "m"),
        Entry(4, 0, "def", "top"),
    ]


def test_rule_decorators_are_not_entries():
    text = "@logged\n@route('/x')\ndef handler():\n    pass\n"
    assert outline(text, "python") == [Entry(3, 0, "def", "handler")]


def test_rule_decorator_does_not_change_depth():
    text = "class V:\n    @property\n    def x(self):\n        return 1\n"
    assert outline(text, "python") == [
        Entry(1, 0, "class", "V"),
        Entry(3, 1, "def", "x"),
    ]


def test_rule_comment_lines_are_ignored():
    text = "# def fake():\n# class Nope:\ndef real():\n    pass\n"
    assert outline(text, "python") == [Entry(3, 0, "def", "real")]


def test_rule_string_assignment_is_not_an_entry():
    text = 'text = "def fake():"\ndef real():\n    pass\n'
    assert outline(text, "python") == [Entry(2, 0, "def", "real")]


def test_rule_docstring_body_is_ignored():
    text = (
        "def f():\n"
        '    """\n'
        "    def ghost():\n"
        "        pass\n"
        '    """\n'
        "    return 1\n"
    )
    assert outline(text, "python") == [Entry(1, 0, "def", "f")]


def test_rule_single_quoted_docstring_body_is_ignored():
    text = (
        "def f():\n"
        "    '''\n"
        "    class Ghost:\n"
        "    pass\n"
        "    '''\n"
        "    return 1\n"
    )
    assert outline(text, "python") == [Entry(1, 0, "def", "f")]


def test_rule_tab_advances_to_next_multiple_of_eight():
    text = "class T:\n\tdef m(self):\n\t\tpass\n"
    assert outline(text, "python") == [
        Entry(1, 0, "class", "T"),
        Entry(2, 1, "def", "m"),
    ]


def test_rule_keyword_prefix_words_are_not_entries():
    text = (
        "defund():\n"
        "    pass\n"
        "class Foo:\n"
        "    def def_x(self):\n"
        "        pass\n"
    )
    assert outline(text, "python") == [
        Entry(3, 0, "class", "Foo"),
        Entry(4, 1, "def", "def_x"),
    ]


def test_rule_name_stops_at_parens_and_base_classes():
    text = (
        "def parse(data, strict=False):\n"
        "    pass\n"
        "class Box(Mapping):\n"
        "    pass\n"
    )
    assert outline(text, "python") == [
        Entry(1, 0, "def", "parse"),
        Entry(3, 0, "class", "Box"),
    ]


def test_rule_empty_or_structureless_text_gives_empty_outline():
    assert outline("", "python") == []
    assert outline("x = 1\ny = 2\n", "python") == []


def test_rule_heading_levels_map_to_depth():
    text = (
        "# One\n"
        "## Two\n"
        "### Three\n"
        "#### Four\n"
        "##### Five\n"
        "###### Six\n"
    )
    assert outline(text, "markdown") == [
        Entry(1, 0, "heading", "One"),
        Entry(2, 1, "heading", "Two"),
        Entry(3, 2, "heading", "Three"),
        Entry(4, 3, "heading", "Four"),
        Entry(5, 4, "heading", "Five"),
        Entry(6, 5, "heading", "Six"),
    ]


def test_rule_backtick_fence_hides_headings():
    text = "# Real\n```\n# Fake\n```\n## Also Real\n"
    assert outline(text, "markdown") == [
        Entry(1, 0, "heading", "Real"),
        Entry(5, 1, "heading", "Also Real"),
    ]


def test_rule_tilde_fence_hides_headings():
    text = "~~~\n# Hidden\n~~~\n# Shown\n"
    assert outline(text, "markdown") == [Entry(4, 0, "heading", "Shown")]


def test_rule_unclosed_fence_swallows_the_rest():
    text = "# Kept\n```\n# Gone\n"
    assert outline(text, "markdown") == [Entry(1, 0, "heading", "Kept")]


def test_rule_closing_hashes_are_stripped():
    text = "## Title ##\n## x#\n"
    assert outline(text, "markdown") == [
        Entry(1, 1, "heading", "Title"),
        Entry(2, 1, "heading", "x#"),
    ]


def test_rule_hash_inside_name_is_kept():
    text = "### C#\n"
    assert outline(text, "markdown") == [Entry(1, 2, "heading", "C#")]


def test_rule_heading_needs_space_or_end_after_hashes():
    text = "#tag\n# ok\n#\n"
    assert outline(text, "markdown") == [
        Entry(2, 0, "heading", "ok"),
        Entry(3, 0, "heading", ""),
    ]


def test_rule_setext_headings_are_not_supported():
    text = "Title\n=====\nnext\n---\n"
    assert outline(text, "markdown") == []


def test_rule_four_leading_spaces_is_not_a_heading():
    text = "   ## three\n    ## four\n"
    assert outline(text, "markdown") == [Entry(1, 1, "heading", "three")]


def test_rule_heading_name_is_stripped():
    text = "##   Hello World   \n"
    assert outline(text, "markdown") == [Entry(1, 1, "heading", "Hello World")]


def test_rule_seven_hashes_is_not_a_heading():
    text = "####### TooDeep\n# ok\n"
    assert outline(text, "markdown") == [Entry(2, 0, "heading", "ok")]


def test_rule_render_format_and_indentation():
    text = "class App:\n    def start(self):\n        pass\n"
    entries = outline(text, "python")
    assert render(entries) == "L1  class App\n  L2  def start"


def test_rule_render_heading_uses_kind_word():
    entries = outline("## Hi\n", "markdown")
    assert render(entries) == "  L1  heading Hi"


def test_rule_render_empty_outline_is_empty_string():
    assert render([]) == ""


def test_rule_unknown_kind_raises_valueerror():
    with pytest.raises(ValueError):
        outline("x = 1\n", "html")


def test_rule_kind_is_case_sensitive():
    with pytest.raises(ValueError):
        outline("x = 1\n", "Python")


def test_rule_entry_is_a_frozen_dataclass():
    entry = Entry(1, 0, "def", "f")
    assert (entry.line, entry.depth, entry.kind, entry.name) == (
        1, 0, "def", "f",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.line = 2
