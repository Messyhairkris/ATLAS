# Contract: verbalize.py — turning text into what the voice says

One self-contained Python module, `verbalize.py`. Pure text in, pure text out:
no audio, no devices, no files.

This is the **Verbatim level** from TTS_SPEC_DRAFT.md section 3 — Kris asked for
"a version that speaks all of the edits, speaking line breaks, apostrophes,
commas question marks and more". A dictation user cannot see the screen while
speaking, so at the verbatim level the voice names every mark it typed.

## Public API

```python
LEVELS = ("off", "brief", "normal", "full", "verbatim")
PUNCTUATION = {...}                      # character -> spoken name
ELLIPSIS = "ellipsis"

def collapse_whitespace(text: str) -> str: ...
def verbalize(text: str, level: str = "normal") -> str: ...
```

Allowed imports: `re`, `typing`. Nothing else.

## PUNCTUATION

A dict from a single character to its spoken name. It must contain at least:

| char | spoken name |
|---|---|
| `,` | `comma` |
| `.` | `period` |
| `?` | `question mark` |
| `!` | `exclamation mark` |
| `'` | `apostrophe` |
| `"` | `quote` |
| `;` | `semicolon` |
| `:` | `colon` |
| `-` | `dash` |
| `(` | `open parenthesis` |
| `)` | `close parenthesis` |
| `\n` | `line break` |
| `\t` | `tab` |

## collapse_whitespace(text)

Every run of whitespace becomes a single space; leading and trailing whitespace
is removed. `collapse_whitespace("a  \n b\t")` is `"a b"`. `""` gives `""`.

## verbalize(text, level="normal")

- `level` not in `LEVELS` raises `ValueError`.
- `level == "off"` returns `""` for any text at all.
- `level` in `("brief", "normal", "full")` returns `collapse_whitespace(text)`:
  the words as written, punctuation left in the text, not named.
- `level == "verbatim"` names every mark:
  1. first, each run of three or more periods becomes `ELLIPSIS`
     (`"wait..."` -> `"wait ellipsis"`);
  2. then every character in `PUNCTUATION` is replaced by its spoken name,
     surrounded by spaces, wherever it appears, **including inside a word**;
  3. then the result is whitespace-collapsed.
- `""` returns `""` at every level.

Worked examples, which the tests use:

| text | level | result |
|---|---|---|
| `"Hello, world."` | `"verbatim"` | `"Hello comma world period"` |
| `"don't"` | `"verbatim"` | `"don apostrophe t"` |
| `"What?!"` | `"verbatim"` | `"What question mark exclamation mark"` |
| `"line one\nline two"` | `"verbatim"` | `"line one line break line two"` |
| `"wait..."` | `"verbatim"` | `"wait ellipsis"` |
| `"a (b) c"` | `"verbatim"` | `"a open parenthesis b close parenthesis c"` |
| `"Hello, world."` | `"normal"` | `"Hello, world."` |
| `"anything"` | `"off"` | `""` |

Characters that are not in `PUNCTUATION` are left exactly as they are, at every
level: `verbalize("café #1", "verbatim")` keeps `café` and `#1`.

## Style

Type hints, a one-line docstring per function naming the rule it implements, no
`print()`. Write the complete file.
