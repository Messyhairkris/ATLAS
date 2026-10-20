use photo_tools::thin::thin;

fn grid(rows: &[&str]) -> (Vec<bool>, usize, usize) {
    let w = rows.first().map_or(0, |r| r.len());
    (rows.iter().flat_map(|r| r.chars().map(|c| c == '#')).collect(), w, rows.len())
}

fn show(bits: &[bool], w: usize) -> String {
    bits.chunks(w)
        .map(|r| r.iter().map(|&b| if b { '#' } else { '.' }).collect::<String>())
        .collect::<Vec<_>>()
        .join(" / ")
}

fn check(rows: &[&str], want: &str) {
    let (b, w, h) = grid(rows);
    assert_eq!(show(&thin(&b, w, h), w), want, "input {}", show(&b, w));
}

/// Guo-Hall written straight from the formulas, judged on a snapshot per sub-iteration.
fn oracle(fg: &[bool], w: usize, h: usize) -> Vec<bool> {
    let at = |img: &Vec<bool>, x: i64, y: i64| -> u8 {
        (x >= 0 && y >= 0 && (x as usize) < w && (y as usize) < h && img[y as usize * w + x as usize]) as u8
    };
    let mut img = fg.to_vec();
    loop {
        let mut any = false;
        for sub in 0..2 {
            let snap = img.clone();
            for y in 0..h as i64 {
                for x in 0..w as i64 {
                    if at(&snap, x, y) == 0 {
                        continue;
                    }
                    let p2 = at(&snap, x, y - 1);
                    let p3 = at(&snap, x + 1, y - 1);
                    let p4 = at(&snap, x + 1, y);
                    let p5 = at(&snap, x + 1, y + 1);
                    let p6 = at(&snap, x, y + 1);
                    let p7 = at(&snap, x - 1, y + 1);
                    let p8 = at(&snap, x - 1, y);
                    let p9 = at(&snap, x - 1, y - 1);
                    let c = ((1 - p2) & (p3 | p4)) + ((1 - p4) & (p5 | p6)) + ((1 - p6) & (p7 | p8)) + ((1 - p8) & (p9 | p2));
                    let n1 = (p9 | p2) + (p3 | p4) + (p5 | p6) + (p7 | p8);
                    let n2 = (p2 | p3) + (p4 | p5) + (p6 | p7) + (p8 | p9);
                    let n = n1.min(n2);
                    let m = if sub == 0 { (p6 | p7 | (1 - p9)) & p8 } else { (p2 | p3 | (1 - p5)) & p4 };
                    if c == 1 && (2..=3).contains(&n) && m == 0 {
                        img[y as usize * w + x as usize] = false;
                        any = true;
                    }
                }
            }
        }
        if !any {
            return img;
        }
    }
}

fn components(img: &[bool], w: usize, h: usize) -> usize {
    let mut seen = vec![false; img.len()];
    let mut n = 0;
    for s in 0..img.len() {
        if !img[s] || seen[s] {
            continue;
        }
        n += 1;
        let mut st = vec![s];
        seen[s] = true;
        while let Some(i) = st.pop() {
            let (x, y) = ((i % w) as i64, (i / w) as i64);
            for dy in -1..=1 {
                for dx in -1..=1 {
                    let (nx, ny) = (x + dx, y + dy);
                    if nx >= 0 && ny >= 0 && (nx as usize) < w && (ny as usize) < h {
                        let j = ny as usize * w + nx as usize;
                        if img[j] && !seen[j] {
                            seen[j] = true;
                            st.push(j);
                        }
                    }
                }
            }
        }
    }
    n
}

fn blobs(seed: u64, w: usize, h: usize) -> Vec<bool> {
    let mut s = seed;
    let mut next = || {
        s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        (s >> 33) as usize
    };
    let mut img = vec![false; w * h];
    for _ in 0..(3 + next() % 5) {
        // a thick stroke between two random points
        let (x0, y0, x1, y1) = (next() % w, next() % h, next() % w, next() % h);
        let r = 1 + next() % 3;
        for t in 0..=40 {
            let x = x0 as f64 + (x1 as f64 - x0 as f64) * t as f64 / 40.0;
            let y = y0 as f64 + (y1 as f64 - y0 as f64) * t as f64 / 40.0;
            for yy in 0..h {
                for xx in 0..w {
                    let (dx, dy) = (xx as f64 - x, yy as f64 - y);
                    if dx * dx + dy * dy <= (r * r) as f64 {
                        img[yy * w + xx] = true;
                    }
                }
            }
        }
    }
    img
}

#[test]
fn lone_pixel_stays() {
    check(&["...", ".#.", "..."], "... / .#. / ...");
}

#[test]
fn square_2x2_keeps_its_top_right() {
    check(&["##", "##"], ".# / ..");
}

#[test]
fn block_3x3_to_its_centre() {
    check(&["###", "###", "###"], "... / .#. / ...");
}

#[test]
fn bar_3x5() {
    check(&["#####", "#####", "#####"], "..... / .###. / .....");
}

#[test]
fn thin_l_loses_only_its_corner() {
    check(&["#..", "#..", "###"], "#.. / #.. / .##");
}

#[test]
fn diagonal_two_thick_becomes_one_line() {
    check(
        &["##....", ".##...", "..##..", "...##.", "....##"],
        "##.... / ..#... / ...#.. / ....#. / .....#",
    );
}

#[test]
fn thick_plus() {
    check(
        &["..##..", "..##..", "######", "######", "..##..", "..##.."],
        "...#.. / ...#.. / .##### / ...... / ...... / ......",
    );
}

#[test]
fn thick_ring_stays_a_ring() {
    check(&["#####", "#####", "##.##", "#####", "#####"], "..... / ..#.. / .#.#. / ..#.. / .....");
}

#[test]
fn two_blobs() {
    check(&["##..#", "##...", "....."], ".#..# / ..... / .....");
}

#[test]
fn already_thin_lines_stay() {
    check(&["#####"], "#####");
    check(&["#", "#", "#"], "# / # / #");
    check(&["#..", ".#.", "..#"], "#.. / .#. / ..#");
}

#[test]
fn empty_and_blank() {
    assert!(thin(&[], 0, 0).is_empty());
    assert_eq!(thin(&[false; 6], 3, 2), vec![false; 6]);
}

#[test]
fn rule_3_parallel_not_sequential_on_random_blobs() {
    for seed in 1..25u64 {
        let (w, h) = (31, 23);
        let img = blobs(seed, w, h);
        assert_eq!(show(&thin(&img, w, h), w), show(&oracle(&img, w, h), w), "seed {seed}");
    }
}

#[test]
fn keeps_every_shape_connected_and_never_adds() {
    for seed in 100..120u64 {
        let (w, h) = (40, 30);
        let img = blobs(seed, w, h);
        let t = thin(&img, w, h);
        assert_eq!(components(&t, w, h), components(&img, w, h), "seed {seed}");
        assert!(t.iter().zip(&img).all(|(&a, &b)| !a || b), "seed {seed}: added a pixel");
    }
}

#[test]
fn thinning_twice_changes_nothing() {
    for seed in 200..210u64 {
        let (w, h) = (35, 25);
        let once = thin(&blobs(seed, w, h), w, h);
        assert_eq!(thin(&once, w, h), once, "seed {seed}");
    }
}

#[test]
fn big_image_is_reasonably_fast() {
    let (w, h) = (800, 600);
    let img: Vec<bool> = (0..w * h).map(|i| (i % w) % 50 < 4 || (i / w) % 40 < 3).collect();
    let start = std::time::Instant::now();
    let t = thin(&img, w, h);
    assert!(start.elapsed().as_secs_f64() < 20.0);
    assert_eq!(components(&t, w, h), components(&img, w, h));
}
