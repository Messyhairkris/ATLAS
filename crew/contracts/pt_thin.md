# Contract: thin.rs - thin lines to one pixel (Guo-Hall)

Module `src/thin.rs` of the crate `photo_tools`. Line art from the Sobel filter has lines
2-5 pixels thick; tracing them as centerlines needs them one pixel wide. This is the
Guo-Hall parallel thinning algorithm (1989): it peels pixels off both sides of every line
until only a connected, one-pixel skeleton is left. It never breaks a line apart and never
removes a whole shape.

## API (exact)

```rust
//! Guo-Hall thinning to one-pixel lines.

/// Thin `fg` (true = line) to lines one pixel wide, keeping every line connected.
pub fn thin(fg: &[bool], width: usize, height: usize) -> Vec<bool>
```

Imports allowed: std only. `fg` is row-major (`fg[y * width + x]`),
`fg.len() == width * height`; the result has the same layout.

## Rules

1. NEIGHBOURS of pixel `(x, y)`, named as in the paper, clockwise from north:

   ```
   p9 p2 p3        p2 = (x, y-1)    p3 = (x+1, y-1)
   p8 p1 p4        p4 = (x+1, y)    p5 = (x+1, y+1)
   p7 p6 p5        p6 = (x, y+1)    p7 = (x-1, y+1)
                   p8 = (x-1, y)    p9 = (x-1, y-1)
   ```

   Each `pK` is `true` when that pixel is inside the image AND currently foreground.
   Outside the image counts as `false`.
2. For a foreground pixel, with `true` = 1 and `false` = 0:
   - `C = (!p2 & (p3 | p4)) + (!p4 & (p5 | p6)) + (!p6 & (p7 | p8)) + (!p8 & (p9 | p2))`
   - `N1 = (p9 | p2) + (p3 | p4) + (p5 | p6) + (p7 | p8)`
   - `N2 = (p2 | p3) + (p4 | p5) + (p6 | p7) + (p8 | p9)`
   - `N = min(N1, N2)`
   - `m = (p6 | p7 | !p9) & p8` in SUB-ITERATION 0, `m = (p2 | p3 | !p5) & p4` in
     SUB-ITERATION 1.
   The pixel is MARKED when `C == 1` and `2 <= N <= 3` and `m` is false.
3. A sub-iteration judges EVERY foreground pixel against the image as it was at the START
   of that sub-iteration, then removes all marked pixels at once. (Removing a pixel as soon
   as it is marked gives a different, wrong result.)
4. One ITERATION is sub-iteration 0 then sub-iteration 1. Repeat iterations until a whole
   iteration removes nothing; return the image.
5. Background pixels are never changed; nothing is ever added.

## Worked examples

`#` = foreground, `.` = background; rows top to bottom, separated by `/`.

| input | result |
|---|---|
| `... / .#. / ...` | unchanged (`C` is 0) |
| `## / ##` | `.# / ..` |
| `### / ### / ###` | `... / .#. / ...` |
| `##### / ##### / #####` | `..... / .###. / .....` |
| `#.. / #.. / ###` | `#.. / #.. / .##` (the corner goes; the line stays connected diagonally) |
| `##.... / .##... / ..##.. / ...##. / ....##` | `##.... / ..#... / ...#.. / ....#. / .....#` |
| `..##.. / ..##.. / ###### / ###### / ..##.. / ..##..` | `...#.. / ...#.. / .##### / ...... / ...... / ......` |
| `##### / ##### / ##.## / ##### / #####` | `..... / ..#.. / .#.#. / ..#.. / .....` (the ring stays a ring) |
| `##..# / ##... / .....` | `.#..# / ..... / .....` |
| 0 x 0 (empty slice) | empty |

Walk for `## / ##` (2 x 2): sub-iteration 0 judges all four pixels against the full square.
Top-left: `p4 = p5 = p6 = 1`, the rest 0: `C = 1`, `N1 = 2`, `N2 = 2`, `m = (1|0|1) & 0 = 0`
-> marked. Top-right: `p6 = p7 = p8 = 1`: `C = 1`, `N = 2`, `m = (1|1|1) & 1 = 1` -> kept.
Bottom-left (`p2 = p3 = p4 = 1`) and bottom-right (`p2 = p8 = p9 = 1`) are marked. Three are
removed at once; in the following sub-iterations the lone top-right pixel has `C = 0` and
stays.
