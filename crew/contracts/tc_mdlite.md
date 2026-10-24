# Contract: mdlite.rs - a small Markdown reader

Module `src/mdlite.rs` of the crate `the_crew`. The Crew's control room shows Kris the
night report, crew reports and review items, all Markdown. `parse` turns a document into
blocks (headings, paragraphs, lists, quotes, code, tables, rules) and `inline` turns a
block's text into spans (bold, italic, code, links). The window draws them. This is NOT
CommonMark: follow THESE rules exactly, even where another Markdown reader would differ.
Pure functions on strings: no I/O.

## API (exact)

```rust
//! A small Markdown reader for The Crew's report views: blocks and inline spans, no HTML.

/// A run of text inside a block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Span {
    /// Plain text.
    Text(String),
    /// `**text**` or `__text__`.
    Bold(String),
    /// `*text*` or `_text_`.
    Italic(String),
    /// `` `text` ``.
    Code(String),
    /// `[text](target)`, `[[target|text]]`, or a bare `https://` address.
    Link { text: String, target: String },
}

/// One block of a document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Block {
    /// `# ` to `###### `.
    Heading { level: u8, spans: Vec<Span> },
    /// Lines of text, joined.
    Paragraph(Vec<Span>),
    /// `- `, `* ` or `+ ` item; depth = indent / 2.
    Bullet { depth: u8, spans: Vec<Span> },
    /// `1. ` or `1) ` item; depth = indent / 2.
    Numbered { depth: u8, number: u32, spans: Vec<Span> },
    /// `> ` lines, joined.
    Quote(Vec<Span>),
    /// A fenced block, or front matter (lang "yaml").
    Code { lang: String, text: String },
    /// A pipe table: header cells, then rows padded or cut to the header's width.
    Table { header: Vec<Vec<Span>>, rows: Vec<Vec<Vec<Span>>> },
    /// `---`, `***` or `___`.
    Rule,
}

/// The spans of one block's text.
pub fn inline(text: &str) -> Vec<Span>

/// The cells of one table row, trimmed, with `\|` read as a literal `|`.
pub fn split_row(line: &str) -> Vec<String>

/// The blocks of a Markdown document, in order.
pub fn parse(markdown: &str) -> Vec<Block>
```

Imports allowed: none needed. `std::mem::take` / `std::mem::replace` are allowed.
Tip: work on `let chars: Vec<char> = text.chars().collect();` with indexes, and build
Strings with `chars[a..b].iter().collect()`; never slice a `&str` at a char index.

---------------------------------------------------------------------------------------

## Part 1 - `inline(text)`

Scan `chars` left to right with an index `i`, keeping a text buffer BUF. Output rule:
**plain characters go into BUF; before pushing any other span, push BUF as `Text` if it is
not empty, then clear it; at the end push BUF the same way.** So the output never holds
an empty `Text` or two `Text`s in a row, and `inline("")` is `[]`.

At each `i`, with `c = chars[i]`, try these in order; the first that SUCCEEDS acts. When
a rule fails, its "on failure" step says what to do; if a rule has no failure step, go on
to the next rule.

**A. Escape.** `c` is `\` and the next char exists and `is_ascii_punctuation()`: push the
next char into BUF, `i += 2`. (A `\` before a letter, space or end stays a plain `\`.)

**B. Code span.** `c` is `` ` ``. Let R = the number of backticks in a row starting at
`i`. Search from `i + R` for a run of EXACTLY R backticks (scan runs: at a backtick,
measure its run length M; if M == R that run closes; otherwise skip the whole run and
keep looking). If found at `k`: CONTENT = chars from `i + R` to `k`; if CONTENT has at
least 2 chars, starts with a space, ends with a space and has some char that is not a
space, remove one space from each end. Push `Code(CONTENT)`, `i = k + R`. Nothing inside
a code span is interpreted. On failure: push all R backticks into BUF, `i += R`.

**C. Wiki link.** `c` is `[` and the next char is `[`. Find the first `]]` at or after
`i + 2` (positions `j`, `j + 1`). CONTENT = chars `i + 2 .. j`. It fails if there is no
`]]`, or CONTENT contains `[`. If CONTENT contains `|`: TARGET = before the first `|`,
LABEL = after it; otherwise both = CONTENT. Trim both. Fails if TARGET is empty. If LABEL
is empty, LABEL = TARGET. Push `Link { text: LABEL, target: TARGET }`, `i = j + 2`.
On failure: push `[` into BUF, `i += 1` (the second `[` is looked at next, by rule D).

**D. Link.** `c` is `[`. Find the first `]` after `i`, at `j`. Fails if there is none,
if the label chars `i + 1 .. j` contain `[`, or if `chars[j + 1]` is not `(`. Find the
first `)` after `j + 1`, at `k`; fails if none. TARGET = chars `j + 2 .. k`, trimmed;
fails if empty. TEXT = the label chars, untrimmed; if TEXT is at least 2 chars and starts
AND ends with a backtick, remove those two backticks; if TEXT is then empty, TEXT =
TARGET. Push `Link { text: TEXT, target: TARGET }`, `i = k + 1`. The label is literal
(no bold or code inside it). On failure: push `[` into BUF, `i += 1`.

**E. Bold.** `c` is `*` or `_` and the next char is the same char (call it D). For `_`
only, it fails if `i > 0` and `chars[i - 1].is_alphanumeric()`. Find the first D D pair
at or after `i + 2`, at `j`; fails if none. CONTENT = chars `i + 2 .. j`; fails if
`CONTENT.trim()` is empty. For `_` only, fails if `chars[j + 2]` exists and
`is_alphanumeric()`. Push `Bold(CONTENT)` (literal: no code or italic inside it),
`i = j + 2`. On failure: push BOTH chars into BUF, `i += 2`.

**F. Italic.** `c` is `*` or `_` (a single one; doubles were handled by E). It fails if
there is no next char or the next char `is_whitespace()`; for `_` only, it also fails if
`i > 0` and `chars[i - 1].is_alphanumeric()`. Find the smallest `j >= i + 2` where
`chars[j] == c`, `chars[j - 1]` is not whitespace, and (for `_` only) `chars[j + 1]` does
not exist or is not alphanumeric. Fails if there is none. Push `Italic(chars i+1 .. j)`,
`i = j + 1`. On failure: push `c` into BUF, `i += 1`.

**G. Bare address.** `c` is `h`, AND (`i == 0` or `chars[i - 1]` is whitespace or one of
`( < " '`), AND the text from `i` starts with `https://` or `http://`. END = the first
position from `i` whose char is whitespace or one of `` < > " ' ` `` (or the end).
Then, while the char before END is one of `. , ; : ! ? )`, step END back by one. It fails
if what is left is no longer than the scheme (`https://` or `http://` alone). Push
`Link { text: URL, target: URL }` where URL = chars `i .. END`, `i = END`.

**H. Otherwise:** push `c` into BUF, `i += 1`.

### Inline worked examples

| text | spans |
|---|---|
| ``run `cargo test` **now**, *please*`` | `Text("run ")`, `Code("cargo test")`, `Text(" ")`, `Bold("now")`, `Text(", ")`, `Italic("please")` |
| ``a `b and ``c` d`` | `Text("a ")`, `Code("b and ``c")`, `Text(" d")` |
| `` `` `x` `` `` | `Code("`x`")` |
| `\*not italic\*` | `Text("*not italic*")` |
| `C:\Users\Kris` | `Text("C:\Users\Kris")` |
| `crew_status and NIGHT_REPORT.md` | `Text(...)` unchanged (rule E/F `_` needs a non-alphanumeric before it) |
| `_quiet_ and __loud__` | `Italic("quiet")`, `Text(" and ")`, `Bold("loud")` |
| `x__y__z` | `Text("x__y__z")` |
| `**a**b` | `Bold("a")`, `Text("b")` (`*` has no word-edge rule) |
| `a*b*c` | `Text("a")`, `Italic("b")`, `Text("c")` |
| `2 * 3 * 4` | `Text("2 * 3 * 4")` |
| `a *b * c*` | `Text("a ")`, `Italic("b * c")` |
| `**`x` and *y***` | `Bold("`x` and *y")`, `Text("*")` |
| `a ** b` | `Text("a ** b")` |
| `[`campaign.py`](crew/campaign.py)` | `Link { text: "campaign.py", target: "crew/campaign.py" }` |
| `[x]( C:\My Files\a.md )` | `Link { text: "x", target: "C:\My Files\a.md" }` |
| `[a] (b)` | `Text("[a] (b)")` |
| `[a [b](c)` | `Text("[a ")`, `Link { text: "b", target: "c" }` |
| `[[hoss-direction\|Hoss]]` (one `\|` = a plain pipe) | `Link { text: "Hoss", target: "hoss-direction" }` |
| `[[ ]]` | `Text("[[ ]]")` |
| `(http://localhost:8080).` | `Text("(")`, `Link` of `http://localhost:8080`, `Text(").")` |
| `xhttps://a.b` | `Text("xhttps://a.b")` |

---------------------------------------------------------------------------------------

## Part 2 - `split_row(line)`

1. Trim the line. Remove ONE leading `|` if present.
2. If what is left ends with `|` and does not end with `\|`, remove that last `|`.
3. Split on every `|` that is not preceded by `\`. In each piece, `\|` becomes `|`.
4. Trim each piece. There is always at least one cell.

| line | cells |
|---|---|
| `\| a \| b \|` | `["a", "b"]` |
| `\| a \|\| c \|` | `["a", "", "c"]` |
| `\| `a \\| b` \| c \|` (a backslash-pipe inside) | ``["`a | b`", "c"]`` |
| `\| x \\|` | `["x |"]` |
| `\|` | `[""]` |

(In this table `\|` means a plain `|` - Markdown needs the escape to show it.)

---------------------------------------------------------------------------------------

## Part 3 - `parse(markdown)`

LINES = `markdown.lines()` (so `\r\n` endings are dropped). Blocks are made line by line.
Text lines can be "open" - a Paragraph, Bullet, Numbered or Quote still collecting text.
**Closing** an open block pushes it with `inline(its text)`. JOIN(text, more): if `more`
is empty do nothing; else if text is empty, text = more; else text = text + " " + more.

**Front matter.** If the FIRST line is exactly `---` and a later line is exactly `---`,
the lines between them become `Code { lang: "yaml", text: those lines joined with "\n" }`
and parsing continues after the closing `---`. If there is no closing `---`, there is no
front matter (the first line is then a Rule).

For each line, with TRIMMED = `line.trim()`, the first rule that matches acts:

1. **Fence.** `line.trim_start()` starts with three backticks. Close the open block.
   LANG = the rest after those three backticks, trimmed. The following lines, EXACTLY as
   they are (no trimming), are the code, up to a line whose trim is 3 or more backticks and
   nothing else (that line is consumed) or the end of input. Push `Code { lang, text }`
   with the code lines joined by `"\n"` (no newline at the end; no lines gives `""`).
2. **Blank.** TRIMMED is empty: close the open block.
3. **Heading.** The line (NOT trimmed) starts with N `#` characters, 1 <= N <= 6, and
   right after them is either the end of the line or a space. Close the open block; push
   `Heading { level: N, spans: inline(rest after the #s, trimmed) }`. (`#tag`,
   `####### x` and `  # x` are not headings.)
4. **Rule.** TRIMMED is 3 or more chars and all of them are `-`, or all `*`, or all `_`.
   Close the open block; push `Rule`.
5. **Table.** TRIMMED starts with `|` AND there is a next line AND the next line is a
   separator: its trim starts with `|`, contains at least one `-`, and has only the
   chars `| - :` and space. Close the open block. HEADER = `split_row(line)`, each cell
   through `inline`. Skip the separator. Then every following line whose trim starts
   with `|` is a row: `split_row`, each cell through `inline`, then padded with empty
   cells (`vec![]`) or cut to HEADER's length. The first line that does not start with `|`
   ends the table and is handled normally by these rules. Push `Table { header, rows }`.
6. **Indent.** Measure the line's leading whitespace: each space counts 1, each tab 4.
   DEPTH = width / 2 (as u8, at most 255). REST = the line after that whitespace.
7. **Bullet.** REST starts with `- `, `* ` or `+ `. Close the open block; open a Bullet
   with DEPTH and text = REST after those 2 chars, trimmed.
8. **Numbered.** REST starts with 1 to 9 ASCII digits followed by `. ` or `) `. NUMBER =
   the digits as u32. If NUMBER is 1, or the open block is NOT a Paragraph: close the open
   block and open a Numbered with DEPTH, NUMBER, text = after the `. ` / `) `, trimmed.
   Otherwise (a Paragraph is open and NUMBER is not 1) this rule does not act: go on.
9. **Quote.** REST starts with `>`. Q = after the `>`, with one space removed if the next
   char is a space, then trimmed. If the open block is a Quote: JOIN it with Q. Otherwise
   close the open block and open a Quote with text Q.
10. **Text.** If a Paragraph, Bullet, Numbered or Quote is open: JOIN it with TRIMMED
    (lazy continuation: wrapped list lines and lazy quote lines join their block).
    Otherwise open a Paragraph with text TRIMMED.

At the end of input, close the open block.

### Parse worked examples (`\n` = newline)

| markdown | blocks |
|---|---|
| `first line\n   second line  \nthird` | `Paragraph([Text("first line second line third")])` |
| `####### seven\n#tag\n#` | `Paragraph([Text("####### seven #tag")])`, `Heading { level: 1, spans: [] }` |
| `- one\n  + nested\n\t- tab\n-not a bullet` | `Bullet{0,"one"}`, `Bullet{1,"nested"}`, `Bullet{2,"tab -not a bullet"}` |
| `- The keeper (`` `--worker` ``\n  opts in).` | `Bullet{0, [Text("The keeper ("), Code("--worker"), Text(" opts in).")]}` |
| `It happened in\n2026. Then more.\n1. a list` | `Paragraph("It happened in 2026. Then more.")`, `Numbered{0, 1, "a list"}` |
| `- item\n3. three` | `Bullet{0,"item"}`, `Numbered{0, 3, "three"}` |
| `1234567890. x` (10 digits) | not Numbered (too many digits) |
| `> Kris: approve\n>needs no words\n>\n> - still quoted\nlazy` | `Quote("Kris: approve needs no words - still quoted lazy")` |
| `text\n> quote` | `Paragraph("text")`, `Quote("quote")` |
| `***\n___\n  -----  \n--\n-*-` | `Rule`, `Rule`, `Rule`, `Paragraph("-- -*-")` |
| `---\nname: x\n---\n# T` | `Code{"yaml","name: x"}`, `Heading{1,"T"}` |
| `---\nname: x` | `Rule`, `Paragraph("name: x")` |
| `  ``` rust \nx\n  ````  \ny` | `Code{"rust","x"}`, `Paragraph("y")` |
| `\| a \|\n\| - \|\n\| b \| extra \|\n\| \|\nafter` | `Table{header [[a]], rows [[[b]], [[]]]}`, `Paragraph("after")` |
| `\| a \|\n\|   \|` | `Paragraph("\| a \| \|   \|")` (a separator needs a `-`) |

(Short forms: `Bullet{0,"one"}` means `Bullet { depth: 0, spans: vec![Span::Text("one".into())] }`.)
