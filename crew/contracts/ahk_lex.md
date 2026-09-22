# Contract: ahk_lex.py — tell AutoHotkey code from comments and strings

One self-contained Python module, `ahk_lex.py`. It is the first part of the gate that
will judge crew-written **AutoHotkey v1** scripts, and everything else in that gate
asks it one question: *is this word code?* A scanner that bans `Run` must not refuse
`; Run it later` in a comment or `"Run"` inside a string, and must not miss a real
`Run` that follows one.

It reads text only. It never runs AutoHotkey.

## Public API (all of these names must exist)

```python
def mask(source: str) -> str: ...
def unterminated(source: str) -> list: ...
def code_lines(source: str) -> list: ...
```

Allowed imports: `re`. Nothing else.

## The AutoHotkey v1 rules this follows

The source is split on `"\n"`. A line ending in `"\r"` keeps its `"\r"` untouched, so
Windows line endings survive; the `"\r"` is never part of the rules below.

**Block comments.** A line whose text, after leading spaces and tabs, **starts with**
`/*` opens a block comment. Every line from there up to and including the next line
whose text, after leading whitespace, starts with `*/` is comment - whole lines,
whatever else is on them. `/* x */` written on one line therefore still opens a block,
exactly as AutoHotkey v1 treats it. A block never closed runs to the end of the file.

**Within any other line**, read left to right:

1. **Backtick escape.** A `` ` `` outside a string, with a character after it: both
   characters are code and are kept as they are. So `` a`;b `` is code - the `;` is
   escaped.
2. **String.** A `"` outside a string opens one. Inside it:
   - `""` is an escaped quote and stays inside the string;
   - a `` ` `` and the character after it stay inside the string;
   - the next single `"` closes it.
   A string still open at the end of the line ends there (strings never span lines).
3. **Line comment.** A `;` outside a string starts a comment that runs to the end of
   the line **when** it is the first non-blank character of the line **or** the
   character just before it is a space or a tab. `a;b` is not a comment.

## mask(source)

Returns text of **exactly the same length and line structure** as `source`:

- every character of a block comment line becomes a space;
- a line comment - its `;` and everything after it - becomes spaces;
- the **contents** of a string become spaces, and so does each `""` or escape pair
  inside it; the opening and closing `"` characters are **kept**;
- everything else is unchanged, including backtick escapes outside strings.

Example (`·` shows a space):

| line | masked |
|---|---|
| `Add(a, b) {  ; sum` | `Add(a, b) {······` |
| `s := "x; not a comment" ; real` | `s := "················"·······` |
| `t := "say ""hi"""` | `t := "··········"` |
| `` u := a`;b `` | `` u := a`;b `` |
| `/*` / `Run, notepad.exe` / `*/` | three lines of spaces, the same lengths |

## unterminated(source)

The 1-based numbers of lines, in order, where a string was opened and not closed by
the end of that line. Lines inside a block comment never count.

`unterminated('ok := "fine"\nbad := "open')` → `[2]`

## code_lines(source)

`[(line_number, masked_text), ...]` for every line whose masked text is not blank,
1-based, in order, with any trailing `"\r"` removed from the text.

## Style

See `HOUSE_STYLE.md`, which is part of this contract.
