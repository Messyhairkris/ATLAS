# Contract: csv.ahk - parse and serialize CSV/DSV strings (AutoHotkey v1.1)

One self-contained AutoHotkey v1.1 module, `csv.ahk`, holding only pure functions:
text in, value out. It parses a CSV/DSV STRING (not a file, not the clipboard, not
the screen) into a 1-based array of 1-based row arrays, and serializes fields and
rows back with correct quoting. It replaces both the file-bound `CSV_Load` (which
needs `FileRead`, banned) and the dynamic-variable cell store (which needs `%`,
banned) - this is the crew's first CSV module anyone may actually use.

It depends on nothing: no `#Include` of any other file is needed or wanted. The
parser is a plain character loop; it does NOT use the regex module.

## Public API (all of these names must exist)

```ahk
CsvParse(text, delim := ",", encap := """")   ; 1-based array of 1-based row arrays
CsvEscape(cell, delim := ",", encap := """")  ; one field, ready for a CSV line
CsvRow(fields, delim := ",", encap := """")   ; 1-based array of fields -> one line
```

`CsvParse` returns a 1-based array of **rows**; each row is a normal 1-based array
of field strings: `rows[2][3]` is row 2, field 3. Every field is a string
(`"007"` stays `"007"`; nothing is converted to a number by the module).

`delim` and `encap` are each exactly ONE character. The default encapsulator is
the double-quote character: the default parameter `encap := """"` is a string of
length 1 holding `"` (a literal quote inside an AutoHotkey string is written `""`).
Passing a longer `delim` or `encap` is outside this contract.

Allowed: AutoHotkey v1.1 built-in functions that only compute a value (SubStr,
InStr, StrLen, StrReplace, StrSplit, Asc...). Nothing that touches windows, keys,
clipboard, files, registry or time.

Form: every line of code lives inside a function. Nothing runs at include time -
no loose statements, no labels, no hotkeys, no dynamic dereference, no `%`
anywhere. Private helper functions are fine as long as the three public names
exist with exactly these spellings and parameters.

## How the pieces work (read this before writing a line)

- The parser must be a **character loop** over `SubStr(text, i, 1)`. Two tempting
  shortcuts are both wrong:
  - `Loop, Parse, text, `n, `r` splits on `n and strips EVERY `r character -
    including a bare `r` that is DATA inside a field, and `r` characters inside
    quoted fields. It also has no idea what a quote is, so a quoted line break
    wrongly ends the row. Do not use it.
  - The stock library's regex lookahead (`ReturnDSVArray`) cannot be copied: it
    stores results through `%`-double-dereference, which the scanner bans
    outright, and relies on `SetFormat` hex tricks. A clean character loop is
    shorter than either workaround.
- `InStr(haystack, needle)` returns the 1-based position or **0 when absent**;
  0 is falsy, so `if (InStr(cell, x))` is a correct "contains" test. But
  `if (value)` is NOT a correct "is empty" test: the string `"0"` is falsy.
  Compare `value == ""` explicitly where emptiness matters.
- `==` compares case-sensitively, `=` case-insensitively. The character loop
  compares single characters with `==` so `"A"` and `"a"` never blur.
- A literal quote inside an AutoHotkey string is doubled: `"a""b"` is the text
  `a"b`. A line break is the backtick escape `n (`` `r`n `` is CRLF). Never
  a backslash.
- Arrays are 1-based, created with `[]`, extended with `.Push(value)`, measured
  with `.Length()`. They are passed and returned BY REFERENCE: build fresh row
  arrays inside `CsvParse`; never hand the caller's array back modified.
- `StrReplace(haystack, needle, replacement)` exists since v1.1.21 and returns a
  NEW string. Use it for doubling encapsulators; do not write a hand loop.

## Rules

1. **Basic parse.** `CsvParse("a,b`nc,d")` returns the 2-row array
   `[["a","b"], ["c","d"]]`: `rows.Length()` is 2, `rows[1][1]` is `"a"`,
   `rows[1][2]` is `"b"`, `rows[2][1]` is `"c"`, `rows[2][2]` is `"d"`.
2. **Fields are kept verbatim - nothing is trimmed, nothing is converted.**
   `CsvParse("a b, c x")` is `[["a b", " c x"]]` (the leading space of the
   second field is data). `CsvParse("007")` is `[["007"]]`, a string.
3. **Quoted fields.** A field whose FIRST character is the encapsulator is a
   quoted field: quotes are removed, and a doubled encapsulator inside is one
   literal encapsulator:
   - `CsvParse("""a,b"",c")` (the text `"a,b",c`) is `[["a,b", "c"]]` - the
     delimiter inside quotes is data.
   - `CsvParse("""a""""b""")` (the text `"a""b"`) is `[["a""b"]]` - that is one
     field whose value is the three characters `a"b`.
   - Quoted spaces are kept: `CsvParse(""" a """)` (the text `" a "`) is
     `[[" a "]]`.
4. **Line breaks.** Both CRLF (`` `r`n ``) and a bare `` `n `` end a row, and can
   be mixed in one text: `CsvParse("a`r`nb`nc")` is three rows
   `[["a"], ["b"], ["c"]]`. A line break INSIDE a quoted field is data and is
   kept exactly as written:
   - `CsvParse("""x`r`ny"",z")` is `[["x`r`ny", "z"]]` (the CRLF stays a CRLF)
   - `CsvParse("""x`ny""")` is `[["x`ny"]]` (a bare `n stays a bare `n)
5. **The delimiter inside quotes is data** (rule 3); the delimiter outside
   quotes always ends the field, even when nothing has been read yet.
6. **Blank lines and trailing line breaks are skipped.** A line with no
   characters at all is not a row: it yields neither a row nor fields.
   - `CsvParse("a,b`n")` is `[["a","b"]]` - one row, no phantom second row
   - `CsvParse("a`n`n`n")` is `[["a"]]`
   - `CsvParse("a`n`nb")` is `[["a"], ["b"]]` - the blank middle line vanishes
7. **Empty text.** `CsvParse("")` returns an empty array (an object whose
   `Length()` is 0) - never `""`, never an error. A text holding ONLY line
   breaks, `CsvParse("`n`r`n")`, is likewise an empty array.
   `CsvParse` ALWAYS returns an object.
8. **Empty fields are real fields.** A trailing delimiter yields a trailing
   empty field; consecutive delimiters yield empty fields in the middle:
   - `CsvParse("a,")` is `[["a", ""]]` (two fields)
   - `CsvParse("a,,b")` is `[["a", "", "b"]]`
   - `CsvParse(",")` is `[["", ""]]`
9. **Lenient quotes (like the stock library).** A quote that is NOT the first
   character of a field is literal text. Characters after a field's closing
   quote and before its delimiter are appended to the field as-is:
   - `CsvParse("ab""c,d")` (the text `ab"c,d`) is `[["ab""c", "d"]]` - the
     value of field 1 is the four characters `ab"c`
   - `CsvParse("""ab""cd,e")` (the text `"ab"cd,e`) is `[["abcd", "e"]]`
   Nothing in CsvParse ever errors or returns an error string.
10. **Unterminated quoted field at the end of the text is LENIENT:** the rest
    of the text - line breaks included, exactly as written - is that field's
    data, and the field and its row are returned normally:
    `CsvParse("a,""b`nc")` (the text `a,"b`nc`) is the ONE row
    `[["a", "b`nc"]]`.
11. **A bare `` `r `` is data.** Only `` `r`n `` and `` `n `` end rows; a `r not
    followed by `n is an ordinary character, kept verbatim, outside quotes as
    well as inside: `CsvParse("a`rb,c")` is one row, `[["a`rb", "c"]]`.
12. **Custom delim and encap** are honored by all three functions, and the
    delimiter is the only field separator - any other character is data:
    - `CsvParse("a;b;c", ";")` is `[["a", "b", "c"]]`
    - `CsvParse("'a;b';c", ";", "'")` is `[["a;b", "c"]]`
    - `CsvParse("'a''b'", ";", "'")` is `[["a'b"]]` (doubled custom
      encapsulator unescapes exactly like doubled quotes)
    Outside quotes, a character that is neither `delim` nor a line break nor an
    opening `encap` is appended to the field, whatever it is.
13. **CsvEscape(cell, delim, encap)** returns the cell ready to sit in a CSV
    line: FIRST double every encapsulator in it, THEN wrap it in encapsulators
    - but only when it contains the delimiter, `` `n ``, `` `r ``, or the
    encapsulator. Otherwise the cell is returned unchanged:
    - `CsvEscape("plain")` is `plain`
    - `CsvEscape("a,b")` is `"a,b"`
    - `CsvEscape("a""b")` (cell `a"b`) is `"a""b"` - doubled, then wrapped
    - `CsvEscape("a`nb")` is `"a`nb"` and `CsvEscape("x`ry")` is `"x`ry"`
    - `CsvEscape("")` is `""` (empty stays empty, unwrapped)
    - `CsvEscape("a,b", ";")` is `a,b` (comma is not the delimiter there);
      `CsvEscape("a;b", ";")` is `"a;b"`
    Leading/trailing spaces never trigger wrapping. Doubling BEFORE wrapping is
    mandatory: wrapping first would quote the cell twice.
14. **CsvRow(fields, delim, encap)** joins a 1-based array through CsvEscape,
    delimiter between fields: `CsvRow(["a", "b"])` is `a,b` and
    `CsvRow(["a b", "c,d"])` is `a b,"c,d"`. A single-element array gives one
    field with no delimiter; an EMPTY array gives the empty string `""`.
    Numbers become their text form: `CsvRow([1, 2])` is `1,2`.
15. **Round trip.** For every field list, `CsvParse(CsvRow(fields))` returns
    `fields` element-for-element - including fields holding delimiters, quotes
    and line breaks - as a one-row result. ONE documented exception:
    `CsvRow([""])` is `""`, and `""` parses to the empty array (rule 7), so a
    lone empty field does not survive the round trip. `["", "x"]` round-trips
    fine (`,x` parses back to `["", "x"]`).
16. **Purity.** No `ByRef`, nothing written to a global, and the same inputs
    always give the same outputs. Two calls to `CsvParse("a,b")` return
    independent arrays; editing one must not change what a later call returns.

## Worked examples

| call | returns |
|---|---|
| `CsvParse("a,b`nc,d")` | `[["a","b"], ["c","d"]]` |
| `CsvParse("a b, c x")` | `[["a b"," c x"]]` |
| `CsvParse("""a,b"",c")` | `[["a,b","c"]]` |
| `CsvParse("""a""""b""")` | `[["a""b"]]` |
| `CsvParse("a`r`nb`nc")` | `[["a"],["b"],["c"]]` |
| `CsvParse("""x`r`ny"",z")` | `[["x`r`ny","z"]]` |
| `CsvParse("a,b`n")` | `[["a","b"]]` |
| `CsvParse("a`n`nb")` | `[["a"],["b"]]` |
| `CsvParse("")` | `[]` (object, `Length()` 0) |
| `CsvParse("a,")` | `[["a",""]]` |
| `CsvParse("ab""c,d")` | `[["ab""c","d"]]` |
| `CsvParse("a`rb,c")` | `[["a`rb","c"]]` (one row) |
| `CsvParse("a;b;c", ";")` | `[["a","b","c"]]` |
| `CsvParse("'a;b';c", ";", "'")` | `[["a;b","c"]]` |
| `CsvEscape("a,b")` | `"a,b"` (wrapped) |
| `CsvEscape("a""b")` | `"a""b"` (doubled, then wrapped) |
| `CsvEscape("plain")` | `plain` |
| `CsvEscape("")` | `""` |
| `CsvRow(["a b", "c,d"])` | `a b,"c,d"` |
| `CsvRow([])` | `""` |

## Edge cases, stated outright

- **Empty text** is `[]`; text holding only line breaks is `[]` (rule 7).
- **A trailing line break** adds nothing: `"a,b`n"` is exactly one row
  (rule 6). Multiple trailing blank lines are all swallowed (rule 6).
- **A blank line in the middle** is skipped entirely - no row, no empty field
  (rule 6). A line holding only spaces is NOT blank; `" "` is a one-field row.
- **A trailing delimiter** is a real empty trailing field (rule 8): `"a,"` is
  `["a", ""]`, distinct from the blank-line rule.
- **A bare `` `r ``** (not followed by `` `n ``) is kept as data, inside and
  outside quotes (rule 11). Inside quotes EVERY line break is data, kept
  exactly as written (rule 4).
- **Unterminated quoted field at end of text:** lenient - the rest of the
  text is the field's data (rule 10). Never an error.
- **Stray quote mid-field** is literal text (rule 9); junk after a closing
  quote is appended verbatim (rule 9).
- **Round-trip exception:** `CsvRow([""])` is `""`, which parses to `[]`
  (rule 15). Every other shape round-trips.
- **Whitespace is never trimmed** anywhere (rule 2).
- The file contains only ASCII; no BOM tricks are needed.

## A careless implementation cannot pass

The following look plausible and are all wrong, with the rule that convicts
them: `Loop, Parse, text, `n, `r` (rules 4 and 11 - it deletes bare-`r` data
and splits quoted fields at embedded line breaks); `StrSplit(text, "`n")`
followed by `StrSplit(line, delim)` (rules 3-5 - a quoted delimiter or line
break wrongly splits); trimming spaces from fields (rule 2); treating a bare
`r as a row terminator (rule 11); treating a blank middle line as a row of
`[""]` (rule 6); treating `"a,"` as ONE field (rule 8); wrapping a cell in
quotes before doubling its quotes (rule 13 - the quotes come out doubled
twice); wrapping every cell unconditionally (rules 13-14 - `plain` must stay
`plain`); quoting a cell because it has leading or trailing spaces (rule 13);
erroring on, or silently dropping, an unterminated quoted field (rule 10);
treating a stray mid-field quote as the start of quoting (rule 9); treating
the comma as a separator when `delim` is something else (rule 12);
0-based arrays (rule 1); `CsvParse("")` returning `""`, an error, or
`[[""]]` instead of `[]` (rule 7); checking for the encapsulator with
truthiness `if (InStr(...))` where the character loop should compare single
characters with `==` (rules 3, 9).
