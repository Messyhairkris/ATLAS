# Contract: lineart_svg.rs - line art as SVG centerline strokes

Module `src/lineart_svg.rs` of the crate `photo_tools`. Line art can be saved as SVG as
well as PNG or JPEG. Each line becomes one stroke down its middle (a centerline): thin,
easy to edit, good for plotters, laser cutters and CAD. Only lines inside the selection
are kept, and the document has no background, so everything else is transparent.

## API (exact)

```rust
//! Line art as SVG centerline strokes.

use image::DynamicImage;

use crate::lineart;
use crate::options::{Error, LineArtOptions};
use crate::select::Mask;
use crate::smooth::{simplify, Pt};
use crate::strokes::trace;
use crate::svg::fmt_num;
use crate::thin::thin;

/// How the strokes are drawn.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StrokeOptions {
    /// Simplification tolerance in pixels; 0 draws straight lines through every corner
    /// (only points in a straight run are dropped, so nothing is lost).
    pub tolerance: f64,
    /// Stroke width in pixels.
    pub width: f64,
    /// Chains with fewer distinct pixels are dropped (specks).
    pub min_pixels: usize,
}

impl Default for StrokeOptions { /* tolerance 1.0, width 1.0, min_pixels 3 */ }

impl StrokeOptions {
    pub fn validate(&self) -> Result<(), Error>
}

/// One chain as SVG path data: pixel centres, simplified by `tolerance`, then straight
/// lines (tolerance 0) or Catmull-Rom cubics; a closed chain ends with Z.
pub fn chain_path(chain: &[(u32, u32)], tolerance: f64) -> String

/// Line art (black on white), thinned and traced into stroked centerlines. Only
/// pixels inside `keep` are traced; the document has no background (transparent).
pub fn render_svg(
    img: &DynamicImage,
    opts: &LineArtOptions,
    stroke: &StrokeOptions,
    keep: Option<&Mask>,
) -> Result<String, Error>
```

Imports allowed: exactly the `use` lines above. The modules you call are shown below the
contract:

```rust
crate::lineart::render(img: &DynamicImage, opts: &LineArtOptions) -> Result<GrayImage, Error>
                         // validates opts; EmptyImage for 0 x 0; black (0) lines on white (255)
crate::thin::thin(fg: &[bool], width: usize, height: usize) -> Vec<bool>
crate::strokes::trace(fg: &[bool], width: usize, height: usize) -> Vec<Vec<(u32, u32)>>
crate::smooth::simplify(points: &[Pt], epsilon: f64) -> Vec<Pt>    // Pt = (f64, f64); RDP
crate::svg::fmt_num(v: f64) -> String     // 2 decimals, no trailing zeros: 0.8333 -> "0.83"
crate::select::Mask      // width(), height(), bits() row-major, true = selected
```

## Rules for `StrokeOptions`

- `Default`: `tolerance 1.0`, `width 1.0`, `min_pixels 3`.
- `validate`, checks in this order, each failing with
  `Error::InvalidOption { name, reason: reason.to_string() }`:
  1. `tolerance` not finite or outside `0.0..=10.0` -> name `"tolerance"`, reason
     `"must be a number from 0 to 10"`;
  2. `width` not finite, `<= 0`, or `> 20` -> name `"stroke-width"`, reason
     `"must be above 0 and at most 20"`;
  3. `min_pixels > 10000` -> name `"min-pixels"`, reason `"must be at most 10000"`.

## Rules for `chain_path` (`chain` is never empty)

1. `pts` = each `(x, y)` as the pixel centre `(x as f64 + 0.5, y as f64 + 0.5)`;
   `q = simplify(&pts, tolerance)`.
2. Start `d = "M {x} {y}"` with `q[0]` (every number through `fmt_num`).
3. ONE point (`q.len() == 1`): append `" L {x} {y}"` with that same point (a dot - round
   caps draw it) and return.
4. `closed` = `q[0] == q[q.len() - 1] && q.len() > 2`. `m = q.len() - 1` segments.
5. For each segment `i` in `0..m`, `a = q[i]`, `b = q[i + 1]`:
   - `tolerance == 0.0`: append `" L {b.x} {b.y}"`;
   - otherwise Catmull-Rom: `p0 = q[i - 1]` if `i > 0`, else `q[m - 1]` if `closed`, else
     `a`; `p3 = q[i + 2]` if `i + 1 < m`, else `q[1]` if `closed`, else `b`;
     `c1 = a + (b - p0) / 6`, `c2 = b - (p3 - a) / 6` (per coordinate, in that order);
     append `" C {c1.x} {c1.y} {c2.x} {c2.y} {b.x} {b.y}"`.
6. If `closed`, append `" Z"`.

## Rules for `render_svg` (in order)

1. `opts.validate()?`, then `stroke.validate()?`.
2. `gray = lineart::render(img, opts)?` (this also refuses a 0 x 0 image).
3. If `keep` is `Some(m)` and its width or height differs from the image's:
   `Err(Error::InvalidOption { name: "selection", reason: format!("is {}x{} but the image is {}x{}", mw, mh, w, h) })`.
4. `fg[i] = gray[i] == 0 && (keep is None || m.bits()[i])` for every pixel, row-major.
5. `chains = trace(&thin(&fg, w, h), w, h)`.
6. For each chain in order: its DISTINCT pixel count is `len - 1` when it has more than
   one point and its first equals its last (a closed loop), else `len`. Drop it if that is
   `< stroke.min_pixels`; otherwise its path is `chain_path(&chain, stroke.tolerance)`.
7. The document, exactly (`W`, `H` = the image size):
   `<svg xmlns="http://www.w3.org/2000/svg" width="W" height="H" viewBox="0 0 W H">` + `\n`;
   then, if there is at least one path, ONE element
   `<path fill="none" stroke="#000000" stroke-width="{fmt_num(width)}" stroke-linecap="round" stroke-linejoin="round" d="{paths joined by one space}"/>` + `\n`;
   then `</svg>` + `\n`. No background rectangle.

## Worked examples

`chain_path`:

| chain | tolerance | result |
|---|---|---|
| `[(1,1)]` | 1.0 | `"M 1.5 1.5 L 1.5 1.5"` |
| `[(0,0),(1,0),(2,0),(3,0)]` | 0.0 | `"M 0.5 0.5 L 3.5 0.5"` (the straight run is one line) |
| `[(0,0),(1,0),(2,0),(3,0)]` | 1.0 | `"M 0.5 0.5 C 1 0.5 3 0.5 3.5 0.5"` |
| `[(0,0),(0,1),(0,2),(1,2),(2,2)]` | 1.0 | `"M 0.5 0.5 C 0.5 0.83 0.17 2.17 0.5 2.5 C 0.83 2.83 2.17 2.5 2.5 2.5"` |
| `[(0,0),(1,0),(2,0),(2,1),(2,2),(1,2),(0,2),(0,1),(0,0)]` | 0.0 | `"M 0.5 0.5 L 2.5 0.5 L 2.5 2.5 L 0.5 2.5 L 0.5 0.5 Z"` |
| `[(0,0),(4,0),(4,4),(0,4),(0,0)]` | 0.5 | `"M 0.5 0.5 C 1.17 -0.17 3.83 -0.17 4.5 0.5 C 5.17 1.17 5.17 3.83 4.5 4.5 C 3.83 5.17 1.17 5.17 0.5 4.5 C -0.17 3.83 -0.17 1.17 0.5 0.5 Z"` |

The L-shape row by hand: `q = [(0.5,0.5), (0.5,2.5), (2.5,2.5)]` (the corner is 1.41 from
the end-to-end line, over 1.0). Segment 0: `p0 = a` (open start), `p3 = (2.5,2.5)`:
`c1 = (0.5, 0.5 + 2/6)`, `c2 = (0.5 - 2/6, 2.5 - 2/6)`. Segment 1: `p0 = (0.5,0.5)`,
`p3 = b` (open end): `c1 = (0.5 + 2/6, 2.5 + 2/6)`, `c2 = (2.5 - 2/6, 2.5)`.

`render_svg`, with `RING` = the 3 x 3 RGB image, black except a white centre, and
`SOBEL` = `LineArtOptions { filter: Sobel, blur: 0.0, low: 361.4, high: 361.4 }` (line
art: every pixel black except the centre; thinning leaves the diamond (1,0), (2,1), (1,2),
(0,1)); `T0` = `StrokeOptions { tolerance: 0.0, ..Default::default() }`; `HEAD` =
`<svg xmlns="http://www.w3.org/2000/svg" width="3" height="3" viewBox="0 0 3 3">\n`;
`P` = `<path fill="none" stroke="#000000" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" d="`:

| call | result |
|---|---|
| `RING, SOBEL, T0, None` | `HEAD + P + "M 1.5 0.5 L 2.5 1.5 L 1.5 2.5 L 0.5 1.5 L 1.5 0.5 Z\"/>\n</svg>\n"` |
| same, keep = every pixel with `x >= 1` | `HEAD + P + "M 1.5 0.5 L 2.5 1.5 L 1.5 2.5\"/>\n</svg>\n"` |
| same, `min_pixels: 5` | `HEAD + "</svg>\n"` (the loop has 4 distinct pixels) |
| same, `width: 2.5` | as the first row with `stroke-width="2.5"` |
| a 4 x 4 all-white image, Sobel low 100, default stroke | `<svg ... width="4" height="4" viewBox="0 0 4 4">\n</svg>\n` |
| `RING, SOBEL, tolerance 11.0` | `Err(InvalidOption { name: "tolerance", reason: "must be a number from 0 to 10" })` |
| `RING, SOBEL, T0, Some(Mask::new(2, 3, true))` | `Err(InvalidOption { name: "selection", reason: "is 2x3 but the image is 3x3" })` |
| a 0 x 0 image, default options | `Err(EmptyImage)` |
| `LineArtOptions { blur: 60.0, .. }` | the `blur` error from `opts.validate()`, before anything else |
