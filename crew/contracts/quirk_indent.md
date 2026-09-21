# Contract: quirk_indent.py - text copied from a contract, re-indented

Part of the crew's **quirk linter**: zero-token checks for mistakes a model is known to
make, run before the gates. This one is Nemotron's: when a contract gives a page template
to reproduce byte for byte, it re-indents the lines "nicely" - in one real attempt, 29 of
them. This module finds those lines in the member's source and puts the contract's
indentation back. Pure text in, pure data out.

## Public API

```python
VERBATIM_TAGS = ("html", "text", "verbatim")
MIN_CHARS = 6

def verbatim_lines(contract: str) -> list[str]: ...
def indent_drift(source: str, lines: list[str]) -> list[dict]: ...
def fix_indent_drift(source: str, lines: list[str]) -> tuple[str, int]: ...
```

Allowed imports: `re`. Nothing else.

## verbatim_lines(contract)

1. A fenced block starts with a line of three backticks followed by an info string and
   ends at the next line that starts with three backticks. Only blocks whose info
   string, stripped and lowercased, is in `VERBATIM_TAGS` count.
2. From those blocks take every line (split on `\n`) whose stripped text is at least
   `MIN_CHARS` characters long, keeping its leading spaces.
3. Return them in order of appearance, each distinct line once.

## The key of a verbatim line

A **placeholder** is `{`, then a character that is not whitespace and not a brace, then
any non-brace characters, then `}` - regex `\{[^{}\s][^{}]*\}`. So `{css}` and
`{S(modules)}` are placeholders; `{ type: "x" }` (space after the brace) is not.

A line's **key** is its text before the first placeholder (the whole line if there is
none), stripped. Its **indent** is the number of leading spaces of the whole line. Keys
shorter than `MIN_CHARS` are ignored. If two lines have the same key, the FIRST one's
indent is used.

## indent_drift(source, lines)

Scan `source` line by line (split on `\n`, numbered from 1). In each line find the string
literals - a `"` or `'`, then characters where a backslash escapes the next one, up to
the same unescaped quote (regex `(["'])((?:\\.|(?!\1).)*)\1`). For each literal, take
its contents; if they end with the two characters backslash-`n`, drop those two. Call
the result `core`.

A literal **drifts** when `core.strip()` is a key and the leading spaces of `core` differ
from that key's indent. Report each as
`{"line": <line number>, "text": <core.strip()>, "expected": <indent>, "found": <core's leading spaces>}`,
in source order.

## fix_indent_drift(source, lines)

Return `(fixed_source, count)`: every drifting literal gets exactly the expected number
of leading spaces (its other characters, including a trailing backslash-`n` and the
quotes, unchanged), and `count` is how many literals were changed. Nothing else in the
source changes. Fixing a source with no drift returns it unchanged and `0`, and fixing
twice changes nothing the second time.

## Worked examples

Contract (as the argument to `verbatim_lines`):

````
```html
<head>
  <title>{escaped title}</title>
  var MODULES = {S(modules)};
}
```
```js
    not verbatim, wrong tag
```
````

gives `["<head>", "  <title>{escaped title}</title>", "  var MODULES = {S(modules)};"]`
(`}` is too short; the js block is not verbatim). Keys: `<head>` -> 0, `<title>` -> 2,
`var MODULES =` -> 2.

| source line | indent_drift finding |
|---|---|
| `'<head>',` | none (already 0) |
| `'  <head>',` | line 1, text `<head>`, expected 0, found 2 |
| `"    <title>" + t + "</title>"` | line 1, text `<title>`, expected 2, found 4 |
| `'        var MODULES = ' + x + ';\n'` | line 1, text `var MODULES =`, expected 2, found 8 |
| `"  <head>\n"` (ends with backslash-n) | line 1, text `<head>`, expected 0, found 2 |
| `const s = "  hello there";` | none (not a key) |

| source | fix_indent_drift |
|---|---|
| `a = ['  <head>', "    <title>"];` | `(a = ['<head>', "  <title>"];, 2)` |
| `x = "  <head>\n";` | `(x = "<head>\n";, 1)` |
| `y = '<head>';` | `(y = '<head>';, 0)` |
