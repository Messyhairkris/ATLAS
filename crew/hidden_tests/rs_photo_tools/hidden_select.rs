use image::GrayImage;
use photo_tools::select::{build, rasterize, Mask, Op, Shape};

fn show(bits: &[bool], w: usize) -> String {
    bits.chunks(w)
        .map(|r| r.iter().map(|&b| if b { '#' } else { '.' }).collect::<String>())
        .collect::<Vec<_>>()
        .join(" / ")
}

fn poly(pts: &[[f32; 2]]) -> Shape {
    Shape::Polygon(pts.to_vec())
}

fn stroke(pts: &[[f32; 2]], radius: f32) -> Shape {
    Shape::Stroke { points: pts.to_vec(), radius }
}

/// Rule 2 exactly as written, pixel by pixel: the oracle for the scanline version.
fn winding_oracle(pts: &[[f32; 2]], w: usize, h: usize) -> Vec<bool> {
    let p: Vec<(f64, f64)> = pts.iter().map(|q| (q[0] as f64, q[1] as f64)).collect();
    let mut out = vec![false; w * h];
    for y in 0..h {
        for x in 0..w {
            let (px, py) = (x as f64 + 0.5, y as f64 + 0.5);
            let mut sum = 0;
            for i in 0..p.len() {
                let (a, b) = (p[i], p[(i + 1) % p.len()]);
                let up = a.1 <= py && b.1 > py;
                let down = b.1 <= py && a.1 > py;
                if !up && !down {
                    continue;
                }
                let xi = a.0 + (py - a.1) * (b.0 - a.0) / (b.1 - a.1);
                if px < xi {
                    sum += if up { 1 } else { -1 };
                }
            }
            out[y * w + x] = sum != 0;
        }
    }
    out
}

fn stroke_oracle(pts: &[[f32; 2]], r: f32, w: usize, h: usize) -> Vec<bool> {
    let p: Vec<(f64, f64)> = pts.iter().map(|q| (q[0] as f64, q[1] as f64)).collect();
    let segs: Vec<((f64, f64), (f64, f64))> =
        if p.len() == 1 { vec![(p[0], p[0])] } else { p.windows(2).map(|s| (s[0], s[1])).collect() };
    let r = r as f64;
    let mut out = vec![false; w * h];
    for y in 0..h {
        for x in 0..w {
            let (px, py) = (x as f64 + 0.5, y as f64 + 0.5);
            out[y * w + x] = segs.iter().any(|&(a, b)| {
                let (dx, dy) = (b.0 - a.0, b.1 - a.1);
                let len2 = dx * dx + dy * dy;
                let t = if len2 == 0.0 { 0.0 } else { (((px - a.0) * dx + (py - a.1) * dy) / len2).clamp(0.0, 1.0) };
                let (qx, qy) = (a.0 + t * dx - px, a.1 + t * dy - py);
                qx * qx + qy * qy <= r * r
            });
        }
    }
    out
}

struct Lcg(u64);
impl Lcg {
    fn next(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((self.0 >> 33) as f32) / ((1u64 << 31) as f32)
    }
}

#[test]
fn rule_2_square_selects_the_middle() {
    let r = rasterize(&poly(&[[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0]]), 4, 4);
    assert_eq!(show(&r, 4), ".... / .##. / .##. / ....");
}

#[test]
fn rule_2_centres_on_left_and_top_edges_are_inside() {
    let r = rasterize(&poly(&[[0.5, 0.5], [2.5, 0.5], [2.5, 2.5], [0.5, 2.5]]), 3, 3);
    assert_eq!(show(&r, 3), "##. / ##. / ...");
}

#[test]
fn rule_2_circled_twice_is_nonzero() {
    let pts = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]];
    assert!(rasterize(&poly(&pts), 4, 4).iter().all(|&b| b));
}

#[test]
fn rule_2_bowtie_matches_the_rule() {
    let pts = [[0.0, 0.0], [4.0, 4.0], [4.0, 0.0], [0.0, 4.0]];
    let r = rasterize(&poly(&pts), 4, 4);
    assert_eq!(r, winding_oracle(&pts, 4, 4));
    assert_eq!(show(&r, 4), "...# / #.## / #.## / ...#");
}

#[test]
fn rule_2_reversed_polygon_selects_the_same() {
    let fwd = [[0.3, 0.2], [7.7, 1.1], [6.2, 6.9], [1.4, 5.5]];
    let mut rev = fwd;
    rev.reverse();
    assert_eq!(rasterize(&poly(&fwd), 8, 8), rasterize(&poly(&rev), 8, 8));
}

#[test]
fn rule_2_random_lassos_match_the_pixel_rule() {
    let mut rng = Lcg(7);
    for case in 0..40 {
        let (w, h) = (23usize, 17usize);
        let n = 3 + case % 9;
        let pts: Vec<[f32; 2]> = (0..n)
            .map(|_| [rng.next() * 30.0 - 4.0, rng.next() * 24.0 - 4.0])
            .collect();
        assert_eq!(
            rasterize(&poly(&pts), w as u32, h as u32),
            winding_oracle(&pts, w, h),
            "case {case}: {pts:?}"
        );
    }
}

#[test]
fn rule_2_points_on_pixel_centres_match_the_pixel_rule() {
    let mut rng = Lcg(99);
    for case in 0..30 {
        let pts: Vec<[f32; 2]> = (0..(3 + case % 6))
            .map(|_| [(rng.next() * 12.0).floor() + 0.5, (rng.next() * 12.0).floor() + 0.5])
            .collect();
        assert_eq!(rasterize(&poly(&pts), 12, 12), winding_oracle(&pts, 12, 12), "case {case}: {pts:?}");
    }
}

#[test]
fn rule_1_invalid_polygons_select_nothing() {
    assert!(rasterize(&poly(&[[0.0, 0.0], [4.0, 0.0]]), 4, 1).iter().all(|&b| !b));
    assert!(rasterize(&poly(&[]), 4, 1).iter().all(|&b| !b));
    let nan = poly(&[[0.0, 0.0], [9.0, 0.0], [f32::NAN, 9.0]]);
    assert!(rasterize(&nan, 4, 4).iter().all(|&b| !b));
    let inf = poly(&[[0.0, 0.0], [f32::INFINITY, 0.0], [0.0, 9.0]]);
    assert!(rasterize(&inf, 4, 4).iter().all(|&b| !b));
}

#[test]
fn rule_1_polygon_far_outside_the_image_is_fine() {
    let big = poly(&[[-1e6, -1e6], [1e6, -1e6], [1e6, 1e6], [-1e6, 1e6]]);
    assert!(rasterize(&big, 5, 3).iter().all(|&b| b));
    let away = poly(&[[100.0, 100.0], [200.0, 100.0], [150.0, 200.0]]);
    assert!(rasterize(&away, 5, 3).iter().all(|&b| !b));
}

#[test]
fn rule_3_big_lasso_is_fast_and_right() {
    let (w, h) = (3000u32, 2000u32);
    let n = 5000;
    let pts: Vec<[f32; 2]> = (0..n)
        .map(|i| {
            let a = i as f32 / n as f32 * std::f32::consts::TAU;
            let r = 900.0 + 80.0 * (a * 13.0).sin();
            [1500.0 + r * a.cos(), 1000.0 + r * a.sin() * 0.95]
        })
        .collect();
    let start = std::time::Instant::now();
    let r = rasterize(&poly(&pts), w, h);
    let took = start.elapsed();
    assert!(took.as_secs_f64() < 10.0, "rasterize took {took:?}; sweep each row (rule 3)");
    assert_eq!(r.len(), (w * h) as usize);
    assert!(r[1000 * 3000 + 1500], "the centre is inside");
    assert!(!r[0], "the corner is outside");
    // Spot-check rows against the pixel rule on a cropped copy of the lasso.
    for &y in &[0usize, 137, 1000, 1500, 1999] {
        let py = y as f64 + 0.5;
        for &x in &[0usize, 650, 700, 1500, 2300, 2350, 2999] {
            let px = x as f64 + 0.5;
            let mut sum = 0;
            for i in 0..pts.len() {
                let (a, b) = (pts[i], pts[(i + 1) % pts.len()]);
                let (a, b) = ((a[0] as f64, a[1] as f64), (b[0] as f64, b[1] as f64));
                let up = a.1 <= py && b.1 > py;
                let down = b.1 <= py && a.1 > py;
                if (up || down) && px < a.0 + (py - a.1) * (b.0 - a.0) / (b.1 - a.1) {
                    sum += if up { 1 } else { -1 };
                }
            }
            assert_eq!(r[y * 3000 + x], sum != 0, "pixel ({x}, {y})");
        }
    }
}

#[test]
fn rule_4_brush_dot_radius_1() {
    assert_eq!(show(&rasterize(&stroke(&[[2.0, 2.0]], 1.0), 4, 4), 4), ".... / .##. / .##. / ....");
}

#[test]
fn rule_4_brush_dot_radius_1_6() {
    assert_eq!(show(&rasterize(&stroke(&[[2.0, 2.0]], 1.6), 4, 4), 4), ".##. / #### / #### / .##.");
}

#[test]
fn rule_4_distance_exactly_radius_counts() {
    assert_eq!(show(&rasterize(&stroke(&[[0.5, 0.5]], 1.0), 3, 3), 3), "##. / #.. / ...");
}

#[test]
fn rule_4_segment() {
    assert_eq!(show(&rasterize(&stroke(&[[0.0, 0.5], [4.0, 0.5]], 0.5), 4, 2), 4), "#### / ....");
}

#[test]
fn rule_4_random_strokes_match_the_distance_rule() {
    let mut rng = Lcg(3);
    for case in 0..30 {
        let n = 1 + case % 5;
        let pts: Vec<[f32; 2]> = (0..n).map(|_| [rng.next() * 26.0 - 3.0, rng.next() * 20.0 - 3.0]).collect();
        let r = 0.3 + rng.next() * 4.0;
        assert_eq!(
            rasterize(&stroke(&pts, r), 20, 14),
            stroke_oracle(&pts, r, 20, 14),
            "case {case}: {pts:?} r {r}"
        );
    }
}

#[test]
fn rule_4_long_stroke_on_big_image_is_fast() {
    let pts: Vec<[f32; 2]> = (0..400).map(|i| [i as f32 * 10.0, 1000.0 + (i as f32 * 0.1).sin() * 500.0]).collect();
    let start = std::time::Instant::now();
    let r = rasterize(&stroke(&pts, 30.0), 4000, 3000);
    assert!(start.elapsed().as_secs_f64() < 10.0, "test only each segment's box (rule 4)");
    assert!(r[1000 * 4000]);
    assert!(!r[0]);
}

#[test]
fn rule_1_invalid_strokes_select_nothing() {
    for s in [
        stroke(&[[1.0, 1.0]], 0.0),
        stroke(&[[1.0, 1.0]], -2.0),
        stroke(&[[1.0, 1.0]], f32::NAN),
        stroke(&[[1.0, 1.0]], f32::INFINITY),
        stroke(&[], 3.0),
        stroke(&[[1.0, 1.0], [f32::NAN, 1.0]], 3.0),
    ] {
        assert!(rasterize(&s, 3, 3).iter().all(|&b| !b), "{s:?}");
    }
}

#[test]
fn rasterize_of_an_empty_image_is_empty() {
    assert!(rasterize(&poly(&[[0.0, 0.0], [5.0, 0.0], [0.0, 5.0]]), 0, 0).is_empty());
    assert!(rasterize(&stroke(&[[1.0, 1.0]], 2.0), 0, 7).is_empty());
}

fn a() -> Shape {
    poly(&[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]])
}
fn b() -> Shape {
    poly(&[[3.0, 0.0], [4.0, 0.0], [4.0, 1.0], [3.0, 1.0]])
}
fn c() -> Shape {
    poly(&[[1.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0]])
}

fn built(ops: &[(Op, Shape)]) -> Option<String> {
    build(4, 1, ops).map(|m| show(m.bits(), 4))
}

#[test]
fn build_rules() {
    assert_eq!(built(&[]), None);
    assert_eq!(built(&[(Op::Replace, a())]).as_deref(), Some("##.."));
    assert_eq!(built(&[(Op::Add, a())]).as_deref(), Some("##.."));
    assert_eq!(built(&[(Op::Subtract, a())]).as_deref(), Some("..##"));
    assert_eq!(built(&[(Op::Replace, a()), (Op::Add, b())]).as_deref(), Some("##.#"));
    assert_eq!(built(&[(Op::Replace, a()), (Op::Subtract, c())]).as_deref(), Some("#..."));
    assert_eq!(built(&[(Op::Add, b()), (Op::Replace, c())]).as_deref(), Some(".#.."));
    assert_eq!(built(&[(Op::Subtract, c()), (Op::Add, c())]).as_deref(), Some("####"));
}

#[test]
fn build_keeps_the_size() {
    let m = build(7, 3, &[(Op::Add, a())]).unwrap();
    assert_eq!((m.width(), m.height(), m.bits().len()), (7, 3, 21));
}

#[test]
fn mask_methods() {
    let m = Mask::new(3, 2, true);
    assert_eq!((m.width(), m.height(), m.count()), (3, 2, 6));
    assert!(m.get(2, 1));
    assert!(!m.get(3, 0) && !m.get(0, 2), "outside is false");
    assert_eq!(Mask::new(2, 2, false).count(), 0);
    assert_eq!(Mask::from_bits(2, 2, vec![true; 3]), None);
    let f = Mask::from_bits(2, 2, vec![false, true, true, false]).unwrap();
    assert!(f.get(1, 0) && f.get(0, 1) && !f.get(0, 0) && !f.get(1, 1));
    assert_eq!(f.bits(), &[false, true, true, false]);
    assert_eq!(f.count(), 2);
}

#[test]
fn mask_from_luma_threshold_128() {
    let img = GrayImage::from_raw(3, 1, vec![127, 128, 255]).unwrap();
    let m = Mask::from_luma(&img);
    assert_eq!((m.width(), m.height()), (3, 1));
    assert_eq!(m.bits(), &[false, true, true]);
}

#[test]
fn mask_apply_ops() {
    let mut m = Mask::new(4, 1, false);
    m.apply(Op::Add, &a());
    assert_eq!(show(m.bits(), 4), "##..");
    m.apply(Op::Subtract, &c());
    assert_eq!(show(m.bits(), 4), "#...");
    m.apply(Op::Replace, &b());
    assert_eq!(show(m.bits(), 4), "...#");
}
