# Contract: str.ahk - composable string helpers (AutoHotkey v1.1)

One self-contained AutoHotkey v1.1 module, `str.ahk`, holding only pure functions:
text in, value out. It gives callers expression-mode helpers that return NEW strings
instead of mutating a variable in place the way the legacy `StringLower` command does,
plus the default/coalesce helpers every script otherwise re-implements as nested
ternaries. It is the foundation module of the campaign; later modules (regex, CSV,
list helpers) normalize text and supply defaults through these exact functions.

It depends on nothing: no `#Include` of any other file is needed or wanted.

## Public API (all of these names must exist)

```ahk
Lower(text)                       ; NEW string: text lowercased (StringLower semantics)
Upper(text)                       ; NEW string: text uppercased (StringUpper semantics)
Title(text)                       ; NEW string: title case (StringLower's "T" mode)
Default(value, fallback := "")    ; fallback only when value == "", else value
Coalesce(values*)                 ; first argument that is not "", else ""
```

Allowed: AutoHotkey v1.1 built-in functions and commands that only compute a value (StringLower, StringUpper, StrLen, SubStr, InStr, StrSplit, RegExReplace...). Nothing that touches windows, keys, clipboard, files, registry or time.

Form: every line of code lives inside one of the five functions. Nothing runs at
include time - no loose statements, no labels, no hotkeys, no dynamic dereference.

## Rules

1. **Lower(text)** returns a NEW string: every letter of `text` lowercased exactly the
   way `StringLower` does it, every other character untouched. `Lower("AbC")` is
   `"abc"`. The parameter is unchanged after the call (rule 10).
2. **Upper(text)** is the same, uppercased. `Upper("AbC")` is `"ABC"`.
3. **Title(text)** is `StringLower`'s `"T"` mode, exactly: the first letter of each
   word becomes upper case and every other letter becomes lower case. A new word
   starts only after a SPACE - a hyphen or an apostrophe does NOT start one
   (verified in real AutoHotkey v1.1 in Windows Sandbox, 2026-09-26):
   - `Title("hello world")` is `"Hello World"`
   - `Title("hELLO wORLD")` is `"Hello World"` (already-mixed case is RESET, not kept)
   - `Title("the-end")` is `"The-end"` (the hyphen does not start a word)
   - `Title("don't stop")` is `"Don't Stop"` (nor does the apostrophe)
4. **Default(value, fallback) - the empty string `""` is the ONLY empty value.**
   `0`, `"0"`, `false` and `" "` (a single space) are all values, never "empty".
   - `Default("", "fb")` is `"fb"`
   - `Default("x", "fb")` is `"x"`
   - `Default("0", "fb")` is `"0"`
   - `Default(0, "fb")` is `0`
   - `Default(" ", "fb")` is `" "`
   Write the test explicitly as `== ""` (or `= ""`). A truthiness test `if (value)` is
   a BUG: in AutoHotkey v1.1 the string `"0"` is falsy, so it would wrongly replace
   `"0"` and `0` with the fallback.
5. `Default(value)` called with no fallback behaves as if the fallback were `""`:
   `Default("")` is `""`, `Default("y")` is `"y"`.
6. **Coalesce(values*)** returns the FIRST argument that is not `""`. It returns `""`
   when every argument is an empty string, and also `""` when called with no arguments
   at all:
   - `Coalesce()` is `""`
   - `Coalesce("")` is `""`
   - `Coalesce("", "", "")` is `""`
   - `Coalesce("", "", "x")` is `"x"`
   - `Coalesce("a", "b")` is `"a"`
   - `Coalesce("", 0, "x")` is `0` (zero is a value; same "0"-is-falsy trap as rule 4)
7. Empty input is legal for every function: `Lower("")`, `Upper("")` and `Title("")`
   are all `""`.
8. Non-ASCII letters are converted exactly the way `StringLower`/`StringUpper` convert
   them on the Unicode build (so `Lower("ÀÉÎ")` is `"àéî"` and `Upper("àéî")` is
   `"ÀÉÎ"`); digits and punctuation never change. Do not write your own
   character tables - call the commands.
9. A number passed where text is expected is read as its text form: `Lower(42)` is
   `"42"`, `Title(100)` is `"100"`. A fallback may be a number: `Default("", 7)` is `7`.
10. The caller's variables are never modified. Parameters are by value; use no
    `ByRef` and write nothing to a global. After `s := "AbC"` and `Lower(s)`, `s` is
    still `"AbC"`.
11. The functions are pure and composable: same input, same output, every call, and
    they nest freely inside one expression - `Upper(Lower("AbC"))` is `"ABC"`,
    `Default(Title(""), "empty")` is `"empty"`.

## How the case commands work (read this before writing a line)

`StringLower` and `StringUpper` are legacy COMMANDS with no return value. This is the
shape every correct implementation of rules 1-3 uses:

```ahk
Lower(text) {
    local out := ""
    StringLower, out, text      ; command writes INTO out; it returns nothing
    return out
}
```

`return StringLower(text)` silently yields `""` - there is nothing to return. Title
case is the same command with a third parameter `T`: `StringLower, out, text, T`.

## Worked examples

| call | returns |
|---|---|
| `Lower("AbC")` | `"abc"` |
| `Upper("AbC")` | `"ABC"` |
| `Title("hELLO wORLD")` | `"Hello World"` |
| `Title("don't stop")` | `"Don't Stop"` |
| `Default("", "fb")` | `"fb"` |
| `Default("0", "fb")` | `"0"` |
| `Default("")` | `""` |
| `Coalesce("", "", "x")` | `"x"` |
| `Coalesce("", 0, "x")` | `0` |
| `Coalesce()` | `""` |
| `Upper(Lower("AbC"))` | `"ABC"` |

## Edge cases, stated outright

- **Empty input:** `""` in, `""` out for `Lower`/`Upper`/`Title` (rule 7);
  `Default`/`Coalesce` treat `""` as the only absence of a value (rules 4-6).
- **Non-ASCII letters** follow the `StringLower`/`StringUpper` commands, whatever they
  do; on the Unicode build that means `À` becomes `à`. Not your algorithm to invent.
- **Numbers passed where text is expected** are stringified (rule 9); nothing errors.
- **Title on already-mixed case** resets it (`"hELLO"` to `"Hello"`), and **Title on
  words with hyphens or apostrophes** does NOT capitalize after them (`"don't"` to
  `"Don't"`, `"the-end"` to `"The-end"`) - that is what the `"T"` mode does (rule 3).
- **Coalesce with zero arguments** returns `""`; with only empty strings, `""` (rule 6).
- **Input variables are left unchanged** by every function (rule 10).
- The file is saved as UTF-8 with BOM, so non-ASCII text in rules 1, 2 and 8 behaves.

## A careless implementation cannot pass

The following look plausible and are all wrong, with the rule that convicts them:
`return StringLower(text)` (rule 1 - commands return nothing, this yields `""`);
`if (value)` as the empty test in `Default` or `Coalesce` (rules 4 and 6 - `"0"` is
falsy); a Title that hand-capitalizes instead of calling the `"T"` mode (rule 3 -
hyphens and mixed case give it away); a `Default` whose fallback has no default
value (rule 5); a `Coalesce` that errors or returns an object when called with no
arguments (rule 6).
