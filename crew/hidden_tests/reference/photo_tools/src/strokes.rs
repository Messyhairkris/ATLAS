//! One-pixel lines to pixel chains (centerline tracing). Reference for the strokes.rs
//! contract.

/// Direction order: E, SE, S, SW, W, NW, N, NE.
const DIRS: [(i64, i64); 8] = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)];

fn at(fg: &[bool], w: usize, h: usize, x: i64, y: i64) -> bool {
    x >= 0 && y >= 0 && (x as usize) < w && (y as usize) < h && fg[y as usize * w + x as usize]
}

/// The direction indexes (into DIRS) of the m-neighbours of foreground pixel (x, y).
pub fn neighbours(fg: &[bool], width: usize, height: usize, x: usize, y: usize) -> Vec<usize> {
    let (x, y) = (x as i64, y as i64);
    let mut out = Vec::new();
    for (k, &(dx, dy)) in DIRS.iter().enumerate() {
        if !at(fg, width, height, x + dx, y + dy) {
            continue;
        }
        // A diagonal step counts only when neither pixel beside it is foreground.
        if dx != 0 && dy != 0
            && (at(fg, width, height, x + dx, y) || at(fg, width, height, x, y + dy))
        {
            continue;
        }
        out.push(k);
    }
    out
}

/// Every foreground pixel in chains of (x, y). A chain runs node to node (a node is a
/// pixel with other than two neighbours), or round a closed loop that has no node,
/// in which case its first pixel is repeated at the end. A pixel with no neighbours
/// is a chain of one.
pub fn trace(fg: &[bool], width: usize, height: usize) -> Vec<Vec<(u32, u32)>> {
    let n = width * height;
    let mut nbrs: Vec<Vec<usize>> = vec![Vec::new(); n];
    for i in 0..n {
        if fg[i] {
            nbrs[i] = neighbours(fg, width, height, i % width, i / width);
        }
    }
    let mut used = vec![0u8; n];
    let step = |i: usize, k: usize| -> usize {
        let (x, y) = ((i % width) as i64 + DIRS[k].0, (i / width) as i64 + DIRS[k].1);
        y as usize * width + x as usize
    };
    let opposite = |k: usize| (k + 4) % 8;
    let xy = |i: usize| ((i % width) as u32, (i / width) as u32);
    let is_node = |i: usize| nbrs[i].len() != 2;
    let mut chains = Vec::new();

    let walk = |start: usize, k0: usize, used: &mut Vec<u8>, stop: &dyn Fn(usize) -> bool| {
        let mut chain = vec![xy(start)];
        let (mut cur, mut k) = (start, k0);
        loop {
            let next = step(cur, k);
            used[cur] |= 1 << k;
            used[next] |= 1 << opposite(k);
            chain.push(xy(next));
            if stop(next) {
                break;
            }
            match nbrs[next].iter().copied().find(|&d| used[next] & (1 << d) == 0) {
                Some(d) => {
                    cur = next;
                    k = d;
                }
                None => break,
            }
        }
        chain
    };

    for i in 0..n {
        if !fg[i] || !is_node(i) {
            continue;
        }
        if nbrs[i].is_empty() {
            chains.push(vec![xy(i)]);
            continue;
        }
        for &k in &nbrs[i] {
            if used[i] & (1 << k) == 0 {
                chains.push(walk(i, k, &mut used, &|j| is_node(j)));
            }
        }
    }
    for i in 0..n {
        if !fg[i] || is_node(i) {
            continue;
        }
        if let Some(&k) = nbrs[i].iter().find(|&&k| used[i] & (1 << k) == 0) {
            chains.push(walk(i, k, &mut used, &|j| j == i));
        }
    }
    chains
}
