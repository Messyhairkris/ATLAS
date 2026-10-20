//! Directed pixel-edge boundaries of each label, linked into closed paths.
//! Reference for the edges.rs contract.

/// One closed boundary path before simplification: every grid vertex it passes, in
/// travel order, and the direction of the edge leaving each vertex
/// (0 east, 1 south, 2 west, 3 north).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawLoop {
    pub label: u8,
    pub verts: Vec<(u32, u32)>,
    pub dirs: Vec<u8>,
}

const STEP: [(i64, i64); 4] = [(1, 0), (0, 1), (-1, 0), (0, -1)];

fn cell(labels: &[u8], width: usize, height: usize, x: i64, y: i64) -> Option<u8> {
    if x < 0 || y < 0 || x >= width as i64 || y >= height as i64 {
        None
    } else {
        Some(labels[y as usize * width + x as usize])
    }
}

/// Owner label of every directed edge, indexed by vertex index * 4 + direction.
fn owners(labels: &[u8], width: usize, height: usize) -> Vec<Option<u8>> {
    let vw = width + 1;
    let mut owner = vec![None; (width + 1) * (height + 1) * 4];
    for py in 0..height {
        for px in 0..width {
            let l = labels[py * width + px];
            let (x, y) = (px as i64, py as i64);
            let sides = [
                (cell(labels, width, height, x, y - 1), (px, py), 0),
                (cell(labels, width, height, x + 1, y), (px + 1, py), 1),
                (cell(labels, width, height, x, y + 1), (px + 1, py + 1), 2),
                (cell(labels, width, height, x - 1, y), (px, py + 1), 3),
            ];
            for (other, (vx, vy), d) in sides {
                if other != Some(l) {
                    owner[(vy * vw + vx) * 4 + d] = Some(l);
                }
            }
        }
    }
    owner
}

/// Every boundary edge as (label, start vertex, direction), ordered by start vertex
/// index y * (width + 1) + x, then by direction.
pub fn boundary_edges(labels: &[u8], width: usize, height: usize) -> Vec<(u8, (u32, u32), u8)> {
    let vw = width + 1;
    owners(labels, width, height)
        .iter()
        .enumerate()
        .filter_map(|(e, o)| {
            o.map(|l| (l, (((e / 4) % vw) as u32, ((e / 4) / vw) as u32), (e % 4) as u8))
        })
        .collect()
}

/// The edges linked into closed loops, in the order their first edge appears in
/// boundary_edges; at a vertex with a choice, turn right, else straight, else left.
pub fn raw_loops(labels: &[u8], width: usize, height: usize) -> Vec<RawLoop> {
    let vw = width + 1;
    let owner = owners(labels, width, height);
    let mut used = vec![false; owner.len()];
    let mut loops = Vec::new();
    for start in 0..owner.len() {
        let Some(label) = owner[start] else { continue };
        if used[start] {
            continue;
        }
        let (mut verts, mut dirs) = (Vec::new(), Vec::new());
        let mut e = start;
        loop {
            used[e] = true;
            let (v, d) = (e / 4, e % 4);
            let (vx, vy) = (v % vw, v / vw);
            verts.push((vx as u32, vy as u32));
            dirs.push(d as u8);
            let nx = (vx as i64 + STEP[d].0) as usize;
            let ny = (vy as i64 + STEP[d].1) as usize;
            let nv = ny * vw + nx;
            let next = [(d + 1) % 4, d, (d + 3) % 4]
                .into_iter()
                .map(|nd| nv * 4 + nd)
                .find(|&ne| owner[ne] == Some(label) && !used[ne]);
            match next {
                Some(ne) => e = ne,
                None => break,
            }
        }
        loops.push(RawLoop { label, verts, dirs });
    }
    loops
}
