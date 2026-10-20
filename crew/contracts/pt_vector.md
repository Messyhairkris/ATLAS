# Contract: vector.rs - vectorization engine (`--mode vector`)

Module `src/vector.rs` of the crate `photo_tools`. Photo in, flat-colour SVG text out:
quantize the colours, merge specks, trace region outlines, smooth them into Bezier curves
and write the SVG - by calling the already accepted modules in order. Library code: no
I/O, no panics on valid options.

## API (exact)

```rust
//! Raster to flat-colour SVG.

use image::DynamicImage;

pub fn render(img: &DynamicImage, opts: &VectorOptions) -> Result<String, Error>
```

Imports allowed: `image::DynamicImage` and these accepted modules (source shown below
the contract):

```rust
crate::kmeans::quantize       // (rgb: &[u8], k: usize, max_iter: usize) -> Palette { colors: Vec<[u8; 3]>, labels: Vec<u8> }
crate::despeckle::despeckle   // (labels: &[u8], width, height, min_area: usize) -> Vec<u8>
crate::contour::trace         // (labels: &[u8], width, height) -> Vec<Loop>; Loop { label: u8, points: Vec<(u32, u32)>, junction: Vec<bool> }
crate::smooth::smooth_loop    // (points: &[(u32, u32)], junction: &[bool], epsilon: f64) -> Vec<Cubic>
                              //   Cubic { from, c1, c2, to }, each (f64, f64)
crate::svg::{document, path_data}
                              // path_data(loops: &[Vec<[f64; 8]>]) -> String
                              // document(width: u32, height: u32, background: [u8; 3], shapes: &[([u8; 3], String)]) -> String
crate::options::{Error, VectorOptions}   // VectorOptions { colors: u8, smoothness: f32, speckle: u32, max_iterations: u32 }
```

The API card (reference below) gives the exact `image` signatures.

## Rules (in order)

1. `opts.validate()?` FIRST.
2. If width or height is 0: `Err(Error::EmptyImage)`.
3. `let rgb = img.to_rgb8();`
   `palette = quantize(rgb.as_raw(), opts.colors as usize, opts.max_iterations as usize)`.
4. `labels = despeckle(&palette.labels, w, h, opts.speckle as usize)` (w, h as `usize`).
5. BACKGROUND: count how many pixels of `labels` have each label `0..palette.colors.len()`;
   the background is `palette.colors[i]` for the label `i` with the largest count; ties ->
   the smaller label.
6. `loops = trace(&labels, w, h)`.
7. SHAPES: for each label `i` in `0..palette.colors.len()`, in order: take every loop with
   `loop.label == i` (in `trace`'s order); for each, `smooth_loop(&loop.points,
   &loop.junction, opts.smoothness as f64)`, and turn each `Cubic` `c` into
   `[c.from.0, c.from.1, c.c1.0, c.c1.1, c.c2.0, c.c2.1, c.to.0, c.to.1]`. That gives a
   `Vec<Vec<[f64; 8]>>` (one inner Vec per loop); the shape is
   `(palette.colors[i], path_data(&that))`. A label with no loops still yields a shape
   (its `d` is empty and `document` skips it).
8. Return `Ok(document(width, height, background, &shapes))` with the image's `u32` size.

## Worked examples

2x1 image: pixel (0,0) red (255,0,0), pixel (1,0) blue (0,0,255);
`VectorOptions { colors: 2, smoothness: 0.0, speckle: 0, max_iterations: 20 }`:
- quantize: bins in key order are blue (key 31) then red (key 31744), count 1 each ->
  colors `[[0,0,255], [255,0,0]]`, labels `[1, 0]`; despeckle with 0 changes nothing;
  counts tie 1-1 -> background label 0, `#0000ff`.
- result (each line ends in a newline):

```
<svg xmlns="http://www.w3.org/2000/svg" width="2" height="1" viewBox="0 0 2 1">
<rect width="2" height="1" fill="#0000ff"/>
<path fill="#0000ff" fill-rule="evenodd" d="M 1 0 C 1.33 0 1.67 0 2 0 C 2 0.33 2 0.67 2 1 C 1.67 1 1.33 1 1 1 C 1 0.67 1 0.33 1 0 Z"/>
<path fill="#ff0000" fill-rule="evenodd" d="M 1 0 C 1 0.33 1 0.67 1 1 C 0.67 1 0.33 1 0 1 C 0 0.67 0 0.33 0 0 C 0.33 0 0.67 0 1 0 Z"/>
</svg>
```

| input | opts | result |
|---|---|---|
| 5x1: 2 yellow then 3 black pixels | colors 2 | the `<rect>` fill is `#000000` (black has more pixels) |
| 3x2 all (10, 200, 30) | colors 8, speckle 0 | one `<path>`, fill `#0ac81e` (quantize returns one colour) |
| 0x0 image | colors 1 (invalid) | `Err(InvalidOption { name: "colors", reason: "must be from 2 to 64" })` |
| 0x0 image | colors 8 | `Err(EmptyImage)` |
| 6x6, dark left half, light right half, one light speck at (1,1) | colors 2, smoothness 0, speckle 2 | 2 loops in total (the speck merged); with speckle 0, 4 loops |
