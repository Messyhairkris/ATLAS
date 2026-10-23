"""Hidden tests for js_imports.py. Every table row, plus the js_lex reuse rule."""

import pytest

import js_imports as ji


def test_forbidden_globals_exact():
    assert ji.FORBIDDEN_GLOBALS == (
        "eval", "Function", "process", "require", "fetch", "XMLHttpRequest",
        "WebSocket", "Worker", "globalThis", "window", "document")


@pytest.mark.parametrize("source,expected", [
    ('import a from "./a.js";', ["./a.js"]),
    ('import "./side.js";', ["./side.js"]),
    ("export { x } from './x.js'", ["./x.js"]),
    ('export * as ns from "n"', ["n"]),
    ('const m = await import( "dyn" )', ["dyn"]),
    ("const fs = require('fs')", ["fs"]),
    ('// import a from "no"', []),
    ('x.from "no"', []),
    ('reimport "no"', []),
    ('const s = "from"; f("a")', []),
    ("import(`tpl`)", []),
    ('import a from /* c */ "b"', ["b"]),
    ('import a from "b"; import c from "b"', ["b", "b"]),
    ('import a from "b" "c"', ["b"]),
    ('/* import "x" */ import "y"', ["y"]),
    ("import {\n  a,\n  b,\n} from 'multi'", ["multi"]),
    ('require\n(\n"spaced")', ["spaced"]),
    ("", []),
    # 2026-09-27: the trigger must END the code before the string (a variable named
    # `from` falsely rejected a correct module in the touchup-splice campaign).
    ('let from = 0; f("a")', []),
    ('out.push({ from, to: i }); g(":")', []),
    ('const u = import.meta.url; f("a")', []),
    ('let from = 0; f("a"); import x from "y"', ["y"]),
    ("const b = '\\\\'; import x from 'y'", ["y"]),
    ('const t = `a\\\\`; import x from "y"', ["y"]),
    ('const r = /a\\\\/g; import x from "y"', ["y"]),
])
def test_imports_table(source, expected):
    assert ji.imports(source) == expected


def test_check_imports_reports_only_disallowed():
    assert ji.check_imports('import a from "b"; import "c"', {"b"}) == ["c"]


def test_check_imports_sorted_and_unique():
    assert ji.check_imports('import "z"; import "a"; import "z"', set()) == ["a", "z"]


def test_check_imports_is_exact_match():
    assert ji.check_imports('import "./three.js"', {"three.js"}) == ["./three.js"]


@pytest.mark.parametrize("source,expected", [
    ("fetch(url)", ["fetch"]),
    ("obj.fetch(url)", []),
    ("a?.window", []),
    ("obj . process", []),
    ("const processed = 1", []),
    ('eval("x"); window.alert(1); eval(y)', ["eval", "window"]),
    ('new Function("return 1")', ["Function"]),
    ("// fetch(x)", []),
    ('"document"', []),
    ("`${fetch(1)}`", []),
    ("obj.\n  require('x')", []),
    ("x = globalThis; y = new Worker(u); z = document", ["Worker", "document",
                                                        "globalThis"]),
])
def test_forbidden_uses_table(source, expected):
    assert ji.forbidden_uses(source) == expected
