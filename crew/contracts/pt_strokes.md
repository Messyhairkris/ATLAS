# Contract: strokes.rs - one-pixel lines to pixel chains

Module `src/strokes.rs` of the crate `photo_tools`. After thinning, every line in the line
art is one pixel wide. This module follows those lines and returns them as chains of pixel
coordinates - one chain from an end or a fork to the next end or fork, or once round a
closed loop - so they can be written as SVG strokes down the middle of each line.

## API (exact)

```rust
//! One-pixel lines to pixel chains (centerline tracing).

/// The direction indexes (into E, SE, S, SW, W, NW, N, NE) of the m-neighbours of
/// foreground pixel (x, y).
pub fn neighbours(fg: &[bool], width: usize, height: usize, x: usize, y: usize) -> Vec<usize>

/// Every foreground pixel in chains of (x, y).
pub fn trace(fg: &[bool], width: usize, height: usize) -> Vec<Vec<(u32, u32)>>
```

Imports allowed: std only. `fg` is row-major (`fg[y * width + x]`),
`fg.len() == width * height`.

## Rules

1. DIRECTIONS, in this fixed order (index: step `(dx, dy)`, y grows downwards):
   `0 E (1,0)`, `1 SE (1,1)`, `2 S (0,1)`, `3 SW (-1,1)`, `4 W (-1,0)`, `5 NW (-1,-1)`,
   `6 N (0,-1)`, `7 NE (1,-1)`. Outside the image is background.
2. M-NEIGHBOURS (`neighbours`): walk the 8 directions in order and keep direction `k` when
   the pixel one step that way is foreground, EXCEPT a diagonal step `(dx, dy)` is dropped
   when either pixel beside it - `(x + dx, y)` or `(x, y + dy)` - is foreground (the two
   are already joined through that pixel). Return the kept direction indexes in order.
   This stops a staircase like `## / .##` from looking like a fork.
3. A pixel's DEGREE is its number of m-neighbours. A NODE is a foreground pixel whose
   degree is not 2 (a line end, a fork, or a lone pixel).
4. Every link between two m-neighbours is used at most once. Keep, per pixel, which of its
   8 directions are used; using a link marks it at BOTH ends (direction `k` at one end,
   `(k + 4) % 8` at the other).
5. WALK from pixel `s` in direction `k`: the chain starts `[s]`; repeat: step to the pixel
   `n` in direction `k`, mark that link used (rule 4), append `n`; stop if the STOP test
   holds for `n`; otherwise continue from `n` in the FIRST of `n`'s m-neighbour directions
   (in rule-1 order) that is not yet used; if none is left, stop.
6. PASS 1 - lines: visit the nodes in raster order (y, then x). A node with degree 0 is a
   chain of one pixel, `[(x, y)]`. Otherwise, for each of its m-neighbour directions in
   order whose link is not yet used, WALK from it, stopping at the first NODE reached;
   that walk is a chain.
7. PASS 2 - closed loops with no node: visit the non-node foreground pixels in raster
   order. For a pixel `p` that still has an unused link, WALK from `p` in its first unused
   direction, stopping when the walk is back at `p` (the chain starts and ends with `p`).
8. The result is every pass-1 chain in the order made, then every pass-2 chain.
   Coordinates are `(x as u32, y as u32)`. Every foreground pixel appears in at least one
   chain (a fork appears in each chain that ends there).

## Worked examples

`#` = foreground; rows top to bottom, separated by `/`.

| input | `trace` result |
|---|---|
| `####` | `[[(0,0),(1,0),(2,0),(3,0)]]` |
| `... / .#. / ...` | `[[(1,1)]]` |
| `#.# / ... / #..` | `[[(0,0)], [(2,0)], [(0,2)]]` |
| `##. / .## / ..#` | `[[(0,0),(1,0),(1,1),(2,1),(2,2)]]` (a staircase, not a fork) |
| `#.. / .#. / ..#` | `[[(0,0),(1,1),(2,2)]]` |
| `### / #.# / ###` | `[[(0,0),(1,0),(2,0),(2,1),(2,2),(1,2),(0,2),(0,1),(0,0)]]` (pass 2) |
| `## / ##` | `[[(0,0),(1,0),(1,1),(0,1),(0,0)]]` (four links, all degree 2) |
| `##### / ..#.. / ..#..` | `[[(0,0),(1,0),(2,0)], [(2,0),(3,0),(4,0)], [(2,0),(2,1),(2,2)]]` |
| `..#.. / ..#.. / ##### / ..#.. / ..#..` | `[[(2,0),(2,1),(2,2)], [(0,2),(1,2),(2,2)], [(2,2),(3,2),(4,2)], [(2,2),(2,3),(2,4)]]` |
| `#...# / .#.#. / ..#.. / .#.#. / #...#` | `[[(0,0),(1,1),(2,2)], [(4,0),(3,1),(2,2)], [(2,2),(3,3),(4,4)], [(2,2),(1,3),(0,4)]]` |
| `###.. / #.#.. / #####` | `[[(2,2),(3,2),(4,2)], [(2,2),(1,2),(0,2),(0,1),(0,0),(1,0),(2,0),(2,1),(2,2)]]` |
| empty image | `[]` |

`neighbours` examples: in `##. / .## / ..#`, pixel (1,0) -> `[2, 4]` (S and W; SE to (2,1)
is dropped because (1,1) is foreground). In `#.. / .#. / ..#`, pixel (1,1) -> `[1, 5]`.
In `### / ### / ###`, pixel (1,1) -> `[0, 2, 4, 6]`.

Walk for `###.. / #.#.. / #####`: degrees are all 2 except (2,2) (W, E and N: 3) and (4,2)
(1), so the nodes in raster order are (2,2), (4,2). From (2,2): E reaches node (4,2) ->
chain 1. W walks (1,2), (0,2), (0,1), (0,0), (1,0), (2,0), (2,1) and arrives back at the
node (2,2) -> chain 2 (that also uses the N link of (2,2)). N is used; (4,2)'s only link is
used. Pass 2 finds no unused link.
