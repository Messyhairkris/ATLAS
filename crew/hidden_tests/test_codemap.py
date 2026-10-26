"""Hidden tests for codemap.py. Every contract row, plus real code the crew meets."""

import pytest

import codemap as cm


@pytest.mark.parametrize("path, want", [
    ("a/B.PY", "python"), ("x\\y.rs", "rust"), ("m.mjs", "js"), ("c.TSX", "js"),
    ("s.ahk", "ahk"), ("w.pyw", "python"), ("Makefile", None), ("dir.v2/README", None),
    ("dir.v2\\README", None), ("archive.tar.gz", None), (".py", "python"), ("a.", None),
])
def test_language_of(path, want):
    assert cm.language_of(path) == want


def test_python_ast():
    src = ("def a():\n  pass\nclass K:\n  def m(self): pass\n  async def n(self): pass\n"
           "  class In:\n    def deep(self): pass\nasync def b(): pass")
    assert cm.outline(src, "python") == [(1, "def", "a"), (3, "class", "K"),
                                         (4, "method", "K.m"), (5, "method", "K.n"),
                                         (8, "def", "b")]


def test_python_decorated_and_nested_are_handled_like_ast():
    src = "@dec\ndef f():\n    def inner(): pass\n\nx = 1\nif x:\n    def hidden(): pass\n"
    assert cm.outline(src, "python") == [(2, "def", "f")]


def test_python_fallback_on_a_syntax_error():
    src = "def ok(:\n    class X:\n  async def y(): pass"
    assert cm.outline(src, "python") == [(1, "def", "ok"), (2, "class", "X"), (3, "def", "y")]


def test_python_crlf():
    assert cm.outline("def a():\r\n    pass\r\nclass B:\r\n    pass\r\n", "python") == [
        (1, "def", "a"), (3, "class", "B")]


def test_js_row():
    src = ("export default async function main() {}\nexport class Box {}\n"
           "const add = (a, b) => a + b\nlet f = async x => x\nexport const LIMIT = 3\n"
           "interface P {}\nfunction* gen() {}")
    assert cm.outline(src, "js") == [(1, "function", "main"), (2, "class", "Box"),
                                     (3, "function", "add"), (4, "function", "f"),
                                     (5, "const", "LIMIT"), (6, "type", "P"),
                                     (7, "function", "gen")]


def test_js_rules_in_order_and_non_matches():
    src = ("const x = 3\nexport const g = function () {}\n  export type T = {}\n"
           "abstract class A {}\nexport abstract class B {}\nconst $el = el => el\n"
           "// function commented\nobj.method = () => 1\nconst h = (a) =>\n")
    assert cm.outline(src, "js") == [(2, "function", "g"), (3, "type", "T"), (4, "class", "A"),
                                     (5, "class", "B"), (6, "function", "$el"),
                                     (9, "function", "h")]


def test_rust_row():
    src = ("pub(crate) async fn run() {}\nstruct S;\npub enum E { A }\n"
           "impl<T: Clone> Display for Wrap<T> {\nimpl S\n  fn inner(&self) {}\nmod tests;")
    assert cm.outline(src, "rust") == [(1, "fn", "run"), (2, "struct", "S"), (3, "enum", "E"),
                                       (4, "impl", "Display for Wrap<T>"), (5, "impl", "S"),
                                       (6, "fn", "inner"), (7, "mod", "tests")]


def test_rust_more():
    src = ('pub const fn c() {}\nunsafe extern "C" fn ffi() {}\npub trait Tr {}\n'
           "type Alias = u8;\nimpl  Foo   for   Bar  { fn x() {} }\nlet fnord = 1;\n"
           "pub(super) struct P {}")
    assert cm.outline(src, "rust") == [(1, "fn", "c"), (2, "fn", "ffi"), (3, "trait", "Tr"),
                                       (4, "type", "Alias"), (5, "impl", "Foo for Bar"),
                                       (7, "struct", "P")]


def test_ahk_row():
    src = ("Greet(name) {\n}\nHelper(x)\n; comment\n{\n}\nif(x)\n{\n:*:btw::by the way\n"
           "::omw::on my way\nStart:\n^!t::MsgBox\n  Indented() {\nCall(x)\nnext()")
    assert cm.outline(src, "ahk") == [(1, "function", "Greet"), (3, "function", "Helper"),
                                      (9, "hotstring", ":*:btw"), (10, "hotstring", "::omw"),
                                      (11, "label", "Start"), (12, "hotkey", "^!t")]


def test_ahk_more():
    src = ("While(x) {\nLoop(n)\n{\nUntil(y) {\nF(a, b) { ; does a thing\n}\n"
           "G()\n\n   \n; note\n{\nMyLabel: ; why\n#IfWinActive ahk_class X\nF1::\nx := f(1)")
    assert cm.outline(src, "ahk") == [(5, "function", "F"), (7, "function", "G"),
                                      (12, "label", "MyLabel"), (14, "hotkey", "F1")]


def test_unknown_language():
    assert cm.outline("x", "cobol") == []
    assert cm.outline("", "python") == []


def test_render_outline():
    assert cm.render_outline("a.py", []) == "a.py\n  (no symbols found)"
    assert cm.render_outline("a.py", [(1, "def", "f"), (12, "class", "K")]) == (
        "a.py\n      1  def f\n     12  class K")
    assert cm.render_outline("a.py", [(i, "def", "f") for i in range(1, 6)], 2) == (
        "a.py\n      1  def f\n      2  def f\n  ... 3 more")
    assert cm.render_outline("a.py", [(123456, "def", "f")]) == "a.py\n  123456  def f"
    assert cm.render_outline("a.py", [(1, "def", "f")] * 3, 3).count("\n") == 3


def test_repo_map_rows():
    assert cm.repo_map({"b.py": "def f(): pass", "a.rs": "fn g() {}", "notes.txt": "x"}) == (
        "a.rs\n  fn g\nb.py\n  def f")
    assert cm.repo_map({"a.py": ""}) == "a.py\n  (no symbols)"
    assert cm.repo_map({"r.md": "x"}) == "(no code files)"
    assert cm.repo_map({}) == "(no code files)"
    assert cm.repo_map({"a.py": "def f(): pass", "b.py": "def g(): pass"}, 12) == (
        "a.py\n  def f\n... 1 more files")
    assert cm.repo_map({"a.py": "def f(): pass"}, 3) == "... 1 more files"


def test_repo_map_counts_only_known_languages_left_out():
    files = {"a.py": "def f(): pass", "b.py": "def g(): pass", "c.txt": "", "d.rs": "fn h(){}"}
    assert cm.repo_map(files, 13) == "a.py\n  def f\n... 2 more files"


def test_repo_map_default_cap():
    files = {f"m{i:03d}.py": "\n".join(f"def f{j}(): pass" for j in range(30))
             for i in range(40)}
    out = cm.repo_map(files)
    body, last = out.rsplit("\n", 1)
    assert len(body) <= 6000 and last.startswith("... ") and last.endswith(" more files")
    shown = body.count(".py\n")
    assert last == f"... {40 - shown} more files"
