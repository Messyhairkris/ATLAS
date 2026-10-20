# Contract: ascii.rs - text art from cell brightness

Module `src/ascii.rs` of the crate `photo_tools`. Splits the image into cells twice as
tall as wide (terminal characters are tall) and prints one character per cell from a
density ramp, optionally in 24-bit ANSI colour. Byte-exact: tests compare whole strings.

## API (exact)

```rust
//! Text art from cell brightness.

/// Lightest to darkest.
pub const RAMP: &[u8] = b" .:-=+*#%@";

/// (cell_w, cell_h, cols, rows) for an image and a requested column count.
pub fn grid(width: usize, height: usize, columns: usize) -> (usize, usize, usize, usize)

/// One line per row of cells, each ending in "\n". With `rgb`, every character is
/// preceded by a 24-bit colour escape and every line ends with a reset.
pub fn render(
    gray: &[u8],
    rgb: Option<&[u8]>,
    width: usize,
    height: usize,
    columns: usize,
    invert: bool,
) -> String
```

Imports allowed: std only.

`gray` is row-major (`gray[y * width + x]`, length `width * height`); `rgb`, when given,
is the same pixels as packed RGB (`rgb[(y * width + x) * 3 + k]`, k = 0, 1, 2).

## Rules

1. `grid`: if `width == 0` or `height == 0`, return `(0, 0, 0, 0)`.
2. `columns` is clamped to `1..=width`. `cell_w = width / columns`;
   `cell_h = cell_w * 2`, but if `height < cell_h` then `cell_h = height`.
   `cols = width / cell_w`; `rows = height / cell_h` (integer division). Pixels past
   `cols * cell_w` or `rows * cell_h` are never read.
3. `render`: for each row of cells top to bottom, for each cell left to right:
   `mean = (sum of the cell's gray values) / (cell_w * cell_h)` in `u32`, truncating.
4. Ramp index: `(255 - mean) * 9 / 255` (integer); with `invert`, `mean * 9 / 255`.
   The character is `RAMP[index]`.
5. When `rgb` is `Some`, before EACH character write `"\x1b[38;2;{r};{g};{b}m"` where
   `r, g, b` are the cell's channel means (sum / count, truncating, like rule 3); after the
   LAST character of each line write `"\x1b[0m"`.
6. Every line, including the last, ends with `"\n"`. No cells -> `""`.

## Worked examples

| `grid(w, h, columns)` | result |
|---|---|
| `grid(4, 2, 2)` | `(2, 2, 2, 1)` - cell_h would be 4 > height 2, so 2 |
| `grid(10, 10, 3)` | `(3, 6, 3, 1)` |
| `grid(0, 5, 3)` / `grid(5, 0, 3)` | `(0, 0, 0, 0)` |
| `grid(4, 8, 0)` | `(4, 8, 1, 1)` - columns clamped to 1 |
| `grid(3, 6, 10)` | `(1, 2, 3, 3)` - columns clamped to 3 |
| `grid(100, 30, 25)` | `(4, 8, 25, 3)` |

| mean | (255 - mean) * 9 / 255 | char |
|---|---|---|
| 255 | 0 | `' '` |
| 200 | 1 | `'.'` |
| 128 | 4 | `'='` |
| 100 | 5 | `'+'` |
| 28 | 8 | `'%'` |
| 0 | 9 | `'@'` |

| call | result |
|---|---|
| `render(&[0; 8], None, 4, 2, 2, false)` | `"@@\n"` |
| `render(&[255; 8], None, 4, 2, 2, false)` | `"  \n"` |
| `render(&[0; 8], None, 4, 2, 2, true)` | `"  \n"` |
| `render(&[0, 255, 0, 255, 128, 200, 128, 200], None, 2, 4, 2, false)` | `"@ \n=.\n"` |
| `render(&[0, 1], None, 1, 2, 1, false)` | `"@\n"` - mean (0+1)/2 = 0 |
| 5x4 image, black except column x = 4 white, columns 2 | `"@@\n"` - x = 4 is past the cells |
| `render(&[0, 0], Some(&[10,20,30, 11,21,31]), 1, 2, 1, false)` | `"\x1b[38;2;10;20;30m@\x1b[0m\n"` |
| `render(&[], None, 0, 0, 10, false)` | `""` |

Two coloured cells (2x2 image, gray `[76, 29, 76, 29]`, rgb red, blue, red, blue,
columns 2): `"\x1b[38;2;255;0;0m*\x1b[38;2;0;0;255m#\x1b[0m\n"`.
