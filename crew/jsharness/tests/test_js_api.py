import pytest
import js_api

# ----------------------------------------------------------------------
# exported_names - rule 1: default export
def test_exported_names_rule_1_default():
    """Rule 1 - `export default ...` yields the name \"default\"."""
    src = "export default 42;"
    assert js_api.exported_names(src) == ["default"]


# ----------------------------------------------------------------------
# exported_names - rule 2: function (async, generator, plain)
def test_exported_names_rule_2_function_plain():
    """Rule 2 - `export function name()` yields the function name."""
    src = "export function go() {}"
    assert js_api.exported_names(src) == ["go"]


def test_exported_names_rule_2_function_async():
    """Rule 2 - optional `async` before `function` is ignored."""
    src = "export async function load() {}"
    assert js_api.exported_names(src) == ["load"]


def test_exported_names_rule_2_function_generator():
    """Rule 2 - optional `*` after `function` is ignored."""
    src = "export function* gen() {}"
    assert js_api.exported_names(src) == ["gen"]


# ----------------------------------------------------------------------
# exported_names - rule 3: class export
def test_exported_names_rule_3_class():
    """Rule 3 - `export class Name` yields the class name."""
    src = "export class Viewer {}"
    assert js_api.exported_names(src) == ["Viewer"]


# ----------------------------------------------------------------------
# exported_names - rule 4: const/let/var, first declarator only, ignore destructuring
def test_exported_names_rule_4_const_multiple():
    """Rule 4 - only the first declarator of a const/let/var export is reported."""
    src = "export const A = 1, B = 2;"
    assert js_api.exported_names(src) == ["A"]


def test_exported_names_rule_4_destructuring():
    """Rule 4 - a destructuring pattern yields no name."""
    src = "export const { a } = o;"
    assert js_api.exported_names(src) == []


# ----------------------------------------------------------------------
# exported_names - rule 5: namespace re-export
def test_exported_names_rule_5_namespace():
    """Rule 5 - `export * as ns ...` yields the namespace name."""
    src = "export * as ns from 'm';"
    assert js_api.exported_names(src) == ["ns"]


def test_exported_names_rule_5_bare_star():
    """Rule 5 - a bare `export * from ...` yields no name."""
    src = "export * from 'm';"
    assert js_api.exported_names(src) == []


# ----------------------------------------------------------------------
# exported_names - rule 6: named export list
def test_exported_names_rule_6_named_list():
    """Rule 6 - `{ a, b as c, d as default }` yields a, c, default."""
    src = "export { a, b as c, d as default };"
    assert js_api.exported_names(src) == ["a", "c", "default"]


def test_exported_names_rule_6_no_space_after_brace():
    """Rule 6 - `{` may be directly followed by a name."""
    src = "export{e,f as g};"
    assert js_api.exported_names(src) == ["e", "g"]


# ----------------------------------------------------------------------
# missing_api - required names not exported
def test_missing_api_basic():
    """missing_api returns required names that are not exported, preserving order."""
    src = "export const A = 1; export function b() {}"
    required = ["A", "b", "c"]
    assert js_api.missing_api(src, required) == ["c"]


def test_missing_api_multiple_missing():
    """missing_api works when several required names are absent."""
    src = "export { x } from 'mod';"
    required = ["x", "y", "z"]
    assert js_api.missing_api(src, required) == ["y", "z"]


# ----------------------------------------------------------------------
# stub_functions - empty body is a stub
def test_stub_functions_empty_body():
    """A function with an empty body is considered a stub."""
    src = "function a() {}"
    assert js_api.stub_functions(src) == ["a"]


# ----------------------------------------------------------------------
# stub_functions - comment-only body is a stub (code_only turns comment into space)
def test_stub_functions_comment_body():
    """A function whose body contains only a comment is a stub after code_only."""
    src = "export async function b() { /* later */ }"
    assert js_api.stub_functions(src) == ["b"]


# ----------------------------------------------------------------------
# stub_functions - single throw new Error with empty or string argument is a stub
def test_stub_functions_throw_error_string():
    """A single `throw new Error('msg')` (string becomes empty after code_only) is a stub."""
    src = "function c() { throw new Error('not implemented'); }"
    assert js_api.stub_functions(src) == ["c"]


def test_stub_functions_throw_error_no_arg():
    """A single `throw new Error()` is a stub."""
    src = "function d() { throw new Error(); }"
    assert js_api.stub_functions(src) == ["d"]


# ----------------------------------------------------------------------
# stub_functions - default parameter with braces, empty body (still a stub)
def test_stub_functions_default_param_braces():
    """A function with a default parameter (`={}`) and an empty body is a stub."""
    src = "function e(x = {}) {}"
    assert js_api.stub_functions(src) == ["e"]


# ----------------------------------------------------------------------
# stub_functions - nested throw is NOT a stub
def test_stub_functions_nested_throw_not_stub():
    """A throw inside a nested block prevents the function from being a stub."""
    src = "function f() { if (cond) { throw new Error('bad'); } }"
    assert js_api.stub_functions(src) == []


# ----------------------------------------------------------------------
# stub_functions - computed error message is NOT a stub
def test_stub_functions_computed_throw_not_stub():
    """A throw with a computed message (`'a' + b`) is not a stub."""
    src = "function g() { throw new Error('a' + b); }"
    assert js_api.stub_functions(src) == []


# ----------------------------------------------------------------------
# stub_functions - arrow functions are ignored
def test_stub_functions_arrow_ignored():
    """Arrow functions are not considered for stub detection."""
    src = "const h = () => {}"
    assert js_api.stub_functions(src) == []


# ----------------------------------------------------------------------
# stub_functions - later function is stub, earlier is not
def test_stub_functions_multiple_functions():
    """Only the later stub function should be reported."""
    src = "function i() { return 1; } function j() {}"
    assert js_api.stub_functions(src) == ["j"]
