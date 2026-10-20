# Contract: select.rs - selections and the pixel mask they make

Module `src/select.rs` of the crate `photo_tools`. The user isolates areas of interest
with a lasso, a polyline or a round "blob" brush; Shift adds to the selection, Ctrl
removes from it. Unselected areas are not rendered. This module turns those shapes into
a mask: one bool per pixel. It is pure geometry - no UI, no I/O.

## API (exact)

```rust
//! Selections: lasso and polyline polygons, round brush strokes, and the pixel mask
//! they make.

use image::GrayImage;

/// One selection shape, in image pixel coordinates (pixel (x, y) covers x..x+1, y..y+1).
#[derive(Debug, Clone, PartialEq)]
pub enum Shape {
    /// A closed polygon (lasso or polyline): the last point joins the first.
    Polygon(Vec<[f32; 2]>),
    /// A round brush of `radius` dragged through `points` in order.
    Stroke { points: Vec<[f32; 2]>, radius: f32 },
}

/// How a shape changes the selection: no key, Shift, Ctrl.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Op {
    Replace,
    Add,
    Subtract,
}

/// One bool per pixel, row-major; true = selected.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Mask {
    width: u32,
    height: u32,
    bits: Vec<bool>,
}

impl Mask {
    pub fn new(width: u32, height: u32, value: bool) -> Mask
    pub fn from_bits(width: u32, height: u32, bits: Vec<bool>) -> Option<Mask>
    pub fn from_luma(img: &GrayImage) -> Mask
    pub fn width(&self) -> u32
    pub fn height(&self) -> u32
    pub fn bits(&self) -> &[bool]
    pub fn get(&self, x: u32, y: u32) -> bool
    pub fn count(&self) -> usize
    pub fn apply(&mut self, op: Op, shape: &Shape)
}

pub fn rasterize(shape: &Shape, width: u32, height: u32) -> Vec<bool>
pub fn build(width: u32, height: u32, ops: &[(Op, Shape)]) -> Option<Mask>
```

The three `Mask` fields stay private (no `pub`). Imports allowed: exactly the `use` line
above, plus std.

## Mask methods

- `new`: every one of the `width * height` bits set to `value`.
- `from_bits`: `None` when `bits.len() != width * height`, else the mask.
- `from_luma`: a mask image of the same size; a pixel is selected when its gray value is
  `>= 128`.
- `width`, `height`, `bits`: the fields. `count`: the number of `true` bits.
- `get(x, y)`: the bit at `bits[y * width + x]`; `false` when `x >= width` or
  `y >= height`. Compute the index in `usize` (a big image overflows `u32`).
- `apply(op, shape)`: `r = rasterize(shape, width, height)`, then for every pixel:
  `Replace` -> `r`; `Add` -> `bit || r`; `Subtract` -> `bit && !r`.

## Rules for `rasterize` (in order)

The result is `width * height` bools, row-major. A pixel `(x, y)` is judged at its
CENTRE `(px, py) = (x + 0.5, y + 0.5)`. Do all arithmetic in `f64` (convert each `f32`
coordinate with `as f64`).

1. INVALID SHAPES select nothing (all false): a polygon with fewer than 3 points; a stroke
   with no points; any point with a non-finite coordinate (NaN or infinite); a stroke
   whose radius is not finite or is `<= 0`. Points outside the image are fine.
2. POLYGON - nonzero winding. The edges are `p[i] -> p[i + 1]` for every `i`, plus the
   closing edge `p[n - 1] -> p[0]`. For a pixel centre, each edge `a -> b` contributes:
   - `+1` if `a.y <= py && b.y > py`, and `px < xi`;
   - `-1` if `b.y <= py && a.y > py`, and `px < xi`;
   - `0` otherwise (horizontal edges never count);
   where `xi = a.x + (py - a.y) * (b.x - a.x) / (b.y - a.y)`, computed exactly in that
   order. The pixel is selected when the sum is NOT zero. (So a centre exactly on a left or
   top edge is inside, on a right or bottom edge outside, and a region circled twice still
   counts.)
3. POLYGON SPEED: the hidden tests rasterize a 3000 x 2000 image with a 5000-point lasso
   and fail if it takes over 10 seconds in a debug build. Testing every edge against every
   pixel is far too slow. Do it per row: for row `y`, collect `(xi, +1/-1)` for the edges
   that cross `py` (the two conditions above), sort them by `xi`, then sweep the row left
   to right: a pixel's sum is the total of the crossings whose `xi > px`. This gives
   exactly rule 2's result.
4. STROKE - a round brush. The segments are `points[i] -> points[i + 1]`; a single point is
   one segment from the point to itself. A pixel is selected when, for ANY segment `a -> b`,
   the squared distance from the centre to the segment is `<= radius * radius`:
   - `d = b - a`, `len2 = d.x * d.x + d.y * d.y`;
   - `t = 0` if `len2 == 0`, else `t = ((px - a.x) * d.x + (py - a.y) * d.y) / len2`
     clamped to `0.0..=1.0`;
   - `q = (a.x + t * d.x - px, a.y + t * d.y - py)`; squared distance `q.x * q.x + q.y * q.y`.
   Only test pixels inside each segment's bounding box grown by `radius + 1` (clamped to
   the image) - the result is the same, and a long stroke on a big image stays fast.

## Rules for `build`

1. No operations: `None` (no selection means the whole image is used).
2. Otherwise start from `Mask::new(width, height, value)` where `value` is `true` when
   the FIRST operation is `Subtract` (Ctrl with no selection removes from the whole
   image), else `false`; then `apply` every operation in order and return `Some(mask)`.

## Worked examples

`#` = selected, `.` = not; rows top to bottom, separated by `/`.

| shape | image | result |
|---|---|---|
| `Polygon([[1,1],[3,1],[3,3],[1,3]])` | 4 x 4 | `.... / .##. / .##. / ....` |
| `Polygon([[0.5,0.5],[2.5,0.5],[2.5,2.5],[0.5,2.5]])` | 3 x 3 | `##. / ##. / ...` (centres on the left/top edges are in, right/bottom out) |
| `Polygon([[0,0],[4,0],[4,4],[0,4],[0,0],[4,0],[4,4],[0,4]])` (circled twice) | 4 x 4 | all 16 selected (winding 2 is not zero) |
| `Polygon([[0,0],[4,0]])` (2 points) | 4 x 1 | none (rule 1) |
| `Polygon([[0,0],[9,0],[f32::NAN,9]])` | 4 x 4 | none (rule 1) |
| `Stroke { points: [[2,2]], radius: 1.0 }` | 4 x 4 | `.... / .##. / .##. / ....` |
| `Stroke { points: [[2,2]], radius: 1.6 }` | 4 x 4 | `.##. / #### / #### / .##.` |
| `Stroke { points: [[0.5,0.5]], radius: 1.0 }` | 3 x 3 | `##. / #.. / ...` (distance exactly 1 counts) |
| `Stroke { points: [[0,0.5],[4,0.5]], radius: 0.5 }` | 4 x 2 | `#### / ....` |
| `Stroke { points: [[1,1]], radius: 0.0 }` | 3 x 3 | none (rule 1) |

With `A = Polygon([[0,0],[2,0],[2,1],[0,1]])` (pixels 0 and 1 of a 4 x 1 image),
`B = Polygon([[3,0],[4,0],[4,1],[3,1]])` (pixel 3) and
`C = Polygon([[1,0],[2,0],[2,1],[1,1]])` (pixel 1):

| ops | `build(4, 1, ops)` |
|---|---|
| `[]` | `None` |
| `[(Replace, A)]` | `##..` |
| `[(Add, A)]` | `##..` (starts empty) |
| `[(Subtract, A)]` | `..##` (starts full) |
| `[(Replace, A), (Add, B)]` | `##.#` |
| `[(Replace, A), (Subtract, C)]` | `#...` |
| `[(Add, B), (Replace, C)]` | `.#..` (Replace drops what came before) |

`Mask::from_luma` of the 3 x 1 gray image `[127, 128, 255]` -> `.##`.
`Mask::new(2, 2, true).get(2, 0)` -> `false` (outside).
`Mask::from_bits(2, 2, vec![true; 3])` -> `None`.
