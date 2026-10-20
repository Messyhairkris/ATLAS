# Contract: composite.rs - outside the selection is transparent white

Module `src/composite.rs` of the crate `photo_tools`. After a gray result is rendered,
the selection decides what is kept: pixels outside it become transparent white, and the
eraser can remove more afterwards. PNG keeps the transparency; JPEG has none, so it is
flattened to white.

## API (exact)

```rust
//! Selections and erasing applied to rendered images: outside is transparent white.

use image::{GrayAlphaImage, GrayImage, LumaA};

use crate::options::Error;
use crate::select::Mask;

/// Every pixel opaque: (v, 255).
pub fn opaque(img: &GrayImage) -> GrayAlphaImage

/// Selected pixels keep their value, opaque; the rest become transparent white (255, 0).
pub fn keep(img: &GrayImage, keep: &Mask) -> Result<GrayAlphaImage, Error>

/// Erased pixels (true in `erased`) become transparent white (255, 0).
pub fn erase(img: &mut GrayAlphaImage, erased: &Mask) -> Result<(), Error>

/// For formats without transparency (JPEG): transparent pixels become white 255.
pub fn flatten(img: &GrayAlphaImage) -> GrayImage

/// Before ASCII art: unselected pixels of a row-major gray buffer become blank -
/// 255, or 0 when the art is inverted - so cells outside the selection print spaces.
pub fn blank_outside(gray: &mut [u8], keep: &Mask, invert: bool) -> Result<(), Error>
```

Imports allowed: exactly the `use` lines above (you may also name `image::Luma`).
`crate::select::Mask` (source shown below the contract) gives `width()`, `height()`,
`bits()` (row-major, `true` = selected) and `get(x, y)`.

## Rules

1. SIZE CHECK, first, in `keep` and `erase`: if the mask's width or height differs from
   the image's, return
   `Err(Error::InvalidOption { name: "selection", reason: format!("is {}x{} but the image is {}x{}", mask_w, mask_h, img_w, img_h) })`
   and change nothing.
2. `blank_outside` checks LENGTH instead: if `gray.len() != keep.bits().len()`, return
   `Err(Error::InvalidOption { name: "selection", reason: format!("has {} pixels but the image has {}", keep.bits().len(), gray.len()) })`
   and change nothing.
3. `opaque`: same size, every pixel `LumaA([v, 255])`.
4. `keep`: same size; a selected pixel is `LumaA([v, 255])`, any other `LumaA([255, 0])`.
5. `erase`: every pixel whose bit is `true` becomes `LumaA([255, 0])`; the rest are
   untouched (already-transparent pixels stay as they are).
6. `flatten`: same size; a pixel with alpha `0` becomes `255`; any other alpha keeps its
   gray value `v` (the alpha is dropped).
7. `blank_outside`: every byte whose bit is `false` becomes `255`, or `0` when `invert`;
   selected bytes are untouched.

## Worked examples

Images are rows of pixels; `(v,a)` is a gray+alpha pixel. Masks: `#` selected, `.` not.

| call | input | result |
|---|---|---|
| `opaque` | `[10, 200]` (2 x 1) | `[(10,255), (200,255)]` |
| `keep` | `[10, 200, 0]` (3 x 1), mask `#.#` | `Ok([(10,255), (255,0), (0,255)])` |
| `keep` | 3 x 1 image, mask 2 x 1 | `Err(InvalidOption { name: "selection", reason: "is 2x1 but the image is 3x1" })` |
| `erase` | `[(10,255), (20,255), (255,0)]`, mask `.##` | `[(10,255), (255,0), (255,0)]` |
| `erase` | 2 x 2 image, mask 2 x 1 | `Err(... reason: "is 2x1 but the image is 2x2")`, image unchanged |
| `flatten` | `[(10,255), (37,0), (90,128)]` | `[10, 255, 90]` |
| `blank_outside` | `[5, 6, 7]`, mask `#.#`, invert false | `[5, 255, 7]` |
| `blank_outside` | `[5, 6, 7]`, mask `#.#`, invert true | `[5, 0, 7]` |
| `blank_outside` | 3 bytes, mask of 4 pixels | `Err(... reason: "has 4 pixels but the image has 3")`, bytes unchanged |
