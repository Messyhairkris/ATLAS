//! Region outlines along pixel edges. Reference for the contour.rs contract.

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

fn key(p: (u32, u32)) -> (u32, u32) {
    (p.1, p.0)
}

/// Every outline of every label, sorted by label, then by first point (y, x).
pub fn trace(labels: &[u8], width: usize, height: usize) -> Vec<Loop> {
    let mut loops = Vec::new();
    for raw in raw_loops(labels, width, height) {
        let n = raw.verts.len();
        let (mut points, mut junction) = (Vec::new(), Vec::new());
        for i in 0..n {
            let (x, y) = raw.verts[i];
            let j = is_junction(labels, width, height, x as usize, y as usize);
            if raw.dirs[(i + n - 1) % n] != raw.dirs[i] || j {
                points.push((x, y));
                junction.push(j);
            }
        }
        let m = points.len();
        let mut best = 0;
        for i in 1..m {
            let (a, b) = (key(points[i]), key(points[best]));
            if a < b || (a == b && key(points[(i + 1) % m]) < key(points[(best + 1) % m])) {
                best = i;
            }
        }
        points.rotate_left(best);
        junction.rotate_left(best);
        loops.push(Loop { label: raw.label, points, junction });
    }
    loops.sort_by_key(|l| (l.label, key(l.points[0]), key(l.points[1])));
    loops
}
