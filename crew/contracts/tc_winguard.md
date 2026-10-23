# Contract: winguard.rs - the Windows command guard

Module `src/winguard.rs` of the crate `the_crew`. Agents on this Windows 10 machine often
type a Linux command into PowerShell. Before a PowerShell command runs, `check` decides:
**Allow** it, **Rewrite** it to the PowerShell form (when the translation is certain), or
**Block** it with a note naming what to use instead. Pure functions on strings: no I/O.

## API (exact)

```rust
//! Windows command guard: checks a PowerShell command before it runs.

/// What the guard decided.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    /// Run the command as given.
    Allow,
    /// Run `Verdict::command` instead: a fixed-up copy of the input.
    Rewrite,
    /// Do not run it; `Verdict::notes` says why and what to use instead.
    Block,
}

/// The guard's answer for one command.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Verdict {
    /// Allow, Rewrite or Block.
    pub action: Action,
    /// The rewritten command for Rewrite; otherwise the input, unchanged.
    pub command: String,
    /// One line per finding, in the order found; empty for Allow.
    pub notes: Vec<String>,
}

/// The PowerShell way to do what a Unix-only command does, or None.
pub fn suggestion(head: &str) -> Option<&'static str>

/// Cut a command into pieces: segment, separator, segment, ... (always an odd count).
pub fn split(command: &str) -> Vec<String>

/// Replace the first `k` words of `segment`, keeping what surrounds them.
pub fn replace_words(segment: &str, k: usize, with: &str) -> String

/// The guard's verdict on one PowerShell command.
pub fn check(command: &str) -> Verdict
```

Imports allowed: none needed (std prelude only; `std::mem::take` is allowed if you want it).

## Words and heads

- A **word** is a maximal run of non-whitespace characters, exactly what
  `str::split_whitespace` yields. Quotes are NOT considered when cutting words.
- The **head** of a segment is its first word lowercased with `to_ascii_lowercase()`.
  A segment with no words has no head and never produces a note.

## Rule S - `suggestion(head)`

Exact lookup in this table (keys are lowercase; anything else, including `"Grep"`, gives
`None`). Copy every string character for character:

| head | suggestion |
|---|---|
| head | `Select-Object -First N (or Get-Content file -TotalCount N)` |
| tail | `Select-Object -Last N (or Get-Content file -Tail N)` |
| grep | `Select-String -Pattern 'text'` |
| which | `(Get-Command name).Source` |
| touch | `New-Item -ItemType File (only if the file is missing)` |
| wc | `Measure-Object -Line` |
| sed | `the -replace operator` |
| awk | `ForEach-Object with -split` |
| cut | `the -split operator` |
| tr | `the -replace operator` |
| xargs | `ForEach-Object` |
| export | `$env:NAME = 'value'` |
| unset | `Remove-Item Env:NAME` |
| env | `Get-ChildItem Env:` |
| source | `. .\script.ps1 (dot-sourcing)` (in Rust source: `". .\\script.ps1 (dot-sourcing)"`) |
| uname | `[Environment]::OSVersion` |
| chmod | `icacls` |
| chown | `icacls` |
| ln | `New-Item -ItemType SymbolicLink` |
| du | `Get-ChildItem -Recurse \| Measure-Object -Property Length -Sum` (one `\|` is a plain pipe character) |
| df | `Get-PSDrive -PSProvider FileSystem` |
| less | `Get-Content file \| Out-Host -Paging` |
| stat | `Get-Item path \| Format-List *` |
| wget | `Invoke-WebRequest (or curl.exe)` |

(The `\|` above is only Markdown table escaping: each is a single `|` character.)

## Rules for `split(command)` - apply in order, scanning characters left to right

Keep a state: OUTSIDE (start), SINGLE, DOUBLE, HERE-SINGLE, HERE-DOUBLE.

In OUTSIDE, look at the current character `c` (and the next one):
1. `` ` `` (backtick): copy it AND the next character (if there is one) into the
   current segment. Neither is ever a separator.
2. `@` followed by `'` -> copy both, state HERE-SINGLE. `@` followed by `"` -> copy both,
   state HERE-DOUBLE.
3. `'` -> copy, state SINGLE. `"` -> copy, state DOUBLE.
3b. **Nesting** (added 2026-10-23): keep a counter DEPTH, starting at 0. `{` or `(` ->
   copy it and add 1. `}` or `)` -> copy it and subtract 1, but never below 0. While
   DEPTH is above 0, rules 4 and 5 do not apply: every other character is copied. (So
   `@{n='f';e={$_.Name}}`, `$(a; b)` and `if ($x) { a; b }` are one segment each. A
   command inside braces is therefore not checked: a missed Linux command there is far
   better than refusing correct PowerShell.)
4. `&&` or `||` (two identical characters) -> end the current segment; push the
   two-character separator. A single `&` is NOT a separator (it is copied).
5. `|`, `;` or a newline `\n` -> end the current segment; push that one character as
   the separator.
6. Anything else: copy it into the current segment.

Braces and parentheses inside SINGLE, DOUBLE and the here-strings do not change DEPTH, and
neither does an escaped one (`` `{ `` is copied by rule 1).

In SINGLE: copy every character; a `'` returns to OUTSIDE.
In DOUBLE: copy every character; a backtick copies itself and the next character (so
`` `" `` does not end the string); a `"` returns to OUTSIDE.
In HERE-SINGLE: copy every character; when the three characters `\n`, `'`, `@` appear in
a row, copy all three and return to OUTSIDE. HERE-DOUBLE: the same with `\n`, `"`, `@`.

A quote or here-string that never ends keeps the rest of the command in the current
segment. At the end, push the current segment (it may be empty). The result alternates
segment, separator, segment, ...; it always has an odd number of items, and joining all
items gives back exactly the input. `split("")` is `[""]`.

## Rules for `replace_words(segment, k, with)`

Write the segment as `lead` (leading whitespace) + word 1 + whitespace + ... + word k +
`rest` (everything after the last character of word k, including the whitespace right
after it). Return `lead + with + rest`. If `k` is 0 or the segment has fewer than `k`
words, return the segment unchanged.

## Rules for `check(command)` - apply in order

1. If `command` has no words at all: `Allow`, `command` unchanged, no notes.
2. **Block pass.** `pieces = split(command)`; segments are the items at even indexes
   (0, 2, 4, ...). For each segment in order, the FIRST of these that matches gives that
   segment ONE note:
   a. **Assignment prefix**: the first word contains `=`, and the part before the first
      `=` (NAME) is non-empty, starts with an ASCII letter or `_`, and has only ASCII
      letters, digits and `_`. VALUE is everything after that first `=` (may be empty).
      Note: `NAME=VALUE prefix: not PowerShell - use $env:NAME = 'VALUE'; then the command`
      with NAME and VALUE substituted.
   b. The head has a `suggestion`: note `HEAD: not a PowerShell command - use SUGGESTION`
      (HEAD is the lowercased head).
   c. The head is `find` and the second word is `.` or `..`, or starts with `-` or `~`:
      note `find: this is Windows find.exe (text search) - use Get-ChildItem -Recurse -Filter <pattern>`
   d. The head and the second word are a row of the **flag table** below, and the segment
      has MORE THAN ONE argument. An *argument* is a word after the second word that does
      not contain `>`. Note:
      `HEAD FLAG with several paths - use REPLACEMENT -Path <a>, <b>`
      (`<a>, <b>` are literal text.)
   If any segment got a note: `Block`, `command` unchanged, `notes` = all notes in segment
   order. Stop.
3. **Rewrite pass** (only when step 2 found nothing). For each segment, in order:
   a. **One word rewrite**, the first that matches:
      - the head and the second word are a row of the flag table (the second word must
        match EXACTLY, case-sensitive): replace the first 2 words with REPLACEMENT using
        `replace_words`. Note: `W1 W2 -> REPLACEMENT` with W1 and W2 the two words as
        written (not lowercased).
      - the head is `where`, the separator before this segment is not `|` (the first
        segment has no separator before it, so it counts as not piped), and there is a
        second word that does not start with `{` or `-`: replace the first word with
        `where.exe`. Note: `W1 -> where.exe` (W1 as written).
   b. **Redirections**, applied to the segment text after 3a, in THIS order, each one
      replacing every occurrence (inside quotes too) and adding ONE note `FROM -> TO` for
      the segment if it occurred at least once:
      1. `2>/dev/null` -> `2>$null`
      2. `&>/dev/null` -> `*>$null`
      3. `> /dev/null` -> `> $null`  (with the space)
      4. `>/dev/null` -> `>$null`
   Notes go in segment order; inside one segment, the word-rewrite note first, then the
   redirect notes in the order above.
4. If step 3 made any note: `Rewrite`, `command` = all pieces joined in order with the
   rewritten segments (separators unchanged), `notes` as collected. Otherwise `Allow`,
   `command` unchanged, no notes.

### Flag table

| head | second word (exact) | REPLACEMENT |
|---|---|---|
| ls | `-la`, `-al`, `-a` | `Get-ChildItem -Force` |
| ls | `-l` | `Get-ChildItem` |
| rm | `-rf`, `-fr` | `Remove-Item -Recurse -Force` |
| rm | `-r` | `Remove-Item -Recurse` |
| mkdir | `-p` | `New-Item -ItemType Directory -Force` |

## Worked examples

`split`:

| call | result |
|---|---|
| `split("a \| b")` | `["a ", "\|", " b"]` |
| `split("a \|\| b && c")` | `["a ", "\|\|", " b ", "&&", " c"]` |
| `split("a;")` | `["a", ";", ""]` |
| `split("")` | `[""]` |
| `split("x 'a\|b' \"c;d\" e")` | `["x 'a\|b' \"c;d\" e"]` (quoted separators do not count) |
| ``split("a`\|b")`` | ``["a`\|b"]`` (backtick escapes) |
| `split("one\ntwo")` | `["one", "\n", "two"]` |
| ``split("say \"a`\"\|b\" \| c")`` | ``["say \"a`\"\|b\" ", "\|", " c"]`` |
| `split("'open \| x")` | `["'open \| x"]` (unterminated quote) |
| `split("Select-Object @{n='f';e={$_.Name}} \| Sort-Object")` | `["Select-Object @{n='f';e={$_.Name}} ", "\|", " Sort-Object"]` (rule 3b) |
| `split("$(a; b); c")` | `["$(a; b)", ";", " c"]` |
| `split("a } ; b")` | `["a } ", ";", " b"]` (DEPTH never goes below 0) |
| `split("'{' ; b")` | `["'{' ", ";", " b"]` (a quoted brace does not count) |

`replace_words`:

| call | result |
|---|---|
| `replace_words("  rm -rf build", 2, "Remove-Item -Recurse -Force")` | `"  Remove-Item -Recurse -Force build"` |
| `replace_words(" ls -la ", 2, "Get-ChildItem -Force")` | `" Get-ChildItem -Force "` |
| `replace_words("where  python", 1, "where.exe")` | `"where.exe  python"` |
| `replace_words("ls", 2, "x")` | `"ls"` (fewer than k words) |

`check` (A = Allow, R = Rewrite, B = Block; "same" = the input unchanged):

| command | action | command out | notes |
|---|---|---|---|
| `Get-ChildItem -Force` | A | same | none |
| `"   "` | A | same | none |
| `git log --oneline \| head -5` | B | same | `head: not a PowerShell command - use Select-Object -First N (or Get-Content file -TotalCount N)` |
| `grep -r TODO src; which python` | B | same | the grep note, then the which note |
| `FOO=1 python run.py` | B | same | `FOO=1 prefix: not PowerShell - use $env:FOO = '1'; then the command` |
| `find . -name '*.rs'` | B | same | the find note |
| `find /i "error" log.txt` | A | same | none (`/i` is find.exe's own switch) |
| `rm -rf build dist` | B | same | `rm -rf with several paths - use Remove-Item -Recurse -Force -Path <a>, <b>` |
| `ls -la \| grep x` | B | same | only the grep note (a block wins over every rewrite) |
| `ls -la` | R | `Get-ChildItem -Force` | `ls -la -> Get-ChildItem -Force` |
| `rm -rf build 2>/dev/null` | R | `Remove-Item -Recurse -Force build 2>$null` | `rm -rf -> Remove-Item -Recurse -Force`, `2>/dev/null -> 2>$null` |
| `mkdir -p out\logs` | R | `New-Item -ItemType Directory -Force out\logs` | `mkdir -p -> New-Item -ItemType Directory -Force` |
| `cd crew && ls -l` | R | `cd crew && Get-ChildItem` | `ls -l -> Get-ChildItem` |
| `where python` | R | `where.exe python` | `where -> where.exe` |
| `Get-Process \| where { $_.CPU -gt 1 }` | A | same | none (piped, and `{`) |
| `echo hi > /dev/null` | R | `echo hi > $null` | `> /dev/null -> > $null` |
| `LS -la` | R | `Get-ChildItem -Force` | `LS -la -> Get-ChildItem -Force` |
| `ls -la; rm -r tmp` | R | `Get-ChildItem -Force; Remove-Item -Recurse tmp` | `ls -la -> Get-ChildItem -Force`, `rm -r -> Remove-Item -Recurse` |
| `cat x &>/dev/null` | R | `cat x *>$null` | `&>/dev/null -> *>$null` |
| `python -c "import a; print(1)"` | A | same | none (the `;` is quoted) |
| a here-string: `git commit -m @'` newline `export the data` newline `'@` | A | same | none (inside a here-string nothing is a separator) |
| `Get-ChildItem \| Select-Object @{n='file';e={$_.FullName}}` | A | same | none (rule 3b: the `;` is inside braces) |
| `foreach ($n in 'a','b') { $n }; ls -la` | R | `foreach ($n in 'a','b') { $n }; Get-ChildItem -Force` | `ls -la -> Get-ChildItem -Force` |

(In the tables, `\|` is a single `|` character.)

Points members got wrong in similar tasks: walk the rules in the stated order; keep every
separator and every space exactly as it was; compare flags case-sensitively but heads
lowercased; count arguments only after the second word and skip words containing `>`.
