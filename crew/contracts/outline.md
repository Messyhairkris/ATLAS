# Contract: outline.py - a file's structure at a glance

One self-contained Python module, `outline.py`. Given the *text* of a file and
its kind, it returns an outline: one entry per structural line, so a reader can
see a file's shape before reading it. Two kinds are supported: `"python"`
(`def`, `async def` and `class` lines, top-level and nested, found by their
leading keyword and indentation - the module may NOT use the `ast` module) and
`"markdown"` (ATX headings `#` to `######`, ignoring lines inside fenced code
blocks). A second function renders an outline as plain text lines.

## Public API (all of these names must exist)

```python
@dataclass(frozen=True)
class Entry:
    line: int      # 1-based line number in the source text
    depth: int     # 0 = outermost (see the kind's depth rule)
    kind: str      # "class" | "def" | "async def" | "heading"
    name: str      # the identifier, or the heading text (may be "")

def outline(text: str, kind: str) -> list: ...   # list of Entry, file order
def render(entries: list) -> str: ...
```

Allowed imports: `dataclasses`, `re`, and `from __future__ import annotations`.
Nothing else. No `ast`, no `open`, no file or network access: the text arrives
as an argument.

## outline(text, kind)

1. `kind` `"python"` applies the Python rules below; `"markdown"` the Markdown
   rules. ANY other kind - `"Python"`, `"mkd"`, `""`, `None` - raises
   `ValueError`, and it is raised before the text is scanned.
2. `text` is split into lines with `str.splitlines()`. Line numbers count from
   1 and blank lines count. Entries come back in file order.

## Python rules

1. A line yields an entry only when its first token is the keyword: optional
   leading spaces/tabs, then `class`, `def` or `async def` (single spaces or
   tabs between and after the words), then an identifier matching
   `[A-Za-z_][A-Za-z0-9_]*`. The `name` is that identifier; everything after it
   (`(`, `:`, base classes, defaults, ...) is ignored. `class Box(Mapping):`
   has name `"Box"`.
2. The keyword must be followed by whitespace. `defund():`, `defined = 1` and
   `classy:` are never entries.
3. Comments and strings never produce entries:
   - The scanner tracks triple-quoted strings across lines with simple
     counting, no backslash handling: scanning left to right, when outside a
     string a `#` ends the line (rest is a comment) and an occurrence of
     `"""` or `'''` opens a string; inside a string the next occurrence of the
     same delimiter closes it.
   - Any line that BEGINS while the scanner is inside such a string yields no
     entry, even if the string closes on that line. (So a docstring containing
     a `def ghost():` line adds nothing to the outline.)
   - Ordinary single/double-quoted one-liners are not tracked; they cannot
     produce entries because the keyword must be the line's first token, so
     `text = "def fake():"` is never an entry.
4. Decorator lines (`@...`) are ordinary lines: no entry, and no effect on the
   depth of the decorated `def`/`class`.
5. Indentation width is computed from the leading whitespace only: a space is
   one column, a tab advances to the next multiple of 8 (Python's own rule).
6. Depth comes from a stack of the widths of open `class`/`def` blocks. For
   each entry line: pop every open block whose width is >= this line's width;
   `depth` is the number of blocks left; then push this line's width. So a
   method of a top-level class is depth 1, a function nested inside that method
   is depth 2, and the next top-level `def` after a class is depth 0 again.
7. Anything else (`lambda`, calls, assignments) is invisible to the outline.

## Markdown rules

1. Fence tracking: any line whose left-stripped text starts with three or more
   backticks OR three or more tildes toggles fenced-code state. Fence lines and
   lines inside a fenced block never yield headings. An unclosed fence swallows
   the rest of the file.
2. A heading is a line outside fences matching: 0-3 leading spaces, then 1-6
   `#` characters, then either end of line or at least one space/tab. Four or
   more leading spaces, seven or more hashes, or text glued to the hashes
   (`#tag`) mean NO heading.
3. The `name` is the text after the hashes, leading and trailing spaces/tabs
   stripped; then a closing run of `#` characters is removed if it is the whole
   remaining text or is preceded by a space/tab; then stripped again. So
   `## Title ##` -> `"Title"`, `### C#` -> `"C#"`, `#` alone -> `""`.
4. `depth` is the number of hashes minus 1. `kind` is `"heading"`.
5. Setext headings are NOT supported: a line of `===` or `---` under text
   yields nothing.

## render(entries)

1. One line per entry: `"  " * depth` (two spaces per depth level), then
   `"L<line>  <kind> <name>"` - a capital L, the line number, TWO spaces, the
   kind, ONE space, the name. Example at depth 0: `L12  def parse`.
2. The lines are joined with `"\n"`, with NO trailing newline. An empty
   outline renders as `""`.

## Examples

```python
outline("class App:\n    def start(self):\n        def helper():\n"
        "            pass\n", "python")
# [Entry(1, 0, "class", "App"), Entry(2, 1, "def", "start"),
#  Entry(3, 2, "def", "helper")]
# render(...) == "L1  class App\n  L2  def start\n    L3  def helper"

outline("# Guide\n```\n# nope\n```\n## Install ##\n", "markdown")
# [Entry(1, 0, "heading", "Guide"), Entry(5, 1, "heading", "Install")]
# render(...) == "L1  heading Guide\n  L5  heading Install"

outline("x = 1\n", "html")   # ValueError
```

## Error behaviour

Only one error is specified: an unknown `kind` raises `ValueError`. Everything
else - empty text, odd indentation, unmatched fences or strings - is parsed by
the rules above and never raises.

## Style

See `HOUSE_STYLE.md`, which is part of this contract.
