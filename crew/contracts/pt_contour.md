# Contract: contour.rs - region outlines along pixel edges

Module `src/contour.rs` of the crate `photo_tools`. Given a label map (one palette index
per pixel), produce the closed outlines of every region, running along pixel EDGES (grid
lines), so neighbouring regions share exactly the same border. Later modules smooth these
outlines into SVG curves.

## API (exact)

```rust
//! Region outlines along pixel edges.

/// One closed outline of one label. `points[i]` is a grid vertex (x, y) with
/// 0 <= x <= width and 0 <= y <= height; the last point joins back to the first.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Loop {
    pub label: u8,
    pub points: Vec<(u32, u32)>,
    pub junction: Vec<bool>,
}

/// True where three or more values meet (outside counts as one value), or at a
/// checkerboard saddle of two labels with all four cells inside the image.
pub fn is_junction(labels: &[u8], width: usize, height: usize, x: usize, y: usize) -> bool

/// Every outline of every label, sorted by label, then by first point (y, x).
pub fn trace(labels: &[u8], width: usize, height: usize) -> Vec<Loop>
```

Imports allowed: std only.

`labels` is row-major: pixel `(px, py)` has label `labels[py * width + px]`.

## Geometry

Pixel `(px, py)` is the unit square with corners `(px, py)` and `(px+1, py+1)`. Vertices
are the grid points `(x, y)`, `0 <= x <= width`, `0 <= y <= height`. y grows DOWNWARD.
Around vertex `(x, y)` lie four cells: NW = `(x-1, y-1)`, NE = `(x, y-1)`,
SW = `(x-1, y)`, SE = `(x, y)`. A cell outside the image has the value OUTSIDE, which is
different from every label.

## Rules

1. JUNCTION. `is_junction(x, y)` is true if the four cells around the vertex hold 3 or
   more distinct values (OUTSIDE counts as a value), OR if all four cells are inside the
   image, `NW == SE`, `NE == SW` and `NW != NE` (a checkerboard saddle). Otherwise false.
2. BOUNDARY EDGES. For each pixel with label L, each side whose neighbouring cell across
   that side is not L (another label, or OUTSIDE) is one DIRECTED edge of label L:
   | side | from | to | direction |
   |---|---|---|---|
   | top (neighbour above) | `(px, py)` | `(px+1, py)` | east |
   | right (neighbour right) | `(px+1, py)` | `(px+1, py+1)` | south |
   | bottom (neighbour below) | `(px+1, py+1)` | `(px, py+1)` | west |
   | left (neighbour left) | `(px, py+1)` | `(px, py)` | north |
   The region is always on the RIGHT of the direction of travel (on screen): outer
   outlines run clockwise, holes counter-clockwise.
3. LINKING. A loop follows edges of ONE label: each edge ends where the next begins.
   At a vertex where two unused edges of that label leave (only happens at a saddle),
   take the one that turns RIGHT relative to the arriving direction (east -> south,
   south -> west, west -> north, north -> east). Never turn back. A loop ends when it
   comes back to its first edge. Every edge belongs to exactly one loop.
4. POINTS. A loop's points are the start vertices of its edges, in travel order, then
   DROP every vertex where the path goes straight through (arriving and leaving
   direction equal) UNLESS that vertex is a junction (rule 1). Corners and junctions
   stay. `junction[i] = is_junction(points[i])`.
5. START. Rotate each loop's points (and junction flags with them) so it starts at its
   smallest point by `(y, x)`, keeping the travel direction. If that point occurs twice,
   start at the occurrence whose following point is smaller by `(y, x)`.
6. ORDER. Sort the loops by label ascending, then by first point `(y, x)`, then by second
   point `(y, x)`.
7. An empty image (`width == 0` or `height == 0`) gives no loops.

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
