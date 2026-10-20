# Contract: edges.rs - boundary edges linked into closed paths

Module `src/edges.rs` of the crate `photo_tools`. Part 2 of 3 of the outline tracer
(junction.rs, edges.rs, contour.rs). Finds every pixel side that separates a region from
something else, as a DIRECTED edge, and links the edges of each label into closed paths.
No simplification here - every vertex the path passes is kept.

## API (exact)

```rust
//! Directed pixel-edge boundaries of each label, linked into closed paths.

/// One closed boundary path before simplification: every grid vertex it passes, in
/// travel order, and the direction of the edge leaving each vertex
/// (0 east, 1 south, 2 west, 3 north).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawLoop {
    pub label: u8,
    pub verts: Vec<(u32, u32)>,
    pub dirs: Vec<u8>,
}

/// Every boundary edge as (label, start vertex, direction), ordered by start vertex
/// index y * (width + 1) + x, then by direction.
pub fn boundary_edges(labels: &[u8], width: usize, height: usize) -> Vec<(u8, (u32, u32), u8)>

/// The edges linked into closed loops, in the order their first edge appears in
/// boundary_edges; at a vertex with a choice, turn right, else straight, else left.
pub fn raw_loops(labels: &[u8], width: usize, height: usize) -> Vec<RawLoop>
```

Imports allowed: std only. A good representation: one slot per possible edge, index
`vertex_index * 4 + direction` with `vertex_index = y * (width + 1) + x`, holding the
owning label (`Option<u8>`). Walking those slots in index order IS the required order.

## Geometry

`labels` is row-major: pixel `(px, py)` has label `labels[py * width + px]`. Pixel
`(px, py)` is the unit square with corners `(px, py)` and `(px+1, py+1)`; y grows
DOWNWARD. Vertices are `(x, y)` with `0 <= x <= width`, `0 <= y <= height`.
Directions: 0 = east (+x), 1 = south (+y), 2 = west (-x), 3 = north (-y).

## Rules

1. EDGES. For each pixel with label L, each side whose neighbouring cell across that side
   is not L (another label, or outside the image) is one directed edge owned by L:

   | side | neighbour checked | from | to | direction |
   |---|---|---|---|---|
   | top | `(px, py-1)` | `(px, py)` | `(px+1, py)` | 0 east |
   | right | `(px+1, py)` | `(px+1, py)` | `(px+1, py+1)` | 1 south |
   | bottom | `(px, py+1)` | `(px+1, py+1)` | `(px, py+1)` | 2 west |
   | left | `(px-1, py)` | `(px, py+1)` | `(px, py)` | 3 north |

   The region is always on the RIGHT of the direction of travel (on screen). No two
   pixels ever produce the same (start vertex, direction).
2. ORDER. `boundary_edges` lists `(label, from, direction)` sorted by
   `from.1 * (width + 1) + from.0`, then by direction 0..3.
3. LINKING. `raw_loops`: take the first edge (rule-2 order) not yet used; it starts a new
   loop. Repeatedly: mark the current edge used, push its start vertex to `verts` and its
   direction to `dirs`, and move to its end vertex. There, among the UNUSED edges of the
   SAME label that start at that vertex, take the first that exists in this order:
   turn RIGHT (`(d + 1) % 4`), go STRAIGHT (`d`), turn LEFT (`(d + 3) % 4`). Never turn
   back. When none exists the loop is closed (you are back at its first edge). Then
   continue with the next unused edge in rule-2 order.
4. Loops are returned in the order they were started. Every edge is in exactly one loop.
   An empty image gives no edges and no loops.

## Worked examples

`boundary_edges(&[3], 1, 1)` = `[(3, (0,0), 0), (3, (1,0), 1), (3, (0,1), 3), (3, (1,1), 2)]`
(vertex indices with width + 1 = 2: (0,0) = 0, (1,0) = 1, (0,1) = 2, (1,1) = 3).

`boundary_edges(&[0, 1], 2, 1)` =
`[(0,(0,0),0), (1,(1,0),0), (0,(1,0),1), (1,(2,0),1), (0,(0,1),3), (0,(1,1),2), (1,(1,1),3), (1,(2,1),2)]`
- at vertex (1,0) label 1 leaves east (direction 0) and label 0 leaves south (1): sorted
by direction.

`raw_loops(&[0, 0], 2, 1)` =
`[RawLoop { label: 0, verts: [(0,0), (1,0), (2,0), (2,1), (1,1), (0,1)], dirs: [0, 0, 1, 2, 2, 3] }]`

`raw_loops(&[0, 1], 2, 1)` =
```
RawLoop { label: 0, verts: [(0,0), (1,0), (1,1), (0,1)], dirs: [0, 1, 2, 3] }
RawLoop { label: 1, verts: [(1,0), (2,0), (2,1), (1,1)], dirs: [0, 1, 2, 3] }
```

Hole - `raw_loops(&[0,0,0, 0,1,0, 0,0,0], 3, 3)`:
```
RawLoop { label: 0, verts: [(0,0),(1,0),(2,0),(3,0),(3,1),(3,2),(3,3),(2,3),(1,3),(0,3),(0,2),(0,1)],
          dirs: [0,0,0,1,1,1,2,2,2,3,3,3] }
RawLoop { label: 1, verts: [(1,1),(2,1),(2,2),(1,2)], dirs: [0,1,2,3] }
RawLoop { label: 0, verts: [(1,1),(1,2),(2,2),(2,1)], dirs: [1,0,3,2] }
```
At vertex (1,1) label 1 leaves east (0) and label 0 leaves south (1), so the label-1 loop
starts first. The hole loop then goes south, and at (1,2) right (west) and straight
(south) do not exist, so it turns left (east).

Saddle - `raw_loops(&[0,1, 1,0], 2, 2)`:
```
RawLoop { label: 0, verts: [(0,0),(1,0),(1,1),(0,1)], dirs: [0,1,2,3] }
RawLoop { label: 1, verts: [(1,0),(2,0),(2,1),(1,1)], dirs: [0,1,2,3] }
RawLoop { label: 1, verts: [(0,1),(1,1),(1,2),(0,2)], dirs: [0,1,2,3] }
RawLoop { label: 0, verts: [(1,1),(2,1),(2,2),(1,2)], dirs: [0,1,2,3] }
```
The first loop arrives at (1,1) heading south; both west (pixel (0,0)'s bottom) and east
(pixel (1,1)'s top) are unused label-0 edges there; RIGHT of south is west, so it takes
west and the two diagonal 0-pixels stay in separate loops.

L-shape - `raw_loops(&[1,1, 1,0], 2, 2)`:
```
RawLoop { label: 1, verts: [(0,0),(1,0),(2,0),(2,1),(1,1),(1,2),(0,2),(0,1)], dirs: [0,0,1,2,1,2,3,3] }
RawLoop { label: 0, verts: [(1,1),(2,1),(2,2),(1,2)], dirs: [0,1,2,3] }
```
(at (1,1), heading west: right (north) and straight (west) do not exist; left is south.)
