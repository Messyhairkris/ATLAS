# Contract: shapes_file.rs - selections as text

Module `src/shapes_file.rs` of the crate `photo_tools`. The editor saves a selection
(and the eraser strokes) as a small text file, one shape per line, and the command line
reads it back with `--select file.txt`. Text in, values out: no file I/O here.

## API (exact)

```rust
//! Selections as text, one shape per line.

use crate::options::Error;
use crate::select::{Op, Shape};

/// A saved selection: the selection operations in order, and the eraser strokes.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Selection {
    pub ops: Vec<(Op, Shape)>,
    pub erased: Vec<Shape>,
}

/// Parse the text. Blank lines and everything after `#` are ignored.
pub fn parse(text: &str) -> Result<Selection, Error>

/// The text form: a header comment, the operations in order, then the eraser strokes.
pub fn write(sel: &Selection) -> String
```

Imports allowed: exactly the `use` lines above, plus std. `Shape` and `Op` are shown in
`select.rs` below the contract: `Shape::Polygon(Vec<[f32; 2]>)`,
`Shape::Stroke { points: Vec<[f32; 2]>, radius: f32 }`, `Op::{Replace, Add, Subtract}`.

## The format

One shape per line:

```
<action> polygon <x>,<y> <x>,<y> <x>,<y> ...
<action> stroke <radius> <x>,<y> ...
```

`<action>` is `replace`, `add` or `subtract` (a selection operation, `Op::Replace`,
`Op::Add`, `Op::Subtract`) or `erase` (an eraser stroke). Tokens are separated by any
whitespace.

## Rules for `parse` (in order, per line)

Every error is `Err(Error::InvalidOption { name: "selection", reason })` where `reason`
starts with `line N: ` (`N` counts from 1, blank and comment lines included), then the
text in the table below. The FIRST error stops the parse.

1. Split the text on `'\n'`. In each line, drop everything from the first `#` on, then
   split the rest on whitespace (`split_whitespace`, which also drops a trailing `\r`).
   No tokens: skip the line.
2. Token 1 is the action; any other word is an error.
3. Token 2 is the shape kind: `polygon` or `stroke`; anything else (or nothing) is an
   error. `erase` with `polygon` is an error.
4. POLYGON: every token after `polygon` is a point. Fewer than 3 points is an error.
5. STROKE: token 3 is the radius: it must parse as `f32` (`str::parse::<f32>`) and be
   finite and `> 0`, else an error (an absent token is the empty string `""`). Every token
   after it is a point; no points is an error.
6. A POINT is `x,y`: split at the FIRST comma; both halves must parse as `f32` and be
   finite. No comma, a half that does not parse, or a non-finite value is an error.
   Points are checked left to right.
7. A good line adds `(op, shape)` to `ops`, or the stroke to `erased` for `erase`.

| problem | reason after `line N: ` |
|---|---|
| unknown action `X` | `unknown action "X" (use replace, add, subtract or erase)` |
| unknown or missing shape `X` | `unknown shape "X" (use polygon or stroke)` (missing: `""`) |
| `erase ... polygon` | `erase takes a stroke` |
| bad radius token `X` | `bad radius "X"` |
| bad point token `X` | `bad point "X" (write x,y)` |
| polygon with under 3 points | `a polygon needs at least 3 points` |
| stroke with no points | `a stroke needs at least 1 point` |

## Rules for `write`

1. Start with the line `# photo_tools selection`.
2. One line per operation, in order: the action word, a space, then the shape; then one
   line per eraser stroke: `erase `, then the shape.
3. A shape is `polygon` followed by ` x,y` for each point, or `stroke`, a space, the
   radius, then ` x,y` for each point.
4. Numbers use `f32`'s `Display` (`format!("{}", v)`): `10.0` -> `10`, `2.5` -> `2.5`,
   `0.1` -> `0.1`. That form parses back to the same `f32`, so `parse(&write(&s))` gives
   back `s`.
5. Every line ends with `\n`, including the last.

## Worked examples

| text | result |
|---|---|
| `"replace polygon 1,1 3,1 3,3"` | `ops: [(Replace, Polygon([[1,1],[3,1],[3,3]]))]`, `erased: []` |
| `"add stroke 4 10,10 20,10\n  # note\n\nerase stroke 2.5 5,5"` | `ops: [(Add, Stroke { points: [[10,10],[20,10]], radius: 4 })]`, `erased: [Stroke { points: [[5,5]], radius: 2.5 }]` |
| `"subtract polygon 0,0 4,0 4,4 # tail comment"` | `ops: [(Subtract, Polygon([[0,0],[4,0],[4,4]]))]` |
| `"replace polygon 1,1\t3,1  3,3\r\n"` | one polygon (tabs, double spaces and `\r` are whitespace) |
| `""` or `"# only a comment"` | empty selection |
| `"\nmove polygon 1,1 2,2 3,3"` | `line 2: unknown action "move" (use replace, add, subtract or erase)` |
| `"add"` | `line 1: unknown shape "" (use polygon or stroke)` |
| `"add circle 1,1"` | `line 1: unknown shape "circle" (use polygon or stroke)` |
| `"erase polygon 1,1 2,2 3,3"` | `line 1: erase takes a stroke` |
| `"add stroke 0 1,1"` | `line 1: bad radius "0"` |
| `"add stroke"` | `line 1: bad radius ""` |
| `"add stroke 3"` | `line 1: a stroke needs at least 1 point` |
| `"add polygon 1,1 2,2"` | `line 1: a polygon needs at least 3 points` |
| `"add polygon 1,1 2;2 3,3"` | `line 1: bad point "2;2" (write x,y)` |
| `"add polygon 1,1 2,inf 3,3"` | `line 1: bad point "2,inf" (write x,y)` |
| `"add polygon 1,1,1 2,2 3,3"` | `line 1: bad point "1,1,1" (write x,y)` (the second half `"1,1"` does not parse) |

`write` of `ops: [(Replace, Polygon([[1,1],[3,1],[3,3]])), (Subtract, Stroke { points: [[2,2]], radius: 1.5 })]`,
`erased: [Stroke { points: [[0.25,7],[8,9]], radius: 3 }]`:

```
# photo_tools selection
replace polygon 1,1 3,1 3,3
subtract stroke 1.5 2,2
erase stroke 3 0.25,7 8,9
```
