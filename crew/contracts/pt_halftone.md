# Contract: halftone.rs - halftone dots

Module `src/halftone.rs` of the crate `photo_tools`. Splits the image into square cells
and draws one black dot per cell whose area follows the cell's darkness, like newspaper
print.

## API (exact)

```rust
//! Amplitude-modulated halftone dots.

/// One black dot per cell, its area following the cell's darkness.
pub fn halftone(gray: &[u8], width: usize, height: usize, cell: usize) -> Vec<u8>
```

Imports allowed: `std::f64::consts::SQRT_2` (or write the constant out).

`gray` is row-major (`gray[y * width + x]`), `gray.len() == width * height`. The result
has the same layout; every byte is 0 (black) or 255 (white).

## Rules

1. `c = cell`, but if `cell < 2` use `c = 2`.
2. Cells tile the image from `(0, 0)`: cell `(cx, cy)` covers columns
   `cx*c .. min((cx+1)*c, width)` and rows `cy*c .. min((cy+1)*c, height)` (end
   excluded). Cells at the right and bottom edges may be smaller than `c x c`.
3. `mean` = (sum of the cell's pixels inside the image) / (their count), in `u32` with
   integer division (truncating).
4. `darkness = (255 - mean) as f64 / 255.0`.
   `r = c as f64 * 0.5 * SQRT_2 * darkness.sqrt()` (radius; full darkness reaches the
   cell's corners).
5. The cell centre is `(cx*c) as f64 + c as f64 / 2.0`, likewise for y - always for a
   FULL cell, even when the cell is cut off by the image edge.
6. A pixel `(x, y)` in the cell is black if `dx*dx + dy*dy < r*r` with
   `dx = x as f64 + 0.5 - centre_x` and `dy = y as f64 + 0.5 - centre_y`; otherwise white.
   The comparison is strict, so a white cell (r = 0) has no black pixel at all.

## Worked examples (W = 255)

| gray | w x h | cell | output | why |
|---|---|---|---|---|
| all 255 | 4x4 | 4 | all W | r = 0 |
| all 255 | 3x3 | 3 | all W | centre pixel distance 0 is not < 0 |
| all 0 | 4x4 | 4 | all 0 | r^2 = 8; corners are 1.5^2 + 1.5^2 = 4.5 |
| all 128 | 4x4 | 4 | `W 0 0 W / 0 0 0 0 / 0 0 0 0 / W 0 0 W` | r^2 = 3.98: corners 4.5 out, edges 2.5 in |
| all 128 | 3x3 | 4 | `W 0 0 / 0 0 0 / 0 0 0` | one clipped cell, centre (2, 2): only (0,0) is 4.5 away |
| `[0, 0, 0, 0, 255]` | 5x1 | 4 | `[0, 0, 0, 0, W]` | cell 0 mean 0; cell 1 is x = 4 only, mean 255 |
| `[0,0,255,255, 0,0,255,255]` | 4x2 | 2 | `[0,0,W,W, 0,0,W,W]` | two independent cells |

For mean 128: darkness = 127/255 = 0.498, r = 4 * 0.5 * 1.41421 * 0.7057 = 1.996,
r^2 = 3.984. Pixel centres sit 0.5 or 1.5 from the cell centre on each axis, so their
squared distances are 0.5, 2.5 or 4.5.

`halftone(g, w, h, 0)` and `halftone(g, w, h, 1)` equal `halftone(g, w, h, 2)`.
