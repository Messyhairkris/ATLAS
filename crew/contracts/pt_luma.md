# Contract: luma.rs - gray levels from RGB, and inversion

Module `src/luma.rs` of the crate `photo_tools`. Three small pure functions on bytes.

## API (exact)

```rust
//! Gray levels from RGB, and inversion.

/// Rec. 601 luma of one pixel, rounded: (299 r + 587 g + 114 b + 500) / 1000.
pub fn luma(r: u8, g: u8, b: u8) -> u8

/// One gray byte per complete RGB triple; a trailing partial triple is ignored.
pub fn rgb_to_gray(rgb: &[u8]) -> Vec<u8>

/// 255 - v for every byte.
pub fn invert(gray: &[u8]) -> Vec<u8>
```

Imports allowed: none needed (std prelude only).

## Rules

1. `luma`: compute `(299 * r + 587 * g + 114 * b + 500) / 1000` in `u32` (each byte
   widened to `u32` BEFORE multiplying), integer division, and return it as `u8`. The
   largest possible value is exactly 255.
2. `rgb_to_gray`: walk `rgb` three bytes at a time (`chunks_exact(3)` does exactly this);
   each triple `[r, g, b]` gives `luma(r, g, b)`. If `rgb.len()` is not a multiple of 3,
   the 1 or 2 bytes left over at the end are ignored. Empty in, empty out.
3. `invert`: `255 - v` for each byte, same order, same length. Empty in, empty out.

## Worked examples

| call | result | why |
|---|---|---|
| `luma(0, 0, 0)` | 0 | 500 / 1000 = 0 |
| `luma(255, 255, 255)` | 255 | 255500 / 1000 = 255 |
| `luma(255, 0, 0)` | 76 | 76745 / 1000 |
| `luma(0, 255, 0)` | 150 | 150185 / 1000 |
| `luma(0, 0, 255)` | 29 | 29570 / 1000 |
| `luma(10, 20, 30)` | 18 | (2990 + 11740 + 3420 + 500) / 1000 = 18650 / 1000 |
| `luma(0, 0, 5)` | 1 | 570 + 500 = 1070 -> 1 (the +500 rounds) |
| `luma(0, 0, 4)` | 0 | 456 + 500 = 956 -> 0 |
| `rgb_to_gray(&[255, 0, 0, 0, 255, 0, 7])` | `vec![76, 150]` | the lone 7 is ignored |
| `rgb_to_gray(&[1, 2])` | `vec![]` | no complete triple |
| `invert(&[0, 255, 100, 1])` | `vec![255, 0, 155, 254]` | |
| `invert(&[])` | `vec![]` | |

`255 * 299` overflows `u8` and `u16`: widen first (`r as u32 * 299`).
