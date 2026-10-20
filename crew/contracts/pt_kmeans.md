# Contract: kmeans.rs - deterministic colour quantization

Module `src/kmeans.rs` of the crate `photo_tools`. Reduces a photo's colours to at most
`k` (the vector engine's `--colors`). K-means runs on 5-bit colour BINS rather than on
every pixel, which makes it fast and fully deterministic - no randomness anywhere.

## API (exact)

```rust
//! Deterministic K-means colour quantization over 5-bit colour bins.

/// The palette (centre order) and one label per pixel.
#[derive(Debug, Clone, PartialEq)]
pub struct Palette {
    pub colors: Vec<[u8; 3]>,
    pub labels: Vec<u8>,
}

/// Quantize packed RGB bytes (3 per pixel) to at most `k` colours.
pub fn quantize(rgb: &[u8], k: usize, max_iter: usize) -> Palette
```

Imports allowed: std only (`std::collections::BTreeMap` is a good fit for bins).

Pixels are `rgb.chunks_exact(3)` (a trailing partial triple is ignored).

## Rules

1. BINS. Each pixel `(r, g, b)` falls in the bin with
   `key = (r >> 3) << 10 | (g >> 3) << 5 | (b >> 3)` (as `u32`). A bin keeps `count`
   (pixels) and `sum_r, sum_g, sum_b` (as `u64`). List the bins in ASCENDING key order.
   A bin's POSITION is `[sum_r / count, sum_g / count, sum_b / count]` in `f64`.
2. No pixels: return `Palette { colors: vec![], labels: vec![] }`.
3. `k` is clamped to `1..=64`, then to at most the number of bins.
4. DISTANCE between two `f64` colours is the squared Euclidean distance
   `d0*d0 + d1*d1 + d2*d2` (no square root).
5. INITIAL CENTRES (farthest-first, no randomness):
   - centre 0 = the position of the bin with the largest `count`; ties -> the smaller key.
   - each next centre = the position of the bin whose distance to its NEAREST chosen
     centre is largest; ties -> the larger `count`, then the smaller key.
6. ITERATE at most `max_iter` times (`max_iter == 0` means no iterations: keep the rule-5
   centres):
   a. ASSIGN every bin to its nearest centre (rule 4); ties -> the lower centre index.
   b. If this assignment equals the previous iteration's assignment, STOP (the first
      iteration always continues).
   c. UPDATE each centre to `[sum of its bins' sum_r / sum of their counts, ...g, ...b]`
      in `f64` (that is, the pixel-weighted mean). A centre with no bins keeps its place.
7. PALETTE: each centre channel rounded with `f64::round` (half away from zero), clamped
   to `0.0..=255.0`, as `u8`. `colors[i]` is centre `i`, in centre order.
8. LABELS: for every pixel in input order, the index of the nearest PALETTE colour,
   measured on the pixel's own bytes and the rounded palette in integers
   (`sum of (p - c)^2` in `i32`); ties -> the lower index.

## Worked examples

| pixels | k | max_iter | colors | labels |
|---|---|---|---|---|
| (none) | 4 | 10 | `[]` | `[]` |
| `(10,10,10) x3, (200,50,50) x2` in order `a a b a b` | 2 | 10 | `[[10,10,10], [200,50,50]]` | `[0, 0, 1, 0, 1]` |
| `(9,9,9) x6` | 8 | 10 | `[[9,9,9]]` | `[0; 6]` |
| `(10,10,10) x3, (200,50,50) x2` | 0 | 5 | `[[86,26,26]]` | all 0 |
| `(8,8,8), (15,15,15)` | 1 | 0 | `[[12,12,12]]` | `[0, 0]` |
| `(0,0,0), (40,0,0), (48,0,0), (200,0,0)` | 2 | 10 | `[[29,0,0], [200,0,0]]` | `[0, 0, 0, 1]` |
| same four | 3 | 10 | `[[0,0,0], [200,0,0], [44,0,0]]` | `[0, 2, 2, 1]` |
| `g g g (64,128,128) (192,128,128)`, g = (128,128,128) | 2 | 10 | `[[144,128,128], [64,128,128]]` | `[0, 0, 0, 1, 0]` |
| `(0,0,0) x2, (100,0,0), (200,0,0) x2` | 2 | 10 | `[[33,0,0], [200,0,0]]` | `[0, 0, 0, 1, 1]` |

Walk-throughs:

- `(8,8,8), (15,15,15)`: same bin (`8>>3 = 15>>3 = 1`), position 11.5; no iterations;
  11.5 rounds to 12.
- `(0..), (40..), (48..), (200..)`, k = 2: four bins of count 1. Centre 0: all counts tie,
  smallest key -> (0,0,0). Centre 1: farthest -> (200,0,0). Iteration 1 assigns 0, 40,
  48 to centre 0 and moves it to 88 / 3 = 29.33; iteration 2 gives the same assignment ->
  stop. 29.33 rounds to 29.
- k = 3 on the same pixels: centre 2 is the bin farthest from its nearest centre:
  40 is 1600 from centre 0, 48 is 2304 -> (48,0,0). Then 40 and 48 move to centre 2,
  which becomes 44.
- The `g` row: (64,..) and (192,..) are both 4096 from centre 0 with count 1 each -> the
  smaller key, (64,..), is centre 1. (192,..) is nearer centre 0, which becomes
  (3*128 + 192) / 4 = 144. With TWO (192,..) pixels instead, (192,..) wins the tie by count.
- The last row: (0,..) and (200,..) both have count 2 -> smaller key (0,..) is centre 0.
  (100,..) is 10000 from both centres -> lower index, centre 0, which becomes 100 / 3.
