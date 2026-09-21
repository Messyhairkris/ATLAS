import pytest
import js_imports
import js_lex

def test_imports_from_keyword():
    source = 'import a from "./a.js";'
    assert js_imports.imports(source) == ["./a.js"]

def test_imports_bare():
    source = 'import "./side.js";'
    assert js_imports.imports(source) == ["./side.js"]

def test_imports_export_from():
    source = 'export { x } from \'x.js\''
    assert js_imports.imports(source) == ["x.js"]

def test_imports_export_as():
    source = 'export * as ns from "n"'
    assert js_imports.imports(source) == ["n"]

def test_imports_dynamic():
    source = 'const m = await import( "dyn" )'
    assert js_imports.imports(source) == ["dyn"]

def test_imports_require():
    source = 'const fs = require(\'fs\')'
    assert js_imports.imports(source) == ["fs"]

def test_imports_skips_comments():
    source = '// import a from "no"'
    assert js_imports.imports(source) == []

def test_imports_word_boundary_from():
    source = 'x.from "no"'
    assert js_imports.imports(source) == []

def test_imports_word_boundary_import():
    source = 'reimport "no"'
    assert js_imports.imports(source) == []

def test_imports_string_after_string():
    source = 'import a from "b"; import c from "b"'
    assert js_imports.imports(source) == ["b", "b"]

def test_imports_template_literal():
    source = 'import(`tpl`)'
    assert js_imports.imports(source) == []

def test_imports_string_after_comment():
    source = 'import a from /* c */ "b"'
    assert js_imports.imports(source) == ["b"]

def test_check_imports_filters_allowed():
    source = 'import a from "b"; import "c"'
    allowed = {"b"}
    assert js_imports.check_imports(source, allowed) == ["c"]

def test_check_imports_sorts_and_dedupes():
    source = 'import "z"; import "a"; import "z"'
    allowed = set()
    assert js_imports.check_imports(source, allowed) == ["a", "z"]

def test_forbidden_uses_fetch():
    source = 'fetch(url)'
    assert js_imports.forbidden_uses(source) == ["fetch"]

def test_forbidden_uses_property_access():
    source = 'obj.fetch(url)'
    assert js_imports.forbidden_uses(source) == []

def test_forbidden_uses_optional_chaining():
    source = 'a?.window'
    assert js_imports.forbidden_uses(source) == []

def test_forbidden_uses_whitespace_before_dot():
    source = 'obj . process'
    assert js_imports.forbidden_uses(source) == []

def test_forbidden_uses_multiple():
    source = 'eval("x"); window.alert(1); eval(y)'
    assert js_imports.forbidden_uses(source) == ["eval", "window"]

def test_forbidden_uses_function():
    source = 'new Function("return 1")'
    assert js_imports.forbidden_uses(source) == ["Function"]

def test_forbidden_uses_commented_out():
    source = '// fetch(x)'
    assert js_imports.forbidden_uses(source) == []

def test_forbidden_uses_string_literal():
    source = '"document"'
    assert js_imports.forbidden_uses(source) == []
