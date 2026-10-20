# Contract: dither.rs - Floyd-Steinberg error diffusion

Module `src/dither.rs` of the crate `photo_tools`. Turns gray into pure black and white
for laser engraving, spreading each pixel's rounding error to its unvisited neighbours.

## API (exact)

```rust
//! Floyd-Steinberg error diffusion to one bit.

/// Every output byte is 0 or 255. Rows top to bottom, each left to right.
pub fn floyd_steinberg(gray: &[u8], width: usize, height: usize) -> Vec<u8>
```

Imports allowed: none needed (std prelude only).

`gray` is row-major (`gray[y * width + x]`), `gray.len() == width * height`. The result
has the same layout.

## Rules

1. Copy `gray` into a working buffer of `i32`.
2. Visit pixels row by row from the top, and in EVERY row from left to right (no
   serpentine order).
3. At each pixel: `old` = the buffer value; `new` = 255 if `old >= 128`, else 0. Write
   `new` to the output. `err = old - new` (may be negative).
4. Add to the buffer, only where that neighbour exists inside the image:
   - right `(x+1, y)`: `err * 7 / 16`
   - down-left `(x-1, y+1)`: `err * 3 / 16`
   - down `(x, y+1)`: `err * 5 / 16`
   - down-right `(x+1, y+1)`: `err * 1 / 16`
   Each share is computed separately with `i32` multiplication then `/ 16`, which in
   Rust truncates toward zero (`-385 / 16 == -24`). A share for a missing neighbour is
   dropped, not moved elsewhere.
5. The buffer is never clamped: values above 255 or below 0 stay as they are and are
   compared in rule 3 as they are.

## Worked examples

| gray (w x h) | output | why |
|---|---|---|
| `[100]` 1x1 | `[0]` | 100 < 128 |
| `[128]` 1x1 | `[255]` | 128 >= 128 |
| `[100, 100]` 2x1 | `[0, 255]` | err 100, right gets 700/16 = 43 -> 143 |
| `[200, 152]` 2x1 | `[255, 255]` | err -55, right gets -385/16 = -24 (not -25) -> 128 |
| `[100, 255, 115]` 3x1 | `[0, 255, 255]` | 255 + 43 = 298 kept (rule 5): err 43, right gets 18 -> 133 |
| `[64, 64, 64, 64]` 2x2 | `[0, 0, 0, 255]` | see below |
| `[128, 128, 100, 100]` 2x2 | `[255, 0, 0, 255]` | row 1 runs left to right too |
| `[100; 9]` 3x3 | `[0, 255, 0, 0, 255, 0, 0, 0, 255]` | see below |

2x2 of 64: (0,0) 64 -> 0, err 64: right 28 -> 92, down 20 -> 84, down-right 4 -> 68.
(1,0) 92 -> 0, err 92: down-left 17 -> 101, down 28 -> 96. (0,1) 101 -> 0, err 101:
right 44 -> 140. (1,1) 140 -> 255.

3x3 of 100, buffer after each step (only changed cells):
(0,0) 100->0 err 100: (1,0)=143 (0,1)=131 (1,1)=106.
(1,0) 143->255 err -112: (2,0)=51 (0,1)=110 (1,1)=71 (2,1)=93.
(2,0) 51->0 err 51: (1,1)=80 (2,1)=108.
(0,1) 110->0 err 110: (1,1)=128 (0,2)=134 (1,2)=106.
(1,1) 128->255 err -127: (2,1)=53 (0,2)=111 (1,2)=67 (2,2)=93.
(2,1) 53->0 err 53: (1,2)=76 (2,2)=109.
(0,2) 111->0 err 111: (1,2)=124.
(1,2) 124->0 err 124: (2,2)=163.
(2,2) 163->255.
