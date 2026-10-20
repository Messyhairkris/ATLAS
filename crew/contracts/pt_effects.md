# Contract: effects.rs - sketch and retro engine (`--mode fx`)

Module `src/effects.rs` of the crate `photo_tools`. One entry point that applies the
chosen style - pencil sketch, Floyd-Steinberg dither, halftone, cross-hatching or ASCII
art - by calling the already accepted modules. Library code: no I/O, no panics on valid
options.

## API (exact)

```rust
//! Sketch, dither, halftone, hatch and ASCII effects.

use image::{DynamicImage, GrayImage};

/// An effect's result: a gray image, or text for the ASCII style.
#[derive(Debug, Clone, PartialEq)]
pub enum EffectOutput {
    Image(GrayImage),
    Text(String),
}

pub fn render(img: &DynamicImage, opts: &EffectOptions) -> Result<EffectOutput, Error>
```

Imports allowed: `image::{DynamicImage, GrayImage}`,
`imageproc::filter::gaussian_blur_f32`, and these accepted modules (source shown below
the contract):

```rust
crate::luma::{rgb_to_gray, invert}             // rgb_to_gray(&[u8]) -> Vec<u8>; invert(&[u8]) -> Vec<u8>
crate::dodge::dodge_layers                     // (base: &[u8], blend: &[u8]) -> Vec<u8>
crate::dither::floyd_steinberg                 // (gray, width, height) -> Vec<u8>
crate::halftone::halftone                      // (gray, width, height, cell: usize) -> Vec<u8>
crate::hatch::hatch                            // (gray, width, height, spacing: usize) -> Vec<u8>
crate::ascii::render                           // (gray, rgb: Option<&[u8]>, width, height, columns: usize, invert: bool) -> String
crate::options::{EffectOptions, Error, Style}  // EffectOptions { style, blur, cell, columns, ansi, invert }
```

The API card (reference below) gives the exact `image` and `imageproc` signatures.
Note that `crate::ascii::render` and this module's `render` share a name: import the
module (`use crate::ascii;` then `ascii::render(..)`) or rename on import.

## Rules (in order)

1. `opts.validate()?` FIRST.
2. If width or height is 0: `Err(Error::EmptyImage)`.
3. `let rgb = img.to_rgb8();` `let gray = rgb_to_gray(rgb.as_raw());` (Rec. 601; never
   `to_luma8`). `w, h` = the image size as `usize`; `cell = opts.cell as usize`.
4. By `opts.style`:
   - `Sketch`: `inverted = invert(&gray)` as a `GrayImage` (w x h);
     `blurred = gaussian_blur_f32(&inverted, opts.blur)` (validation guarantees blur >= 0.5);
     pixels = `dodge_layers(&gray, blurred.as_raw())`.
   - `Dither`: `floyd_steinberg(&gray, w, h)`.
   - `Halftone`: `halftone(&gray, w, h, cell)`.
   - `Hatch`: `hatch(&gray, w, h, cell)` (the `cell` option is the hatch spacing).
   - `Ascii`: return `Ok(EffectOutput::Text(ascii::render(&gray, colour, w, h,
     opts.columns as usize, opts.invert)))` where `colour` is `Some(rgb.as_raw())` (the
     bytes as a slice) when `opts.ansi`, else `None`.
5. For the four image styles return `Ok(EffectOutput::Image(..))`: the pixels as a
   `GrayImage` of the input's width and height.

## Worked examples

| input | opts | result |
|---|---|---|
| 1x1 RGB (0, 200, 0) | Dither | `Image` with byte `[0]` (Rec. 601 gray 117 < 128; `to_luma8` would give 143 -> 255) |
| 1x1 RGB (0, 255, 0) | Dither | `Image` with byte `[255]` (gray 150) |
| 0x3 image | `cell: 1` (invalid) | `Err(InvalidOption { name: "cell", reason: "must be from 2 to 64" })` |
| 0x3 image | Dither, defaults | `Err(EmptyImage)` |
| 20x12 image, Hatch, cell 5 | | `Image` whose bytes equal `hatch(&gray, 20, 12, 5)` |
| 20x12 image, Ascii, columns 7 | | `Text(ascii::render(&gray, None, 20, 12, 7, false))` |
| 20x12 image, Ascii, columns 5, ansi, invert | | `Text(ascii::render(&gray, Some(rgb bytes), 20, 12, 5, true))` |
| 20x12 image, Sketch, blur 3.0 | | `Image` whose bytes equal `dodge_layers(&gray, gaussian_blur_f32(&invert(&gray) as image, 3.0).as_raw())` |
