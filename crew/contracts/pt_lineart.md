# Contract: lineart.rs - line art engine (`--mode lineart`)

Module `src/lineart.rs` of the crate `photo_tools`. Turns a photo into black lines on a
white background, with the Sobel module or imageproc's Canny detector. This is library
code other Rust programs will call directly, so it never panics on valid options and
never does I/O.

## API (exact)

```rust
//! Line art: black edges on white.

use image::{DynamicImage, GrayImage};

use crate::luma::rgb_to_gray;
use crate::options::{EdgeFilter, Error, LineArtOptions};
use crate::sobel::edge_mask;

/// Validate, convert to gray (Rec. 601), blur, then Sobel or Canny.
pub fn render(img: &DynamicImage, opts: &LineArtOptions) -> Result<GrayImage, Error>
```

Imports allowed: exactly the `use` lines above, plus `imageproc::filter::gaussian_blur_f32`
and `imageproc::edges::canny` (call them by full path or import them). The API card
(reference below) gives their exact signatures.

Already accepted modules you call (their source is shown below the contract):

```rust
crate::luma::rgb_to_gray(rgb: &[u8]) -> Vec<u8>           // Rec. 601, 1 byte per RGB triple
crate::sobel::edge_mask(gray: &[u8], width: usize, height: usize, threshold: u16) -> Vec<u8>
                                                          // 0 where magnitude >= threshold, else 255
crate::options::LineArtOptions { filter, blur, low, high }  // .validate() -> Result<(), Error>
crate::options::Error::{InvalidOption { .. }, EmptyImage}
crate::options::EdgeFilter::{Sobel, Canny}
```

## Rules (in order)

1. `opts.validate()?` FIRST - an invalid option is reported even for an empty image.
2. If `img.width() == 0` or `img.height() == 0`: `Err(Error::EmptyImage)`.
3. GRAY: `let rgb = img.to_rgb8();` then `rgb_to_gray(rgb.as_raw())`, wrapped back into a
   `GrayImage` of the same width and height (`GrayImage::from_raw(w, h, bytes)`).
   Do NOT use `img.to_luma8()` (it uses different weights; the tests can tell).
4. BLUR: if `opts.blur > 0.0`, replace the gray image with
   `imageproc::filter::gaussian_blur_f32(&gray, opts.blur)`. If `opts.blur == 0.0`, do
   not call it (it panics on 0).
5. EDGES:
   - `EdgeFilter::Sobel`: `threshold = opts.low.round()` as `u16` (validation guarantees
     it is >= 0; cap at `u16::MAX`), then
     `edge_mask(gray.as_raw(), width as usize, height as usize, threshold)`. Already black
     on white. `opts.high` is not used.
   - `EdgeFilter::Canny`: `imageproc::edges::canny(&gray, opts.low, opts.high)` gives
     WHITE edges on black; invert every byte (`255 - v`) to get black on white.
6. Return the result as a `GrayImage` with the input's width and height.

## Worked examples

A 3x3 RGB image, black except a white centre pixel; Sobel, blur 0:

| opts.low | threshold | output bytes (row-major) |
|---|---|---|
| 400.0 | 400 | `[255, 0, 255, 0, 255, 0, 255, 0, 255]` |
| 361.4 | 361 | `[0, 0, 0, 0, 255, 0, 0, 0, 0]` |
| 361.6 | 362 | `[255, 0, 255, 0, 255, 0, 255, 0, 255]` |

(The Sobel magnitudes of that image are `[361, 510, 361, 510, 0, 510, 361, 510, 361]`.)

3x1 image red, red, black; Sobel, blur 0, low 300: Rec. 601 gray is `[76, 76, 0]`,
magnitudes `[0, 304, 304]`, output `[255, 0, 0]`. (With `to_luma8` the gray would be 54
and the output all 255 - this is the rule-3 trap.)

| input | opts | result |
|---|---|---|
| 0x0 image | `blur: 60.0` (invalid) | `Err(InvalidOption { name: "blur", reason: "must be a number from 0 to 50" })` |
| 0x0 image | default | `Err(EmptyImage)` |
| 5x0 image | default | `Err(EmptyImage)` |
| any image, Canny, blur 1.2, low 45, high 90 | | bytes equal `255 - v` for every `v` of `canny(&gaussian_blur_f32(&gray, 1.2), 45.0, 90.0)` |

Gray (`ImageLuma8`) and RGBA inputs work the same way: `to_rgb8()` converts them.
