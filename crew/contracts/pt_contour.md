# Contract: contour.rs - region outlines along pixel edges

Module `src/contour.rs` of the crate `photo_tools`. Part 3 of 3 of the outline tracer:
it ASSEMBLES the outlines from the two accepted parts - `crate::junction` (is a vertex a
junction?) and `crate::edges` (boundary edges linked into raw closed paths) - by dropping
straight-through points, rotating each loop to a fixed start, and sorting. The source of
both accepted modules is shown below the contract. Later modules smooth these outlines
into SVG curves.

## API (exact)

```rust
//! Region outlines along pixel edges.

use crate::edges::raw_loops;
pub use crate::junction::is_junction;

/// One closed outline of one label. `points[i]` is a grid vertex (x, y) with
/// 0 <= x <= width and 0 <= y <= height; the last point joins back to the first.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Loop {
    pub label: u8,
    pub points: Vec<(u32, u32)>,
    pub junction: Vec<bool>,
}

/// Every outline of every label, sorted by label, then by first point (y, x).
pub fn trace(labels: &[u8], width: usize, height: usize) -> Vec<Loop>
```

The `pub use` line re-exports `is_junction`, so callers may keep writing
`photo_tools::contour::is_junction`. Do not re-implement it, and do not re-implement
edge finding or linking: call `raw_loops`.

Imports allowed: exactly the two `use` lines above (std prelude otherwise).

From the accepted modules:

```rust
pub struct RawLoop { pub label: u8, pub verts: Vec<(u32, u32)>, pub dirs: Vec<u8> }
// verts[i] = the i-th vertex of the closed path; dirs[i] = direction of the edge
// LEAVING verts[i] (0 east, 1 south, 2 west, 3 north). The edge ARRIVING at verts[i]
// is dirs[(i + n - 1) % n].
pub fn raw_loops(labels: &[u8], width: usize, height: usize) -> Vec<RawLoop>
pub fn is_junction(labels: &[u8], width: usize, height: usize, x: usize, y: usize) -> bool
```

## Rules

1. `trace` calls `raw_loops(labels, width, height)` and turns each `RawLoop` into a `Loop`
   with the same label.
2. POINTS. For each index `i` of the raw loop (n = its length): the vertex is
   `verts[i]`; it is a junction if `is_junction(labels, width, height, x, y)`. KEEP it
   when the arriving direction `dirs[(i + n - 1) % n]` differs from the leaving direction
   `dirs[i]` (a corner) OR it is a junction; otherwise DROP it (straight through). Kept
   vertices go to `points` in order, with their junction flag in `junction` (same index).
3. START. Rotate `points` and `junction` together (e.g. `rotate_left(k)` on both) so the
   loop starts at its smallest point by `(y, x)` - compare y first, then x. If that
   smallest point occurs twice, start at the occurrence whose FOLLOWING point (the next
   one, wrapping round) is smaller by `(y, x)`.
4. ORDER. Sort the loops by label ascending, then by first point `(y, x)`, then by
   second point `(y, x)`.
5. An empty image gives no loops (raw_loops returns none).
## Worked examples (T = true, F = false)

`trace(&[3], 1, 1)`:
`[Loop { label: 3, points: [(0,0), (1,0), (1,1), (0,1)], junction: [F, F, F, F] }]`

`trace(&[0, 0], 2, 1)` - (1,0) and (1,1) are straight and not junctions, so dropped:
`[Loop { label: 0, points: [(0,0), (2,0), (2,1), (0,1)], junction: [F, F, F, F] }]`

`trace(&[0, 1], 2, 1)`:
```
Loop { label: 0, points: [(0,0), (1,0), (1,1), (0,1)], junction: [F, T, T, F] }
Loop { label: 1, points: [(1,0), (2,0), (2,1), (1,1)], junction: [T, F, F, T] }
```
(1,0) is a junction: its cells are OUTSIDE, OUTSIDE, 0, 1 - three values.

Hole - `trace(&[0,0,0, 0,1,0, 0,0,0], 3, 3)`:
```
Loop { label: 0, points: [(0,0), (3,0), (3,3), (0,3)], junction: [F, F, F, F] }  outer, clockwise
Loop { label: 0, points: [(1,1), (1,2), (2,2), (2,1)], junction: [F, F, F, F] }  hole, counter-clockwise
Loop { label: 1, points: [(1,1), (2,1), (2,2), (1,2)], junction: [F, F, F, F] }
```

Saddle - `trace(&[0,1, 1,0], 2, 2)`; vertex (1,1) is a saddle junction, and rule 3 keeps
the two 0-pixels (and the two 1-pixels) in separate loops:
```
Loop { label: 0, points: [(0,0), (1,0), (1,1), (0,1)], junction: [F, T, T, T] }
Loop { label: 0, points: [(1,1), (2,1), (2,2), (1,2)], junction: [T, T, F, T] }
Loop { label: 1, points: [(1,0), (2,0), (2,1), (1,1)], junction: [T, F, T, T] }
Loop { label: 1, points: [(0,1), (1,1), (1,2), (0,2)], junction: [T, T, T, F] }
```
At (1,1) the first loop arrives heading south (down the right side of pixel (0,0)); its
right turn is west, along the bottom of pixel (0,0) - not east into pixel (1,1).

Junction inside a straight run - `trace(&[0,0, 1,2], 2, 2)`: the bottom of the 0-region
runs straight through (1,1), but three labels meet there, so it stays:
```
Loop { label: 0, points: [(0,0), (2,0), (2,1), (1,1), (0,1)], junction: [F, F, T, T, T] }
Loop { label: 1, points: [(0,1), (1,1), (1,2), (0,2)], junction: [T, T, T, F] }
Loop { label: 2, points: [(1,1), (2,1), (2,2), (1,2)], junction: [T, T, F, T] }
```

L-shape - `trace(&[1,1, 1,0], 2, 2)`; (1,1) has only labels 0 and 1 around it and is not
a checkerboard, so it is a corner but not a junction:
```
Loop { label: 0, points: [(1,1), (2,1), (2,2), (1,2)], junction: [F, T, F, T] }
Loop { label: 1, points: [(0,0), (2,0), (2,1), (1,1), (1,2), (0,2)], junction: [F, F, T, F, T, F] }
```

`is_junction` alone, on `[0,1, 1,0]` (2x2): (0,0) false (OUTSIDE and 0); (1,0) true;
(1,1) true (saddle). On `[0,1, 0,1]`: (1,1) false (two labels, not a checkerboard).
On `[5]` (1x1): (1,1) false.