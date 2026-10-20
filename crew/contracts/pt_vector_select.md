# Contract: vector_select.rs - flat-colour SVG of the selected area only

Module `src/vector_select.rs` of the crate `photo_tools`. Like `vector::render`, but for
a selection: the palette is fitted to the SELECTED pixels only (so the colours are spent
on the area of interest, not on the background the user cut away), and nothing outside
the selection is drawn - no background rectangle, so it is transparent.

## API (exact)

```rust
//! Flat-colour SVG of the selected area only; the rest is left transparent.

use image::DynamicImage;

use crate::contour::trace;
use crate::despeckle::despeckle;
use crate::kmeans::quantize;
use crate::options::{Error, VectorOptions};
use crate::select::Mask;
use crate::smooth::smooth_loop;
use crate::svg::{hex, path_data};

/// Like vector::render, but the palette is fitted to the selected pixels only and
/// nothing outside the selection is drawn (no background rectangle).
pub fn render_selected(img: &DynamicImage, opts: &VectorOptions, keep: &Mask) -> Result<String, Error>
```

Imports allowed: exactly the `use` lines above. The accepted modules are shown below the
contract; `vector.rs` (shown too) is the pipeline this one follows.

## Rules (in order)

1. `opts.validate()?`.
2. If the image width or height is 0: `Err(Error::EmptyImage)`.
3. If `keep`'s width or height differs from the image's:
   `Err(Error::InvalidOption { name: "selection", reason: format!("is {}x{} but the image is {}x{}", kw, kh, w, h) })`.
4. Start the document with
   `<svg xmlns="http://www.w3.org/2000/svg" width="W" height="H" viewBox="0 0 W H">` + `\n`.
   If `keep.count() == 0`, append `</svg>` + `\n` and return it (no shapes).
5. PALETTE: `rgb = img.to_rgb8()`; `chosen` = the 3 bytes of every SELECTED pixel, in
   raster order; `palette = quantize(&chosen, opts.colors as usize, opts.max_iterations as usize)`.
6. LABELS for the whole image: `outside = palette.colors.len() as u8`. Walk the pixels in
   raster order: a selected pixel takes the NEXT label from `palette.labels` (they are in
   the same order as `chosen`); an unselected pixel gets `outside`.
7. `labels = despeckle(&labels, w, h, opts.speckle as usize)`; then set every UNSELECTED
   pixel back to `outside` (despeckling must not fill holes in the selection). Selected
   specks that despeckle merged into `outside` stay `outside`.
8. `loops = trace(&labels, w, h)`. For each palette label `0..palette.colors.len()` in
   order: its segments are, for every loop with that label, in loop order,
   `smooth_loop(&l.points, &l.junction, opts.smoothness as f64)` as
   `[from.0, from.1, c1.0, c1.1, c2.0, c2.1, to.0, to.1]` arrays; `d = path_data(&segs)`.
   If `d` is not empty append
   `<path fill="{hex(color)}" fill-rule="evenodd" d="{d}"/>` + `\n`.
   The `outside` label is never drawn.
9. Append `</svg>` + `\n`.

With every pixel selected the result is exactly `vector::render`'s document without its
`<rect .../>` line.

## Worked examples

`RB` = the 2 x 1 RGB image red `(255,0,0)` | blue `(0,0,255)`;
`VO` = `VectorOptions { colors: 2, smoothness: 0.0, speckle: 0, max_iterations: 5 }`;
`HEAD` = `<svg xmlns="http://www.w3.org/2000/svg" width="2" height="1" viewBox="0 0 2 1">\n`.

| call | result |
|---|---|
| `RB, VO, keep = left pixel only` | `HEAD + "<path fill=\"#ff0000\" fill-rule=\"evenodd\" d=\"M 1 0 C 1 0.33 1 0.67 1 1 C 0.67 1 0.33 1 0 1 C 0 0.67 0 0.33 0 0 C 0.33 0 0.67 0 1 0 Z\"/>\n</svg>\n"` |
| `RB, VO, keep = both` | `HEAD + "<path fill=\"#0000ff\" fill-rule=\"evenodd\" d=\"M 1 0 C 1.33 0 1.67 0 2 0 C 2 0.33 2 0.67 2 1 C 1.67 1 1.33 1 1 1 C 1 0.67 1 0.33 1 0 Z\"/>\n<path fill=\"#ff0000\" fill-rule=\"evenodd\" d=\"M 1 0 C 1 0.33 1 0.67 1 1 C 0.67 1 0.33 1 0 1 C 0 0.67 0 0.33 0 0 C 0.33 0 0.67 0 1 0 Z\"/>\n</svg>\n"` (= `vector::render(RB, VO)` without its rect line) |
| `RB, VO, keep = none` | `HEAD + "</svg>\n"` |
| `RB, VO, keep = Mask::new(1, 1, true)` | `Err(InvalidOption { name: "selection", reason: "is 1x1 but the image is 2x1" })` |
| `RB, colors 1` (invalid) | the `colors` error from `validate()` |
| a 0 x 0 image | `Err(EmptyImage)` |
