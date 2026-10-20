//! Outline simplification and cubic Bezier fitting that keeps shared borders
//! identical on both sides. Reference for the smooth.rs contract.

pub type Pt = (f64, f64);

/// One cubic Bezier segment.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Cubic {
    pub from: Pt,
    pub c1: Pt,
    pub c2: Pt,
    pub to: Pt,
}

fn less(a: Pt, b: Pt) -> bool {
    (a.1, a.0) < (b.1, b.0)
}

fn distance(p: Pt, first: Pt, last: Pt) -> f64 {
    let (lx, ly) = (last.0 - first.0, last.1 - first.1);
    let (dx, dy) = (p.0 - first.0, p.1 - first.1);
    if lx == 0.0 && ly == 0.0 {
        (dx * dx + dy * dy).sqrt()
    } else {
        (lx * dy - ly * dx).abs() / (lx * lx + ly * ly).sqrt()
    }
}

/// Ramer-Douglas-Peucker on an open chain; the endpoints are always kept.
pub fn simplify(points: &[Pt], epsilon: f64) -> Vec<Pt> {
    let n = points.len();
    if n <= 2 {
        return points.to_vec();
    }
    let (first, last) = (points[0], points[n - 1]);
    let mut best = 1;
    let mut best_d = distance(points[1], first, last);
    for (i, &p) in points.iter().enumerate().take(n - 1).skip(2) {
        let d = distance(p, first, last);
        if d > best_d {
            best = i;
            best_d = d;
        }
    }
    if best_d > epsilon {
        let mut left = simplify(&points[..=best], epsilon);
        let right = simplify(&points[best..], epsilon);
        left.pop();
        left.extend(right);
        left
    } else {
        vec![first, last]
    }
}

/// simplify() run in the chain's canonical direction, returned in the given one.
pub fn simplify_canonical(chain: &[Pt], epsilon: f64) -> Vec<Pt> {
    let n = chain.len();
    if n <= 2 {
        return chain.to_vec();
    }
    let reversed = if chain[0] != chain[n - 1] {
        less(chain[n - 1], chain[0])
    } else {
        less(chain[n - 2], chain[1])
    };
    if reversed {
        let mut rev: Vec<Pt> = chain.iter().rev().copied().collect();
        rev = simplify(&rev, epsilon);
        rev.reverse();
        rev
    } else {
        simplify(chain, epsilon)
    }
}

/// The chains of a loop: junction to junction, or the whole loop closed on itself.
pub fn split_chains(points: &[(u32, u32)], junction: &[bool]) -> Vec<Vec<Pt>> {
    let n = points.len();
    let pt = |i: usize| (points[i % n].0 as f64, points[i % n].1 as f64);
    let js: Vec<usize> = (0..n).filter(|&i| junction[i]).collect();
    if js.is_empty() {
        return vec![(0..=n).map(pt).collect()];
    }
    let mut out = Vec::new();
    for (k, &a) in js.iter().enumerate() {
        let b = if k + 1 < js.len() { js[k + 1] } else { js[0] + n };
        out.push((a..=b).map(pt).collect());
    }
    out
}

fn cubics(q: &[Pt], epsilon: f64, closed: bool) -> Vec<Cubic> {
    let m = q.len() - 1;
    let mut out = Vec::with_capacity(m);
    for i in 0..m {
        let (a, b) = (q[i], q[i + 1]);
        let (c1, c2) = if epsilon == 0.0 {
            let (dx, dy) = (b.0 - a.0, b.1 - a.1);
            ((a.0 + dx / 3.0, a.1 + dy / 3.0), (b.0 - dx / 3.0, b.1 - dy / 3.0))
        } else {
            let p0 = if i > 0 { q[i - 1] } else if closed { q[m - 1] } else { a };
            let p3 = if i + 1 < m { q[i + 2] } else if closed { q[1] } else { b };
            (
                (a.0 + (b.0 - p0.0) / 6.0, a.1 + (b.1 - p0.1) / 6.0),
                (b.0 - (p3.0 - a.0) / 6.0, b.1 - (p3.1 - a.1) / 6.0),
            )
        };
        out.push(Cubic { from: a, c1, c2, to: b });
    }
    out
}

/// The whole loop as cubic segments, in loop order.
pub fn smooth_loop(points: &[(u32, u32)], junction: &[bool], epsilon: f64) -> Vec<Cubic> {
    if points.len() < 2 {
        return Vec::new();
    }
    let closed = !junction.iter().any(|&j| j);
    let mut out = Vec::new();
    for chain in split_chains(points, junction) {
        let q = simplify_canonical(&chain, epsilon);
        out.extend(cubics(&q, epsilon, closed && q.len() > 2));
    }
    out
}
