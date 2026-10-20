# Contract: sobel.rs - Sobel gradient magnitude and edge mask

Module `src/sobel.rs` of the crate `photo_tools`. The Sobel variant of line art: how
sharply brightness changes at each pixel, and a black-on-white mask of the strong changes.

## API (exact)

```rust
//! Sobel gradient magnitude and edge mask.

/// round(sqrt(gx^2 + gy^2)) per pixel; samples outside the image use the nearest
/// edge pixel (coordinates clamped).
pub fn magnitude(gray: &[u8], width: usize, height: usize) -> Vec<u16>

/// 0 (black) where magnitude >= threshold, else 255 (white).
pub fn edge_mask(gray: &[u8], width: usize, height: usize, threshold: u16) -> Vec<u8>
```

Imports allowed: none needed (std prelude only).

`gray` is row-major (`gray[y * width + x]`), `gray.len() == width * height`; results have
the same layout and length.

## Rules

1. For pixel `(x, y)`, read the 3x3 neighbourhood `p(x + i - 1, y + j - 1)` for
   `i, j in 0..3`. A coordinate outside the image is CLAMPED to the nearest edge:
   column `-1` reads column 0, column `width` reads column `width - 1`, same for rows.
2. Kernels, indexed `[j][i]` (row j, column i):
   ```
   KX = [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]
   KY = [[-1, -2, -1], [0, 0, 0], [1, 2, 1]]
   ```
   `gx = sum of KX[j][i] * p(...)`, `gy = sum of KY[j][i] * p(...)`, in `i32`.
3. `magnitude = sqrt(gx*gx + gy*gy)` computed in `f64`, rounded with `f64::round`
   (half away from zero), stored as `u16`. The largest possible value is 1443.
4. `edge_mask`: 0 where `magnitude >= threshold`, else 255. So `threshold == 0` makes
   every pixel 0.

## Worked examples

| image (row-major) | w x h | magnitude |
|---|---|---|
| all 90 | 4x3 | all 0 |
| every row `[0, 0, 255, 255]` | 4x3 | every row `[0, 1020, 1020, 0]` |
| `[0, 0, 0, 255, 255, 255]` | 3x2 | all 1020 (gy only) |
| `[0,0,0, 0,255,0, 0,0,0]` | 3x3 | `[361, 510, 361, 510, 0, 510, 361, 510, 361]` |
| `[200]` | 1x1 | `[0]` |
| `[0, 1, 1, 2]` | 2x2 | first value 6 (gx = 4, gy = 4, sqrt 32 = 5.66) |

Single bright pixel, step by step for `(0, 0)`: clamping makes the columns read
`[0, 0, 1]` and the rows `[0, 0, 1]`, so the 255 sits at kernel position `[2][2]`:
`gx = 1 * 255`, `gy = 1 * 255`, `sqrt(130050) = 360.62 -> 361`. For `(1, 0)` it sits at
`[2][1]`: `gx = 0`, `gy = 2 * 255 = 510`.

| call on the single bright pixel image | result |
|---|---|
| `edge_mask(.., 400)` | `[255, 0, 255, 0, 255, 0, 255, 0, 255]` |
| `edge_mask(.., 361)` | `[0, 0, 0, 0, 255, 0, 0, 0, 0]` |
| `edge_mask(.., 362)` | `[255, 0, 255, 0, 255, 0, 255, 0, 255]` |
| `edge_mask(.., 511)` | all 255 |
