# Contract: hatch.rs - cross-hatching

Module `src/hatch.rs` of the crate `photo_tools`. Turns a gray image into black hatch
lines on white; darker pixels collect more layers of lines.

## API (exact)

```rust
//! Cross-hatching.

/// Black (0) hatch lines on white (255); darker pixels collect more layers.
pub fn hatch(gray: &[u8], width: usize, height: usize, spacing: usize) -> Vec<u8>
```

Imports allowed: none needed (std prelude only).

`gray` is row-major: pixel `(x, y)` is `gray[y * width + x]`, and the caller guarantees
`gray.len() == width * height`. The result has the same layout and length.

## Rules

1. `s = spacing`, but if `spacing < 2` use `s = 2`.
2. Each pixel `(x, y)` with value `v` is BLACK (0) if ANY of these holds, else WHITE (255):
   - layer 1: `v < 192` and `(x + y) % s == 0`
   - layer 2: `v < 128` and `x % s == y % s`
   - layer 3: `v < 64` and `y % s == 0`
   - layer 4: `v < 32` and `x % s == 0`
3. Each pixel is decided by its own value only. Comparisons are strict (`<`).

## Worked examples (W = 255)

4 wide, 3 high, spacing 3, every pixel the same value `v`:

| v | row 0 | row 1 | row 2 | layers on |
|---|---|---|---|---|
| 255 or 192 | W W W W | W W W W | W W W W | none |
| 191, 150, 128 | 0 W W 0 | W W 0 W | W 0 W W | 1 |
| 127, 100, 64 | 0 W W 0 | W 0 0 W | W 0 0 W | 1, 2 |
| 63, 50, 32 | 0 0 0 0 | W 0 0 W | W 0 0 W | 1, 2, 3 |
| 31, 20, 0 | 0 0 0 0 | 0 0 0 0 | 0 0 0 0 | 1-4 |

5 wide, 4 high, spacing 4, value 0 (all four layers):

```
0 0 0 0 0
0 0 W 0 0
0 W 0 W 0
0 0 W 0 0
```

Mixed: `hatch(&[0, 255, 255, 255, 0, 255, 255, 255], 4, 2, 3)` is
`vec![0, W, W, W, 0, W, W, W]` (only the dark left column has lines).

`hatch(g, w, h, 0)` and `hatch(g, w, h, 1)` equal `hatch(g, w, h, 2)` (rule 1).
