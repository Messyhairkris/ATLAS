# Contract: ahk_api.py — which functions an AutoHotkey file defines

One Python module, `ahk_api.py`, the part of the **AutoHotkey v1** gate that checks a
crew module against its contract: are all the promised functions there, does any of
them do nothing, and is there code outside the functions that would run the moment the
file is included.

It builds on `ahk_lex.py`, already accepted. **Import it and use it**:

```python
from ahk_lex import code_lines
```

## Public API (all of these names must exist)

```python
KEYWORDS = frozenset({...})    # see below
def functions(source: str) -> dict: ...
def missing(source: str, api) -> list: ...
def stubs(source: str) -> list: ...
def top_level(source: str) -> list: ...
```

Allowed imports: `re`, plus `ahk_lex` as shown. Nothing else.

Everything below works on `code_lines(source)`: comments and string contents are
already blanked, and blank lines are gone.

## KEYWORDS

A `frozenset` of lowercase words that look like a function call at the start of a line
but are not a definition. At least: `if while for loop switch catch return else until
try throw finally and or not`.

## functions(source)

A function definition, in AutoHotkey v1, is a code line that is exactly

    Name(parameters) {        or        Name(parameters)
                                        {

- `Name` is a letter or `_` then letters, digits or `_`, and its lowercase form is
  **not** in `KEYWORDS` (so `if (x) {` is not a function);
- the parentheses contain no other parentheses;
- either `{` ends the same line (after optional whitespace), or the line ends at `)`
  and the **next code line** is `{` alone (after stripping). Otherwise it is not a
  definition - it is a call.

The body runs from the line after the opening `{` to the line **before** the `}` that
brings the brace count back to zero. Count `{` and `}` across the lines, starting with
the line that holds the opening `{`. If the braces never balance, the body runs to the
last code line.

Returns a dict keyed by the **lowercase** name (AutoHotkey names are case-insensitive):

```python
{"add": {"name": "Add",            # as written
         "params": ["a", "b"],     # names only
         "line": 3,                # line of the Name(...) text
         "end": 5,                 # line of the closing }
         "body": ["return a + b"]} # stripped code lines of the body
}
```

Parameter names: split the text between the parentheses on `,`; strip each part; drop
a leading `ByRef ` (any case); cut at the first `:=`, `=` or `*`, and strip again.
Empty parts are skipped. So `ByRef text, b := 1, rest*` → `["text", "b", "rest"]`.

Scanning continues after a function's closing `}` - a definition is never found inside
another one.

## missing(source, api)

The names from `api`, in `api`'s order and spelling, that `functions(source)` does not
define. Compared without case: `api=["ADD"]` is satisfied by `Add(a) {`.

## stubs(source)

Names (as written), in definition order, of functions whose body has no statement,
or only statements that are exactly `return` (any case) - ignoring body lines that are
just `{` or `}`.

## top_level(source)

Line numbers, in order, of code lines that are **outside every function** - between a
function's `line` and `end`, inclusive, counts as inside - and are **neither**:

- a constant: a name, `:=`, and something after it (`Greeting := "hello"`), nor
- a directive: code starting with `#` (the safety scanner judges those).

Code at the top of an AutoHotkey file runs the moment the file is included; a crew
module must not do anything on its own.

## Example

```
Greeting := "hello"            ; line 1

Add(a, b := 1) {               ; line 3
    return a + b
}

Stub(x)                        ; line 7
{
    return
}
MsgBox, done                   ; line 11
```

- `functions` → keys `add`, `stub`; `add` has params `["a", "b"]`, line 3, end 5, body
  `["return a + b"]`; `stub` has line 7, end 10, body `["return"]`
- `missing(source, ["ADD", "Wrap"])` → `["Wrap"]`
- `stubs` → `["Stub"]`
- `top_level` → `[11]`

## Style

See `HOUSE_STYLE.md`, which is part of this contract.
