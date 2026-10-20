//! Region outlines along pixel edges. Reference for the contour.rs contract.

/// One closed outline of one label. `points[i]` is a grid vertex (x, y) with
/// 0 <= x <= width and 0 <= y <= height; the last point joins back to the first.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Loop {
    pub label: u8,
    pub points: Vec<(u32, u32)>,
    pub junction: Vec<bool>,
}

const OUTSIDE: i32 = -1;

fn cell(labels: &[u8], width: usize, height: usize, x: i64, y: i64) -> i32 {
    if x < 0 || y < 0 || x >= width as i64 || y >= height as i64 {
        OUTSIDE
    } else {
        labels[y as usize * width + x as usize] as i32
    }
}

/// True where three or more values meet (outside counts as one value), or at a
/// checkerboard saddle of two labels with all four cells inside the image.
pub fn is_junction(labels: &[u8], width: usize, height: usize, x: usize, y: usize) -> bool {
    let (x, y) = (x as i64, y as i64);
    let nw = cell(labels, width, height, x - 1, y - 1);
    let ne = cell(labels, width, height, x, y - 1);
    let sw = cell(labels, width, height, x - 1, y);
    let se = cell(labels, width, height, x, y);
    let mut vals = vec![nw, ne, sw, se];
    vals.sort_unstable();
    vals.dedup();
    if vals.len() >= 3 {
        return true;
    }
    vals.len() == 2 && !vals.contains(&OUTSIDE) && nw == se && ne == sw
}

// Directions: 0 east, 1 south, 2 west, 3 north.
const STEP: [(i64, i64); 4] = [(1, 0), (0, 1), (-1, 0), (0, -1)];

/// Every outline of every label, sorted by label, then by first point (y, x).
pub fn trace(labels: &[u8], width: usize, height: usize) -> Vec<Loop> {
    let vw = width + 1;
    // out[v * 4 + d] = there is an unused edge of `label` leaving vertex v in direction d.
    let mut used = vec![false; (width + 1) * (height + 1) * 4];
    let mut owner = vec![-1i32; (width + 1) * (height + 1) * 4];
    for py in 0..height {
        for px in 0..width {
            let l = labels[py * width + px] as i32;
            let (x, y) = (px as i64, py as i64);
            let sides = [
                (cell(labels, width, height, x, y - 1), (px, py), 0),
                (cell(labels, width, height, x + 1, y), (px + 1, py), 1),
                (cell(labels, width, height, x, y + 1), (px + 1, py + 1), 2),
                (cell(labels, width, height, x - 1, y), (px, py + 1), 3),
            ];
            for (other, (vx, vy), d) in sides {
                if other != l {
                    owner[(vy * vw + vx) * 4 + d] = l;
                }
            }
        }
    }
    let mut loops = Vec::new();
    for start in 0..owner.len() {
        if owner[start] < 0 || used[start] {
            continue;
        }
        let label = owner[start];
        let mut verts: Vec<(usize, usize)> = Vec::new();
        let mut dirs: Vec<usize> = Vec::new();
        let mut e = start;
        loop {
            used[e] = true;
            let (v, d) = (e / 4, e % 4);
            let (vx, vy) = (v % vw, v / vw);
            verts.push((vx, vy));
            dirs.push(d);
            let nx = (vx as i64 + STEP[d].0) as usize;
            let ny = (vy as i64 + STEP[d].1) as usize;
            let nv = ny * vw + nx;
            // Right turn first, then straight, then left.
            let mut next = None;
            for nd in [(d + 1) % 4, d, (d + 3) % 4] {
                let ne = nv * 4 + nd;
                if owner[ne] == label && !used[ne] {
                    next = Some(ne);
                    break;
                }
            }
            match next {
                Some(ne) => e = ne,
                None => break,
            }
        }
        let n = verts.len();
        let mut points = Vec::new();
        let mut junction = Vec::new();
        for i in 0..n {
            let prev = dirs[(i + n - 1) % n];
            let (x, y) = verts[i];
            let j = is_junction(labels, width, height, x, y);
            if prev != dirs[i] || j {
                points.push((x as u32, y as u32));
                junction.push(j);
            }
        }
        let m = points.len();
        let mut best = 0;
        for i in 1..m {
            let key = |k: usize| (points[k].1, points[k].0);
            let next_key = |k: usize| (points[(k + 1) % m].1, points[(k + 1) % m].0);
            if key(i) < key(best) || (key(i) == key(best) && next_key(i) < next_key(best)) {
                best = i;
            }
        }
        points.rotate_left(best);
        junction.rotate_left(best);
        loops.push(Loop { label: label as u8, points, junction });
    }
    loops.sort_by_key(|l| (l.label, l.points[0].1, l.points[0].0, l.points[1].1, l.points[1].0));
    loops
}
