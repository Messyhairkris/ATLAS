# Contract: smooth.rs - simplify outlines and fit cubic Bezier curves

Module `src/smooth.rs` of the crate `photo_tools`. Turns a pixel-edge outline (from
contour.rs: integer points plus a junction flag per point) into smooth cubic Bezier
segments for SVG. Neighbouring colour regions trace their shared border in opposite
directions; the rules below make both sides produce EXACTLY the same curve, bit for bit,
so the SVG has no gaps or overlaps between colours.

## API (exact)

```rust
//! Outline simplification and cubic Bezier fitting that keeps shared borders
//! identical on both sides.

pub type Pt = (f64, f64);

/// One cubic Bezier segment.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Cubic {
    pub from: Pt,
    pub c1: Pt,
    pub c2: Pt,
    pub to: Pt,
}

/// Ramer-Douglas-Peucker on an open chain; the endpoints are always kept.
pub fn simplify(points: &[Pt], epsilon: f64) -> Vec<Pt>

/// simplify() run in the chain's canonical direction, returned in the given one.
pub fn simplify_canonical(chain: &[Pt], epsilon: f64) -> Vec<Pt>

/// The chains of a loop: junction to junction, or the whole loop closed on itself.
pub fn split_chains(points: &[(u32, u32)], junction: &[bool]) -> Vec<Vec<Pt>>

/// The whole loop as cubic segments, in loop order.
pub fn smooth_loop(points: &[(u32, u32)], junction: &[bool], epsilon: f64) -> Vec<Cubic>
```

Imports allowed: std only. "Smaller by (y, x)" means compare `y` first, then `x`.

## Rules

### simplify (Ramer-Douglas-Peucker)

1. Fewer than 3 points: return them unchanged.
2. `first = points[0]`, `last = points[n-1]`. For each INTERIOR point `p` (index 1 to
   n-2) compute its distance:
   - if `first == last`: `sqrt(dx*dx + dy*dy)` with `(dx, dy) = p - first`;
   - else: `|lx*dy - ly*dx| / sqrt(lx*lx + ly*ly)` with `(lx, ly) = last - first` and
     `(dx, dy) = p - first`.
   Take the point with the LARGEST distance; ties -> the smallest index.
3. If that distance is `> epsilon` (strictly), keep it: the result is
   `simplify(points[..=i])` followed by `simplify(points[i..])` without repeating
   `points[i]`. Otherwise the result is `[first, last]`.

### simplify_canonical

4. Fewer than 3 points: return them unchanged.
5. Decide whether to REVERSE: if `chain[0] != chain[n-1]`, reverse when `chain[n-1]` is
   smaller by (y, x) than `chain[0]`. If they are equal (a closed chain), reverse when
   `chain[n-2]` is smaller by (y, x) than `chain[1]`.
6. If reversing: reverse the chain, `simplify` it, reverse the result back. Otherwise just
   `simplify` it.

### split_chains

7. Convert points to `f64`. If NO point is a junction: return one chain, the whole loop
   closed back on its start: `[p0, p1, ..., p(n-1), p0]`.
8. Otherwise, for each junction index `j_k` in increasing order, a chain runs from
   `j_k` to the NEXT junction `j_(k+1)` inclusive, walking forward; the last chain wraps
   past the end of the list back to the first junction. A loop with exactly one junction
   gives one chain from it all the way round back to it.

### smooth_loop

9. Fewer than 2 points: return no segments.
10. For each chain from rule 7/8, in order: `q = simplify_canonical(chain, epsilon)`, then
    turn `q` into `m = q.len() - 1` segments, segment `i` from `q[i]` (a) to `q[i+1]` (b):
    - If `epsilon == 0.0` (straight lines): `c1 = a + (b - a) / 3`, `c2 = b - (b - a) / 3`
      (per coordinate; compute `(b - a)` once as `(dx, dy)`).
    - Otherwise (Catmull-Rom): `c1 = a + (b - p0) / 6`, `c2 = b - (p3 - a) / 6` where
      - `p0 = q[i-1]` if `i > 0`; else, for a CLOSED loop (no junctions, rule 7) with
        `q.len() > 2`, `p0 = q[m-1]`; else `p0 = a`.
      - `p3 = q[i+2]` if `i + 1 < m`; else, for a closed loop with `q.len() > 2`,
        `p3 = q[1]`; else `p3 = b`.
11. Output all segments of all chains in chain order.

Write the arithmetic exactly in the forms above (`a.0 + (b.0 - p0.0) / 6.0`,
`b.0 - (p3.0 - a.0) / 6.0`): the bit-for-bit match between the two sides of a border
relies on it.

## Worked examples

| call | result |
|---|---|
| `simplify(&[(0,0), (1,0.1), (2,0)], 0.5)` | `[(0,0), (2,0)]` |
| `simplify(&[(0,0), (1,0.1), (2,0)], 0.05)` | all three |
| `simplify(&[(0,0), (1,1), (3,-1), (4,0)], 1.0)` | `[(0,0), (4,0)]` (distance 1 is not > 1) |
| `simplify(&[(0,0), (1,1), (3,-1), (4,0)], 0.99)` | all four ((1,1) wins the tie; then (3,-1) is 1.265 from (1,1)-(4,0)) |
| `simplify(&[(0,0), (1,0), (2,3), (3,0), (4,0.2), (5,0)], 0.5)` | `[(0,0), (1,0), (2,3), (3,0), (5,0)]` |
| `simplify(&[(0,0), (2,0), (2,2), (0,2), (0,0)], 0.5)` | all five (closed: distances from (0,0)) |
| `simplify(&[(0,0), (2,0), (2,2), (0,2), (0,0)], 3.0)` | `[(0,0), (0,0)]` |

(All coordinates above are `f64`.)

`split_chains(&[(0,0), (2,0), (2,1), (0,1)], &[false; 4])` =
`[[(0,0), (2,0), (2,1), (0,1), (0,0)]]`.

`split_chains(&[(0,0), (2,0), (2,1), (1,1), (0,1)], &[F, F, T, T, T])` =
`[[(2,1), (1,1)], [(1,1), (0,1)], [(0,1), (0,0), (2,0), (2,1)]]`.
With only index 2 a junction: `[[(2,1), (1,1), (0,1), (0,0), (2,0), (2,1)]]`.

`smooth_loop(&[(0,0), (1,0), (1,1), (0,1)], &[false; 4], 0.0)`: 4 straight segments; the
first is `from (0,0), c1 (1/3, 0), c2 (2/3, 0), to (1,0)`; the last ends at (0,0).

Same square with epsilon 0.5 (closed, Catmull-Rom; q = all five points, m = 4):
segment 0 has a = (0,0), b = (1,0), p0 = q[3] = (0,1), p3 = q[2] = (1,1), so
`c1 = (1/6, -1/6)`, `c2 = (5/6, -1/6)`. Segment 2 (a = (1,1), b = (0,1), p0 = (1,0),
p3 = (0,0)) has `c1 = (5/6, 7/6)`.

`smooth_loop(&[(0,0), (2,0), (2,1), (1,1), (0,1)], &[F, F, T, T, T], 0.5)` gives 5
segments. Segment 0 (chain `[(2,1), (1,1)]`, clamped both ends): `from (2,1)`,
`c1 = (2 - 1/6, 1)`, `c2 = (1 + 1/6, 1)`. Segment 2 starts the chain
`(0,1) (0,0) (2,0) (2,1)` (RDP keeps all four): `from (0,1)`, `c1 = (0, 1 - 1/6)`,
`c2 = (0 - 2/6, 1/6)` (p0 clamped to a, p3 = (2,0)). The last segment ends at (2,1).
