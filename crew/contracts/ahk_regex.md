# Contract: regex.ahk - RegExMatch captures as real arrays (AutoHotkey v1.1)

One self-contained AutoHotkey v1.1 module, `regex.ahk`, holding only pure functions:
text in, value out. It turns AutoHotkey's `matchN` pseudo-variables and `RegExMatch`'s
match object into real 1-based arrays, so callers never hand-read `match1`, `match2`,
`match3` again and never write the global-match loop themselves. It is the crew's
reusable parsing tool: the CSV module and every future parse-text module consumes it.

It depends on nothing: no `#Include` of any other file is needed or wanted.

## Public API (all of these names must exist)

```ahk
MatchAll(text, needle)     ; 1-based array of capture arrays; empty array on no match
MatchFirst(text, needle)   ; one capture array, or "" when nothing matches
Count(text, needle)        ; number of matches (integer, 0 or more)
```

A **capture array** is a normal 1-based array: element `[1]` is the WHOLE match,
element `[2]` is capture group 1, element `[3]` is capture group 2, and so on, in
group-number order. A group that did not take part in the match is the empty string
`""` - it still occupies its slot (rule 6).

**Needles are ordinary AutoHotkey regex strings WITHOUT an `O)` prefix.** The caller
never writes `O)`; the module adds the object-mode request itself. If the caller's
needle begins with a legitimate option group such as `i)` or `m)` (option letters,
then a close-paren, at the very start of the needle), those options stay in effect:
the module keeps them at the start and merges its own request into that group without
moving anything (rule 10). One leading group is supported; writing TWO option groups
is outside this contract. Writing `O)` yourself is outside this contract.

Allowed: AutoHotkey v1.1 built-in functions that only compute a value (RegExMatch,
InStr, StrLen, SubStr, RegExReplace...). Nothing that touches windows, keys,
clipboard, files, registry or time.

Form: every line of code lives inside a function. Nothing runs at include time - no
loose statements, no labels, no hotkeys, no dynamic dereference, no `%` anywhere.
Private helper functions (not in the API above) are fine as long as the three public
names exist with exactly these spellings and parameters.

## How RegExMatch's object mode works (read this before writing a line)

- `pos := RegExMatch(text, pattern, m, start)` returns the 1-based position of the
  next match, or **0 on no match** (never -1).
- Prefixing the pattern with `O)` makes `m` a match **object** instead of filling the
  `matchN` pseudo-variables. The object answers:
  `m.Value(0)` the whole match; `m.Value(n)` the text of group n;
  `m.Count()` the number of capture groups (NOT counting the whole match);
  `m.Len(0)` and `m.Len(n)` lengths; `m.Pos(n)` positions.
  An unmatched optional group has `m.Value(n)` = `""`, `m.Len(n)` = 0, `m.Pos(n)` = 0.
- The **global loop**: after a match at `found` with length `L`, continue searching at
  `found + max(L, 1)`. A zero-length match (needle like `a*`) must still move one
  character, or the loop never ends. Never start a search beyond
  `StrLen(text) + 1`; a search starting exactly at `StrLen(text) + 1` is legal and can
  still match an empty pattern there.
- **Option letters live only at the START of the needle** as a run of letters closed
  by `)`. `O` may sit in the same group as caller options (`Oi)ab` is valid). Option
  letters anywhere else change the regex's meaning or make it invalid.
- The `matchN` pseudo-variable route (plain RegExMatch without `O)`) cannot be
  collected generically without `%`-double-dereference, which the scanner bans
  outright. Use the object mode; there is no other acceptable way.
- A literal quote inside a needle string is written doubled in source: the needle
  `"""(.*?)"""` is the regex `"(.*?)"`. Never escape quotes with backslash.

## Rules

1. **MatchAll(text, needle)** returns a 1-based array holding one capture array per
   match, in the order the matches occur in `text`. Each capture array's `[1]` is the
   whole match and `[2]`, `[3]`, ... are groups 1, 2, ... in order:
   `MatchAll("a1 b2", "([a-z])(\d)")` is the 2-element array
   `[ ["a1","a","1"], ["b2","b","2"] ]`.
2. A needle with **no capture groups** produces capture arrays of length 1 (just the
   whole match): `MatchAll("a1 b2", "\d")` is `[ ["1"], ["2"] ]`.
3. **No match is an empty array, never an error and never `""`.** `MatchAll` always
   returns an object; when nothing matches its `Length()` is 0, and the same holds for
   empty text: `MatchAll("xyz", "\d+")` and `MatchAll("", "\d+")` both have
   `Length()` 0.
4. **MatchFirst(text, needle)** returns the capture array of the FIRST match, or the
   empty string `""` when nothing matches:
   - `MatchFirst("Price: $99.50", "\$(\d+)\.(\d+)")` is `["$99.50", "99", "50"]`
   - `MatchFirst("xyz", "\d+")` is `""`
   - `MatchFirst("", "\d+")` is `""`
   - `MatchFirst("a1 b2", "([a-z])")` has `[1]` = `"a"` (the first match only).
5. **Count(text, needle)** returns how many matches there are, as an integer, 0 when
   there are none. For every needle, `Count(text, needle)` equals
   `MatchAll(text, needle).Length()`:
   `Count("a1 b2 c3", "\d")` is 3, `Count("xyz", "\d")` is 0, `Count("", "\d+")` is 0.
6. **An unmatched optional group is the empty string at its slot, not a missing
   slot.** `MatchFirst("ab", "(a)(c)?(b)")` is `["ab", "a", "", "b"]` - a 4-element
   array whose element `[3]` is `""`.
7. **Matches do not overlap and are consumed left to right.** After a match, the
   search continues after the whole match, not one character after its start:
   `Count("aaa", "aa")` is 1; `Count("aaaa", "aa")` is 2.
8. **Zero-length matches count, and the scan still moves one character.** The exact
   values (stated, not to be re-derived):
   - `MatchAll("bc", "a*")` is a 3-element array; every element is `[""]`
     (an empty match at position 1, 2, and 3 - including one past the last character)
   - `Count("bc", "a*")` is 3
   - `Count("banana", "a*")` is 7 ("", "a", "", "a", "", "a", "")
   - `Count("", "a*")` is 1 (an empty needle-matched string on empty text)
9. The needle is an ordinary AutoHotkey regex, **case-sensitive by default**:
   `Count("aAa", "a")` is 2. Anchors (`^`, `$`), classes and backslash escapes behave
   as they always do in `RegExMatch`: `Count("abc", "^abc$")` is 1. An empty needle
   `""` behaves like `a*`: it matches empty everywhere.
10. **Caller option letters at the start of the needle are honored** and stay at the
    start; the module merges its object-mode request without moving them:
    - `Count("aAa", "i)a")` is 3 (case-insensitive)
    - `Count("one`r`ntwo", "m)^(\w+)$")` is 2 (multiline: `^`/`$` match per line)
    - `Count("one`ntwo", "m)^(\w+)$")` is **0**: in multiline mode AutoHotkey's default
      line break is CRLF (`` `r`n ``); a bare `` `n `` is not a line break unless the
      caller also writes the `` `n `` option (`` "m`n)" ``). (verified in real AutoHotkey v1.1 in Windows Sandbox, 2026-09-26)
11. **Quotes in needles are doubled in source** (rule: AHK string literals, not
    regex). `MatchFirst("say ""hi"" now", """(.*?)""")` returns a capture array whose
    `[1]` is `"hi"` INCLUDING the quote marks and whose `[2]` is `hi` without them.
12. **Group numbers follow opening parentheses, left to right, nesting included.**
    `MatchFirst("Jason James", "((\w+) (\w+))")` is
    `["Jason James", "Jason James", "Jason", "James"]` - the outer group is group 1
    (whole outer text), then the inner groups in order.
13. The functions are **pure**: they never modify the caller's variables (no `ByRef`,
    nothing written to a global), and the same inputs always give the same outputs.

## Worked examples

| call | returns |
|---|---|
| `MatchAll("a1 b2", "([a-z])(\d)")` | `[["a1","a","1"], ["b2","b","2"]]` |
| `MatchAll("a1 b2", "\d")` | `[["1"], ["2"]]` |
| `MatchAll("xyz", "\d+")` | `[]` (object, `Length()` 0) |
| `MatchFirst("Price: $99.50", "\$(\d+)\.(\d+)")` | `["$99.50","99","50"]` |
| `MatchFirst("ab", "(a)(c)?(b)")` | `["ab","a","","b"]` |
| `MatchFirst("xyz", "\d+")` | `""` |
| `Count("a1 b2 c3", "\d")` | `3` |
| `Count("xyz", "\d")` | `0` |
| `Count("aaa", "aa")` | `1` |
| `Count("bc", "a*")` | `3` |
| `Count("aAa", "i)a")` | `3` |

## Edge cases, stated outright

- **No match:** `MatchAll` returns an empty array object (rule 3), `MatchFirst`
  returns `""` (rule 4), `Count` returns 0 (rule 5). None of them errors.
- **Empty text** is legal for all three (rules 3, 4, 5, 8).
- **Empty or zero-length needles** match empty at every position including one past
  the last character, and the scan advances one character per zero-length match:
  `a*` on `"bc"` is 3 matches, on `"banana"` 7, on `""` 1 (rule 8).
- **Unmatched optional groups** are `""` at their numbered slot, and the array length
  still counts them (rule 6).
- **`RegExMatch` returns 0 on no match**, not -1; a `-1` test hides every failure.
- **Caller options** such as `i)` and `m)` stay at the start of the needle and in
  effect (rule 10); the caller never writes `O)`.
- **Quotes inside a pattern** are doubled `""` in source, never backslash-escaped
  (rule 11).
- The file contains only ASCII; no BOM tricks are needed (there is non-ASCII nowhere
  in this contract's examples).

## A careless implementation cannot pass

The following look plausible and are all wrong, with the rule that convicts them:
testing `found == -1` instead of `found = 0` (rules 3-5 - every "no match" case
errors or returns garbage); a global loop that advances by exactly the match length
(rule 8 - `a*` loops forever); reading `match1`, `match2` pseudo-variables instead of
the `O)` object (rules 1-2 - cannot be collected without the banned `%` idiom);
putting the `O)` or the caller's `i)` mid-needle instead of at the very start
(rule 10 - the pattern's meaning changes); a capture array that skips unmatched
groups or renumbers them (rule 6 - the slot must hold `""`); 0-based arrays
(rules 1-2 - `[1]` is the whole match); `MatchFirst` returning an empty array
instead of `""` on no match (rule 4); advancing one character after a NON-empty
match (rule 7 - `Count("aaa", "aa")` wrongly becomes 2).
