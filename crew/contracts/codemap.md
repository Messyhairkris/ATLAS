# Contract: codemap.py - an outline of a code file, and a map of a repository

Part of the crew harness. A crew member that has to find its way around a code base today reads
files blind (2026-10-26 record: 50 runs ran out of requests, mostly while still looking). This
module gives it, and the PAs, a cheap outline of a file (its functions, classes, ...) and a map
of many files under a size cap. Pure text in, text out. No I/O.

## Public API

```python
LANGUAGES = {".py": "python", ".pyw": "python", ".js": "js", ".mjs": "js", ".cjs": "js",
             ".jsx": "js", ".ts": "js", ".tsx": "js", ".rs": "rust", ".ahk": "ahk"}

def language_of(path: str) -> str | None: ...
def outline(source: str, language: str) -> list[tuple[int, str, str]]: ...
def render_outline(path: str, symbols: list[tuple[int, str, str]], max_lines: int = 80) -> str: ...
def repo_map(files: dict[str, str], max_chars: int = 6000) -> str: ...
```

Allowed imports: `ast`, `re`. Nothing else. Spell every name exactly as above.

A symbol is `(line, kind, name)`: `line` counts from 1; the list is sorted by line, then by its
order of discovery. Lines are split with `source.split("\n")`; a trailing `"\r"` is ignored.

## language_of(path)

The `LANGUAGES` entry for the path's extension compared lower-cased (`X.PY` is python), else
`None`. The extension is the part from the last `.` of the last path segment (`/` or `\`);
a segment with no `.` has none.

## outline(source, language)

An unknown language gives `[]`.

### python

1. Parse with `ast.parse(source)`. For each statement directly in the module body, in order:
   a `def` or `async def` gives `(lineno, "def", name)`; a `class` gives `(lineno, "class",
   name)` and then, for each `def` / `async def` directly in that class body,
   `(lineno, "method", ClassName + "." + name)`. Nothing deeper.
2. If parsing raises `SyntaxError`, fall back to lines: a line matching
   `^\s*(?:async\s+)?def\s+(\w+)` gives `"def"`, a line matching `^\s*class\s+(\w+)` gives
   `"class"` (indentation is ignored in the fallback).

### js (also TypeScript)

Each line, first rule that matches (names are `[A-Za-z_$][\w$]*`):

1. `^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\b\s*\*?\s*(NAME)` -> `"function"`
2. `^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(NAME)` -> `"class"`
3. `^\s*(?:export\s+)?(?:const|let|var)\s+(NAME)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|NAME\s*=>)`
   -> `"function"`
4. `^export\s+(?:const|let|var)\s+(NAME)` -> `"const"`
5. `^\s*(?:export\s+)?(?:interface|type)\s+(NAME)` -> `"type"`

### rust

Each line, first rule that matches:

1. `^\s*(?:pub(?:\([^)]*\))?\s+)?(?:(?:async|const|unsafe|extern(?:\s+"[^"]*")?)\s+)*fn\s+(\w+)`
   -> `"fn"`
2. `^\s*(?:pub(?:\([^)]*\))?\s+)?(struct|enum|trait|mod|type)\s+(\w+)` -> the kind is the
   keyword itself, the name the second group.
3. `^\s*impl\b(?:\s*<[^>]*>)?\s+([^{]+?)\s*(?:\{.*)?$` -> `"impl"`; the name is the group with
   every run of whitespace replaced by one space.

### ahk (AutoHotkey v1)

Only lines that start in column 0 (no leading space or tab) can define anything. First rule
that matches:

1. A function: `^([A-Za-z_][\w#@$]*)\(([^()]*)\)\s*(\{)?\s*(?:;.*)?$`, the name lower-cased is
   not one of `if while for loop return switch else catch until`, and either the line has the
   `{` or the next line that is not blank and does not start with `;` (after stripping) starts
   with `{` -> `"function"`.
2. A hotstring: `^(:[^:\s]*:[^:]+)::` -> `"hotstring"` (name is the group, e.g. `:*:btw`,
   `::btw` for `::btw::`).
3. A label: `^([A-Za-z_][\w#@$]*):\s*(?:;.*)?$` -> `"label"`.
4. A hotkey: `^([^\s;:][^:]*?)::` -> `"hotkey"` (name is the group, e.g. `^!t`).

## render_outline(path, symbols, max_lines=80)

1. First line: `path`.
2. No symbols: a second line `"  (no symbols found)"`.
3. Else one line per symbol, `f"  {line:>5}  {kind} {name}"`, for the first `max_lines`
   symbols; when there are more, a last line `f"  ... {n} more"` (n = how many were left out).
4. Lines joined with `"\n"`.

## repo_map(files, max_chars=6000)

`files` maps a path to its source.

1. Take the paths in sorted order, keeping only those `language_of` knows.
2. Each becomes a block: the path, then one line `f"  {kind} {name}"` per symbol of its
   outline (no line numbers), or the single line `"  (no symbols)"`; lines joined with `"\n"`.
3. Blocks are joined with `"\n"`. Add blocks while the text stays at most `max_chars` long.
   When the next block would go over, stop and add a last line
   `f"... {n} more files"` where n is how many known-language files were not shown (it may
   push the text slightly past max_chars). If even the first block does not fit, the result is
   just that last line.
4. No known-language files: `"(no code files)"`.

## Worked examples (the hidden tests walk every row)

| call | result |
|---|---|
| `language_of("a/B.PY")` | `"python"` |
| `language_of("x\\y.rs")` | `"rust"` |
| `language_of("Makefile")` / `language_of("dir.v2/README")` | `None` / `None` |
| `outline("def a():\n  pass\nclass K:\n  def m(self): pass\n  async def n(self): pass\n  class In:\n    def deep(self): pass\nasync def b(): pass", "python")` | `[(1, "def", "a"), (3, "class", "K"), (4, "method", "K.m"), (5, "method", "K.n"), (8, "def", "b")]` |
| `outline("def ok(:\n    class X:\n  async def y(): pass", "python")` | `[(1, "def", "ok"), (2, "class", "X"), (3, "def", "y")]` (a syntax error: the line fallback) |
| `outline("export default async function main() {}\nexport class Box {}\nconst add = (a, b) => a + b\nlet f = async x => x\nexport const LIMIT = 3\ninterface P {}\nfunction* gen() {}", "js")` | `[(1, "function", "main"), (2, "class", "Box"), (3, "function", "add"), (4, "function", "f"), (5, "const", "LIMIT"), (6, "type", "P"), (7, "function", "gen")]` |
| `outline("pub(crate) async fn run() {}\nstruct S;\npub enum E { A }\nimpl<T: Clone> Display for Wrap<T> {\nimpl S\n  fn inner(&self) {}\nmod tests;", "rust")` | `[(1, "fn", "run"), (2, "struct", "S"), (3, "enum", "E"), (4, "impl", "Display for Wrap<T>"), (5, "impl", "S"), (6, "fn", "inner"), (7, "mod", "tests")]` |
| `outline("Greet(name) {\n}\nHelper(x)\n; comment\n{\n}\nif(x)\n{\n:*:btw::by the way\n::omw::on my way\nStart:\n^!t::MsgBox\n  Indented() {\nCall(x)\nnext()", "ahk")` | `[(1, "function", "Greet"), (3, "function", "Helper"), (9, "hotstring", ":*:btw"), (10, "hotstring", "::omw"), (11, "label", "Start"), (12, "hotkey", "^!t")]` |
| `outline("x", "cobol")` | `[]` |
| `render_outline("a.py", [])` | `"a.py\n  (no symbols found)"` |
| `render_outline("a.py", [(1, "def", "f"), (12, "class", "K")])` | `"a.py\n      1  def f\n     12  class K"` |
| `render_outline("a.py", [(i, "def", "f") for i in range(1, 6)], 2)` | `"a.py\n      1  def f\n      2  def f\n  ... 3 more"` |
| `repo_map({"b.py": "def f(): pass", "a.rs": "fn g() {}", "notes.txt": "x"})` | `"a.rs\n  fn g\nb.py\n  def f"` |
| `repo_map({"a.py": ""})` | `"a.py\n  (no symbols)"` |
| `repo_map({"r.md": "x"})` | `"(no code files)"` |
| `repo_map({"a.py": "def f(): pass", "b.py": "def g(): pass"}, 12)` | `"a.py\n  def f\n... 1 more files"` |
| `repo_map({"a.py": "def f(): pass"}, 3)` | `"... 1 more files"` |
