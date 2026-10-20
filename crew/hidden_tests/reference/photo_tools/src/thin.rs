//! Guo-Hall thinning to one-pixel lines. Reference for the thin.rs contract.

/// The 8 neighbours P2..P9 of (x, y), clockwise from north; outside the image is false.
fn ring(img: &[bool], w: usize, h: usize, x: usize, y: usize) -> [bool; 8] {
    const OFF: [(i64, i64); 8] = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)];
    let mut out = [false; 8];
    for (k, (dx, dy)) in OFF.iter().enumerate() {
        let (nx, ny) = (x as i64 + dx, y as i64 + dy);
        if nx >= 0 && ny >= 0 && (nx as usize) < w && (ny as usize) < h {
            out[k] = img[ny as usize * w + nx as usize];
        }
    }
    out
}

/// Thin `fg` (true = line) to lines one pixel wide, keeping every line connected.
pub fn thin(fg: &[bool], width: usize, height: usize) -> Vec<bool> {
    let mut img = fg.to_vec();
    loop {
        let mut changed = false;
        for step in 0..2 {
            let mut remove = Vec::new();
            for y in 0..height {
                for x in 0..width {
                    if !img[y * width + x] {
                        continue;
                    }
                    let [p2, p3, p4, p5, p6, p7, p8, p9] = ring(&img, width, height, x, y);
                    let c = (!p2 && (p3 || p4)) as u8
                        + (!p4 && (p5 || p6)) as u8
                        + (!p6 && (p7 || p8)) as u8
                        + (!p8 && (p9 || p2)) as u8;
                    let n1 = (p9 || p2) as u8 + (p3 || p4) as u8 + (p5 || p6) as u8 + (p7 || p8) as u8;
                    let n2 = (p2 || p3) as u8 + (p4 || p5) as u8 + (p6 || p7) as u8 + (p8 || p9) as u8;
                    let n = n1.min(n2);
                    let m = if step == 0 { (p6 || p7 || !p9) && p8 } else { (p2 || p3 || !p5) && p4 };
                    if c == 1 && (2..=3).contains(&n) && !m {
                        remove.push(y * width + x);
                    }
                }
            }
            changed |= !remove.is_empty();
            for i in remove {
                img[i] = false;
            }
        }
        if !changed {
            break;
        }
    }
    img
}
