# Contract: diffview.rs - unified diff lines for display

Module `src/diffview.rs` of the crate `the_crew`. The Crew's control room shows commit
requests (unified diffs from `git diff`) to Kris. `classify` labels every line - file
header, hunk header, added, removed, context - and numbers each line in the old and new
file, so the window can colour it and show line numbers. Pure functions on strings: no I/O.

## API (exact)

```rust
//! Unified diff lines, classified for display, with old and new line numbers.

/// What one line of a diff is.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    /// A file's header: `diff --git`, `index`, `---`, `+++`, mode, rename, copy, `Binary files`.
    FileHeader,
    /// A hunk header: `@@ -a,b +c,d @@`.
    Hunk,
    /// A `+` line inside a hunk.
    Added,
    /// A `-` line inside a hunk.
    Removed,
    /// A ` ` (or empty) line inside a hunk.
    Context,
    /// `\ No newline at end of file`.
    NoNewline,
    /// Anything else: commit message text, stats, a line that broke a hunk.
    Other,
}

/// One classified line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Line {
    /// What the line is.
    pub kind: Kind,
    /// Its number in the old file (Removed and Context only).
    pub old: Option<u32>,
    /// Its number in the new file (Added and Context only).
    pub new: Option<u32>,
    /// The line exactly as given, without its line ending.
    pub text: String,
}

/// `(old_start, old_count, new_start, new_count)` of a hunk header, or None.
pub fn parse_hunk_header(line: &str) -> Option<(u32, u32, u32, u32)>

/// Every line of `diff`, classified, in order.
pub fn classify(diff: &str) -> Vec<Line>

/// `(added, removed)`: how many Added and Removed lines there are.
pub fn stats(lines: &[Line]) -> (usize, usize)

/// The path of each file the diff changes, in order, from its `+++` header line.
pub fn files(lines: &[Line]) -> Vec<String>
```

Imports allowed: none needed (std prelude only).

## Rule H - `parse_hunk_header(line)`

The whole grammar, read left to right; anything that does not fit gives `None`:

1. The line starts with exactly `@@ -`.
2. A RANGE: one or more ASCII digits (the start), then optionally `,` and one or more
   ASCII digits (the count). No count means count = 1. A `,` with no digits after it is
   `None`. Each number must parse as `u32` (`"99999999999"` overflows: `None`).
3. Exactly ` +` (space, plus).
4. A second RANGE, the same way.
5. Exactly ` @@`. Anything after it (often a function name) is ignored.

| line | result |
|---|---|
| `@@ -1,3 +1,4 @@` | `Some((1, 3, 1, 4))` |
| `@@ -5 +5,2 @@ fn main() {` | `Some((5, 1, 5, 2))` |
| `@@ -0,0 +1,12 @@` | `Some((0, 0, 1, 12))` |
| `@@ -1,3 +1,4@@` | `None` (no space before `@@`) |
| `@@@ -1 +1 -1 @@@` | `None` (combined diff) |
| `@@ -1, +1 @@` | `None` |
| `@@ -1 +1` | `None` |
| ` @@ -1 +1 @@` | `None` (leading space) |

## Rule C - `classify(diff)`

Lines are exactly what `diff.lines()` yields (so `\r\n` endings are dropped and there is
no empty last line). `text` is that line, unchanged.

Keep a STATE, which starts as OUTSIDE: one of OUTSIDE, HEADER, BODY. In BODY also keep
`old_no`, `new_no` (the next line numbers) and `old_left`, `new_left` (lines still
expected, from the hunk header's counts).

For each line, the FIRST rule that matches decides; numbers are `None` unless the rule
says otherwise:

| # | when | kind | then |
|---|---|---|---|
| 1 | the line starts with `diff --git ` | FileHeader | STATE = HEADER |
| 2 | `parse_hunk_header(line)` is `Some((os, oc, ns, nc))` (in ANY state) | Hunk | STATE = BODY; `old_no = os`, `new_no = ns`, `old_left = oc`, `new_left = nc` |
| 3 | STATE is BODY and (`old_left > 0` or `new_left > 0`) | see table B | |
| 4 | STATE is BODY and the line starts with `\` | NoNewline | |
| 5 | the line starts with `--- ` or `+++ ` | FileHeader | STATE = HEADER |
| 6 | STATE is HEADER and the line starts with one of the header prefixes below | FileHeader | |
| 7 | anything else | Other | if STATE is BODY, STATE = OUTSIDE (HEADER and OUTSIDE stay as they are) |

Table B (rule 3), by the line's first character:

| first char | kind | old | new | then |
|---|---|---|---|---|
| `+` | Added | None | `Some(new_no)` | `new_no += 1`, `new_left -= 1` |
| `-` | Removed | `Some(old_no)` | None | `old_no += 1`, `old_left -= 1` |
| ` ` (space), or the line is empty | Context | `Some(old_no)` | `Some(new_no)` | both numbers `+= 1`, both lefts `-= 1` |
| `\` | NoNewline | None | None | nothing changes |
| anything else | Other | None | None | STATE = OUTSIDE |

Every `+= 1` is `saturating_add(1)` and every `-= 1` is `saturating_sub(1)`: a hunk
header near `u32::MAX` must not panic.

The header prefixes for rule 6, exact and case-sensitive (note the trailing spaces):
`index `, `new file mode `, `deleted file mode `, `old mode `, `new mode `,
`similarity index `, `dissimilarity index `, `rename from `, `rename to `, `copy from `,
`copy to `, `Binary files `.

Consequences, so nobody has to guess:
- Inside a hunk with lines left, `--- x` is a Removed line and `+++ x` an Added line
  (rule 3 comes before rule 5).
- Once both counts reach 0, a further `+c` line is Other, and so is everything after it
  until a rule 1, 2 or 5 line.
- A plain `diff -u` (no `diff --git` line) starts at its `--- ` line (rule 5).
- `index 1234` before any `diff --git` / `---` / `+++` line is Other.

## Worked example

```
diff --git a/src/a.rs b/src/a.rs      FileHeader            (rule 1)
index 1111111..2222222 100644          FileHeader            (rule 6)
--- a/src/a.rs                         FileHeader            (rule 5)
+++ b/src/a.rs                         FileHeader            (rule 5)
@@ -1,3 +1,4 @@ fn main() {           Hunk                  old 1.., new 1.., left 3 and 4
 one                                   Context  old 1 new 1
-two                                   Removed  old 2
+TWO                                   Added            new 2
+three                                 Added            new 3
 four                                  Context  old 3 new 4  (now both lefts are 0)
```

## Rule S - `stats(lines)`

`(number of Added lines, number of Removed lines)`. Only those two kinds count.

## Rule F - `files(lines)`

Walk the lines in order, looking ONLY at lines whose kind is FileHeader:
- A FileHeader starting with `--- `: remember it as the last old path: the text after
  `--- `, cut at the first tab (`\t`) if any, then one leading `a/` removed if present.
- A FileHeader starting with `+++ `: take the text after `+++ `, cut at the first tab.
  - If that is exactly `/dev/null` (a deleted file): push the remembered last old path,
    or push nothing if there is none.
  - Otherwise remove one leading `b/` if present, and push it.

| headers | files |
|---|---|
| `--- a/src/a.rs`, `+++ b/src/a.rs` | `["src/a.rs"]` |
| `--- /dev/null`, `+++ b/new.txt` | `["new.txt"]` |
| `--- a/old.txt`, `+++ /dev/null` | `["old.txt"]` |
| `--- old.txt\t2026-10-23 10:00:00`, `+++ new.txt\t2026-10-23 10:05:00` | `["new.txt"]` |
| `+++ /dev/null` alone | `[]` |

Added or Removed lines that happen to start with `+++ ` / `--- ` are not headers and never
count.
