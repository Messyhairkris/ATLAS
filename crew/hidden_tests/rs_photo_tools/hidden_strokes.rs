use photo_tools::strokes::{neighbours, trace};

type Chains = Vec<Vec<(u32, u32)>>;

fn grid(rows: &[&str]) -> (Vec<bool>, usize, usize) {
    let w = rows.first().map_or(0, |r| r.len());
    (rows.iter().flat_map(|r| r.chars().map(|c| c == '#')).collect(), w, rows.len())
}

fn traced(rows: &[&str]) -> Chains {
    let (b, w, h) = grid(rows);
    trace(&b, w, h)
}

const D: [(i64, i64); 8] = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)];

fn fgat(fg: &[bool], w: usize, h: usize, x: i64, y: i64) -> bool {
    x >= 0 && y >= 0 && (x as usize) < w && (y as usize) < h && fg[y as usize * w + x as usize]
}

/// The rules written out again, independently: the oracle for ordering.
fn oracle(fg: &[bool], w: usize, h: usize) -> Chains {
    let nb = |x: i64, y: i64| -> Vec<usize> {
        (0..8)
            .filter(|&k| {
                let (dx, dy) = D[k];
                fgat(fg, w, h, x + dx, y + dy)
                    && !(dx != 0 && dy != 0 && (fgat(fg, w, h, x + dx, y) || fgat(fg, w, h, x, y + dy)))
            })
            .collect()
    };
    let mut used = std::collections::HashSet::new();
    let link = |x: i64, y: i64, k: usize| {
        let (nx, ny) = (x + D[k].0, y + D[k].1);
        if (x, y) < (nx, ny) { (x, y, nx, ny) } else { (nx, ny, x, y) }
    };
    let walk = |sx: i64, sy: i64, k0: usize, used: &mut std::collections::HashSet<(i64, i64, i64, i64)>, closed: bool| {
        let mut chain = vec![(sx as u32, sy as u32)];
        let (mut x, mut y, mut k) = (sx, sy, k0);
        loop {
            used.insert(link(x, y, k));
            let (nx, ny) = (x + D[k].0, y + D[k].1);
            chain.push((nx as u32, ny as u32));
            let deg = nb(nx, ny).len();
            if (closed && (nx, ny) == (sx, sy)) || (!closed && deg != 2) {
                break;
            }
            match nb(nx, ny).into_iter().find(|&d| !used.contains(&link(nx, ny, d))) {
                Some(d) => {
                    x = nx;
                    y = ny;
                    k = d;
                }
                None => break,
            }
        }
        chain
    };
    let mut out = Vec::new();
    for y in 0..h as i64 {
        for x in 0..w as i64 {
            if !fgat(fg, w, h, x, y) || nb(x, y).len() == 2 {
                continue;
            }
            if nb(x, y).is_empty() {
                out.push(vec![(x as u32, y as u32)]);
            }
            for k in nb(x, y) {
                if !used.contains(&link(x, y, k)) {
                    out.push(walk(x, y, k, &mut used, false));
                }
            }
        }
    }
    for y in 0..h as i64 {
        for x in 0..w as i64 {
            if !fgat(fg, w, h, x, y) || nb(x, y).len() != 2 {
                continue;
            }
            if let Some(k) = nb(x, y).into_iter().find(|&k| !used.contains(&link(x, y, k))) {
                out.push(walk(x, y, k, &mut used, true));
            }
        }
    }
    out
}

fn random(seed: u64, w: usize, h: usize) -> Vec<bool> {
    let mut s = seed;
    let mut next = || {
        s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        (s >> 33) as usize
    };
    let mut img = vec![false; w * h];
    // random walks give lines, forks, loops and the odd thick patch
    for _ in 0..(2 + next() % 4) {
        let (mut x, mut y) = (next() % w, next() % h);
        for _ in 0..(5 + next() % 40) {
            img[y * w + x] = true;
            let (dx, dy) = D[next() % 8];
            x = (x as i64 + dx).clamp(0, w as i64 - 1) as usize;
            y = (y as i64 + dy).clamp(0, h as i64 - 1) as usize;
        }
    }
    for _ in 0..(next() % 4) {
        img[next() % (w * h)] = true;
    }
    img
}

#[test]
fn rule_6_straight_line() {
    assert_eq!(traced(&["####"]), vec![vec![(0, 0), (1, 0), (2, 0), (3, 0)]]);
}

#[test]
fn rule_6_lone_pixels() {
    assert_eq!(traced(&["...", ".#.", "..."]), vec![vec![(1, 1)]]);
    assert_eq!(traced(&["#.#", "...", "#.."]), vec![vec![(0, 0)], vec![(2, 0)], vec![(0, 2)]]);
}

#[test]
fn rule_2_staircase_is_not_a_fork() {
    assert_eq!(traced(&["##.", ".##", "..#"]), vec![vec![(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)]]);
}

#[test]
fn diagonal() {
    assert_eq!(traced(&["#..", ".#.", "..#"]), vec![vec![(0, 0), (1, 1), (2, 2)]]);
}

#[test]
fn rule_7_ring() {
    assert_eq!(
        traced(&["###", "#.#", "###"]),
        vec![vec![(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1), (0, 0)]]
    );
}

#[test]
fn rule_7_square_2x2() {
    assert_eq!(traced(&["##", "##"]), vec![vec![(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]]);
}

#[test]
fn rule_6_tee() {
    assert_eq!(
        traced(&["#####", "..#..", "..#.."]),
        vec![
            vec![(0, 0), (1, 0), (2, 0)],
            vec![(2, 0), (3, 0), (4, 0)],
            vec![(2, 0), (2, 1), (2, 2)],
        ]
    );
}

#[test]
fn rule_6_cross() {
    assert_eq!(
        traced(&["..#..", "..#..", "#####", "..#..", "..#.."]),
        vec![
            vec![(2, 0), (2, 1), (2, 2)],
            vec![(0, 2), (1, 2), (2, 2)],
            vec![(2, 2), (3, 2), (4, 2)],
            vec![(2, 2), (2, 3), (2, 4)],
        ]
    );
}

#[test]
fn rule_6_diagonal_cross() {
    assert_eq!(
        traced(&["#...#", ".#.#.", "..#..", ".#.#.", "#...#"]),
        vec![
            vec![(0, 0), (1, 1), (2, 2)],
            vec![(4, 0), (3, 1), (2, 2)],
            vec![(2, 2), (3, 3), (4, 4)],
            vec![(2, 2), (1, 3), (0, 4)],
        ]
    );
}

#[test]
fn rule_6_loop_with_a_tail() {
    assert_eq!(
        traced(&["###..", "#.#..", "#####"]),
        vec![
            vec![(2, 2), (3, 2), (4, 2)],
            vec![(2, 2), (1, 2), (0, 2), (0, 1), (0, 0), (1, 0), (2, 0), (2, 1), (2, 2)],
        ]
    );
}

#[test]
fn empty_image() {
    assert!(trace(&[], 0, 0).is_empty());
    assert!(trace(&[false; 4], 2, 2).is_empty());
}

#[test]
fn rule_2_neighbours() {
    let (b, w, h) = grid(&["##.", ".##", "..#"]);
    assert_eq!(neighbours(&b, w, h, 1, 0), vec![2, 4]);
    let (b, w, h) = grid(&["#..", ".#.", "..#"]);
    assert_eq!(neighbours(&b, w, h, 1, 1), vec![1, 5]);
    let (b, w, h) = grid(&["###", "###", "###"]);
    assert_eq!(neighbours(&b, w, h, 1, 1), vec![0, 2, 4, 6]);
    assert_eq!(neighbours(&b, w, h, 0, 0), vec![0, 2]);
    let (b, w, h) = grid(&["#.#", ".#.", "#.#"]);
    assert_eq!(neighbours(&b, w, h, 1, 1), vec![1, 3, 5, 7]);
    assert_eq!(neighbours(&b, w, h, 2, 2), vec![5]);
}

#[test]
fn random_patterns_follow_the_rules_exactly() {
    for seed in 1..60u64 {
        let (w, h) = (19, 13);
        let img = random(seed, w, h);
        assert_eq!(trace(&img, w, h), oracle(&img, w, h), "seed {seed}");
    }
}

#[test]
fn every_link_used_once_and_every_pixel_covered() {
    for seed in 100..140u64 {
        let (w, h) = (24, 16);
        let img = random(seed, w, h);
        let chains = trace(&img, w, h);
        let mut links = std::collections::HashMap::new();
        let mut covered = vec![false; w * h];
        for c in &chains {
            for p in c {
                covered[p.1 as usize * w + p.0 as usize] = true;
            }
            for pair in c.windows(2) {
                let (a, b) = (pair[0], pair[1]);
                let key = if a < b { (a, b) } else { (b, a) };
                *links.entry(key).or_insert(0) += 1;
            }
        }
        assert_eq!(covered, img, "seed {seed}: every foreground pixel, and only those");
        assert!(links.values().all(|&n| n == 1), "seed {seed}: a link used twice");
        let mut total = 0;
        for i in 0..w * h {
            if img[i] {
                total += neighbours(&img, w, h, i % w, i / w).len();
            }
        }
        assert_eq!(links.len() * 2, total, "seed {seed}: every m-link used");
    }
}
