# Contract: junction.rs - where region borders meet

Module `src/junction.rs` of the crate `photo_tools`. Part 1 of 3 of the outline tracer
(junction.rs, edges.rs, contour.rs). One small function: is a grid vertex a point where
three or more regions meet?

## API (exact)

```rust
//! Where region borders meet.

/// True where three or more values meet (outside counts as one value), or at a
/// checkerboard saddle of two labels with all four cells inside the image.
pub fn is_junction(labels: &[u8], width: usize, height: usize, x: usize, y: usize) -> bool
```

Imports allowed: none needed (std prelude only).

## Geometry

`labels` is row-major: pixel `(px, py)` has label `labels[py * width + px]`. Pixel
`(px, py)` is the unit square with corners `(px, py)` and `(px+1, py+1)`; y grows
DOWNWARD. Vertices are the grid points `(x, y)` with `0 <= x <= width`,
`0 <= y <= height`. Around vertex `(x, y)` lie four cells:

```
 NW = (x-1, y-1) | NE = (x, y-1)
 ----------------+----------------
 SW = (x-1, y)   | SE = (x, y)
```

A cell outside the image has the value OUTSIDE, which is different from every label
(use an `i32` like -1, or `Option<u8>` with `None`). Mind `x - 1` when `x == 0`: do the
arithmetic in `i64` (or check first) so nothing underflows.

## Rules

1. Collect the four values NW, NE, SW, SE.
2. If they hold 3 or more DISTINCT values (OUTSIDE counts as one value) -> `true`.
3. Else, if all four cells are inside the image and `NW == SE`, `NE == SW` and
   `NW != NE` (a checkerboard of two labels) -> `true`.
4. Otherwise -> `false`.

## Worked examples

| labels (rows /) | w x h | vertex | cells NW NE SW SE | result | rule |
|---|---|---|---|---|---|
| `5` | 1x1 | (0,0), (1,0), (0,1), (1,1) | e.g. (1,1): 5 O O O | false | 4 (two values) |
| `0 1` | 2x1 | (1,0) | O O 0 1 | true | 2 |
| `0 1` | 2x1 | (1,1) | 0 1 O O | true | 2 |
| `0 1` | 2x1 | (0,0) | O O O 0 | false | 4 |
| `0 1` | 2x1 | (2,1) | 1 O O O | false | 4 |
| `0 0 / 1 2` | 2x2 | (1,1) | 0 0 1 2 | true | 2 |
| `0 0 / 1 2` | 2x2 | (1,0) | O O 0 0 | false | 4 |
| `0 1 / 2 3` | 2x2 | (1,1) | 0 1 2 3 | true | 2 |
| `0 1 / 1 0` | 2x2 | (1,1) | 0 1 1 0 | true | 3 (saddle) |
| `7 3 / 3 7` | 2x2 | (1,1) | 7 3 3 7 | true | 3 |
| `0 1 / 0 1` | 2x2 | (1,1) | 0 1 0 1 | false | 4 (NW != SE) |
| `1 1 / 1 0` | 2x2 | (1,1) | 1 1 1 0 | false | 4 |
| `4 4 / 4 4` | 2x2 | (1,1) | 4 4 4 4 | false | 4 |
| `3 3` | 2x1 | (1,1) | 3 3 O O | false | 4 (two values) |
| `0 0 1 / 0 0 1` | 3x2 | (2,0) | O O 0 1 | true | 2 |
| `0 0 1 / 0 0 1` | 3x2 | (2,1) | 0 1 0 1 | false | 4 |
| `0 0 1 / 0 0 1` | 3x2 | (2,2) | 0 1 O O | true | 2 |

(O = OUTSIDE.)
