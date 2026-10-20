//! Deterministic K-means colour quantization over 5-bit colour bins.
//! Reference for the kmeans.rs contract.

/// The palette (centre order) and one label per pixel.
#[derive(Debug, Clone, PartialEq)]
pub struct Palette {
    pub colors: Vec<[u8; 3]>,
    pub labels: Vec<u8>,
}

struct Bin {
    key: u32,
    count: u64,
    sum: [u64; 3],
    pos: [f64; 3],
}

fn dist2(a: [f64; 3], b: [f64; 3]) -> f64 {
    let (d0, d1, d2) = (a[0] - b[0], a[1] - b[1], a[2] - b[2]);
    d0 * d0 + d1 * d1 + d2 * d2
}

fn nearest(p: [f64; 3], centers: &[[f64; 3]]) -> usize {
    let mut best = 0;
    for (i, c) in centers.iter().enumerate() {
        if dist2(p, *c) < dist2(p, centers[best]) {
            best = i;
        }
    }
    best
}

/// Quantize packed RGB bytes (3 per pixel) to at most `k` colours.
pub fn quantize(rgb: &[u8], k: usize, max_iter: usize) -> Palette {
    let mut by_key = std::collections::BTreeMap::<u32, (u64, [u64; 3])>::new();
    for p in rgb.chunks_exact(3) {
        let key = ((p[0] as u32 >> 3) << 10) | ((p[1] as u32 >> 3) << 5) | (p[2] as u32 >> 3);
        let e = by_key.entry(key).or_insert((0, [0; 3]));
        e.0 += 1;
        for c in 0..3 {
            e.1[c] += p[c] as u64;
        }
    }
    if by_key.is_empty() {
        return Palette { colors: Vec::new(), labels: Vec::new() };
    }
    let bins: Vec<Bin> = by_key
        .into_iter()
        .map(|(key, (count, sum))| Bin {
            key,
            count,
            sum,
            pos: [0, 1, 2].map(|c| sum[c] as f64 / count as f64),
        })
        .collect();
    let k = k.clamp(1, 64).min(bins.len());

    let mut first = 0;
    for (i, b) in bins.iter().enumerate() {
        if b.count > bins[first].count {
            first = i;
        }
    }
    let mut centers = vec![bins[first].pos];
    while centers.len() < k {
        let mut best: Option<(f64, usize)> = None;
        for (i, b) in bins.iter().enumerate() {
            let d = centers.iter().map(|c| dist2(b.pos, *c)).fold(f64::INFINITY, f64::min);
            let better = match best {
                None => true,
                Some((bd, bi)) => {
                    d > bd || (d == bd && (b.count > bins[bi].count
                        || (b.count == bins[bi].count && b.key < bins[bi].key)))
                }
            };
            if better {
                best = Some((d, i));
            }
        }
        centers.push(bins[best.map(|(_, i)| i).unwrap_or(0)].pos);
    }

    let mut assignment: Option<Vec<usize>> = None;
    for _ in 0..max_iter {
        let new: Vec<usize> = bins.iter().map(|b| nearest(b.pos, &centers)).collect();
        if assignment.as_ref() == Some(&new) {
            break;
        }
        let mut sums = vec![([0u64; 3], 0u64); centers.len()];
        for (b, &c) in bins.iter().zip(&new) {
            for ch in 0..3 {
                sums[c].0[ch] += b.sum[ch];
            }
            sums[c].1 += b.count;
        }
        for (c, (s, n)) in centers.iter_mut().zip(sums) {
            if n > 0 {
                *c = [0, 1, 2].map(|ch| s[ch] as f64 / n as f64);
            }
        }
        assignment = Some(new);
    }

    let colors: Vec<[u8; 3]> = centers
        .iter()
        .map(|c| c.map(|v| v.round().clamp(0.0, 255.0) as u8))
        .collect();
    let labels = rgb
        .chunks_exact(3)
        .map(|p| {
            let mut best = 0;
            let mut best_d = i32::MAX;
            for (i, c) in colors.iter().enumerate() {
                let d: i32 = (0..3).map(|ch| (p[ch] as i32 - c[ch] as i32).pow(2)).sum();
                if d < best_d {
                    best_d = d;
                    best = i;
                }
            }
            best as u8
        })
        .collect();
    Palette { colors, labels }
}
