use image::{DynamicImage, GrayImage, Rgb, RgbImage};
use photo_tools::lineart_svg::{chain_path, render_svg, StrokeOptions};
use photo_tools::options::{EdgeFilter, Error, LineArtOptions};
use photo_tools::select::Mask;
use photo_tools::{lineart, smooth, strokes, svg, thin};

fn ring() -> DynamicImage {
    DynamicImage::ImageRgb8(RgbImage::from_fn(3, 3, |x, y| {
        if x == 1 && y == 1 { Rgb([255, 255, 255]) } else { Rgb([0, 0, 0]) }
    }))
}

fn sobel(low: f32) -> LineArtOptions {
    LineArtOptions { filter: EdgeFilter::Sobel, blur: 0.0, low, high: low }
}

fn t0() -> StrokeOptions {
    StrokeOptions { tolerance: 0.0, ..StrokeOptions::default() }
}

const HEAD3: &str = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"3\" height=\"3\" viewBox=\"0 0 3 3\">\n";

fn path_el(width: &str, d: &str) -> String {
    format!(
        "<path fill=\"none\" stroke=\"#000000\" stroke-width=\"{width}\" stroke-linecap=\"round\" stroke-linejoin=\"round\" d=\"{d}\"/>\n"
    )
}

fn invalid(name: &'static str, reason: &str) -> Error {
    Error::InvalidOption { name, reason: reason.to_string() }
}

#[test]
fn defaults() {
    assert_eq!(StrokeOptions::default(), StrokeOptions { tolerance: 1.0, width: 1.0, min_pixels: 3 });
    assert_eq!(StrokeOptions::default().validate(), Ok(()));
}

#[test]
fn validate_rules_in_order() {
    let d = StrokeOptions::default();
    let tol = invalid("tolerance", "must be a number from 0 to 10");
    let wid = invalid("stroke-width", "must be above 0 and at most 20");
    assert_eq!(StrokeOptions { tolerance: -0.1, ..d }.validate(), Err(tol.clone()));
    assert_eq!(StrokeOptions { tolerance: 10.5, ..d }.validate(), Err(tol.clone()));
    assert_eq!(StrokeOptions { tolerance: f64::NAN, ..d }.validate(), Err(tol.clone()));
    assert_eq!(StrokeOptions { tolerance: 10.0, ..d }.validate(), Ok(()));
    assert_eq!(StrokeOptions { tolerance: 0.0, ..d }.validate(), Ok(()));
    assert_eq!(StrokeOptions { width: 0.0, ..d }.validate(), Err(wid.clone()));
    assert_eq!(StrokeOptions { width: 20.5, ..d }.validate(), Err(wid.clone()));
    assert_eq!(StrokeOptions { width: f64::INFINITY, ..d }.validate(), Err(wid.clone()));
    assert_eq!(StrokeOptions { width: 20.0, ..d }.validate(), Ok(()));
    assert_eq!(StrokeOptions { min_pixels: 10_001, ..d }.validate(), Err(invalid("min-pixels", "must be at most 10000")));
    assert_eq!(StrokeOptions { min_pixels: 10_000, ..d }.validate(), Ok(()));
    assert_eq!(StrokeOptions { tolerance: 99.0, width: -1.0, min_pixels: 99_999 }.validate(), Err(tol));
}

#[test]
fn chain_path_rows() {
    assert_eq!(chain_path(&[(1, 1)], 1.0), "M 1.5 1.5 L 1.5 1.5");
    assert_eq!(chain_path(&[(0, 0), (1, 0), (2, 0), (3, 0)], 0.0), "M 0.5 0.5 L 3.5 0.5");
    assert_eq!(chain_path(&[(0, 0), (1, 0), (2, 0), (3, 0)], 1.0), "M 0.5 0.5 C 1 0.5 3 0.5 3.5 0.5");
    assert_eq!(
        chain_path(&[(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)], 1.0),
        "M 0.5 0.5 C 0.5 0.83 0.17 2.17 0.5 2.5 C 0.83 2.83 2.17 2.5 2.5 2.5"
    );
    assert_eq!(
        chain_path(&[(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1), (0, 0)], 0.0),
        "M 0.5 0.5 L 2.5 0.5 L 2.5 2.5 L 0.5 2.5 L 0.5 0.5 Z"
    );
    assert_eq!(
        chain_path(&[(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)], 0.5),
        "M 0.5 0.5 C 1.17 -0.17 3.83 -0.17 4.5 0.5 C 5.17 1.17 5.17 3.83 4.5 4.5 C 3.83 5.17 1.17 5.17 0.5 4.5 C -0.17 3.83 -0.17 1.17 0.5 0.5 Z"
    );
}

#[test]
fn chain_path_two_points_and_corners_kept_at_tolerance_zero() {
    assert_eq!(chain_path(&[(2, 3), (3, 4)], 0.0), "M 2.5 3.5 L 3.5 4.5");
    assert_eq!(chain_path(&[(0, 0), (1, 0), (1, 1), (2, 1)], 0.0), "M 0.5 0.5 L 1.5 0.5 L 1.5 1.5 L 2.5 1.5");
}

#[test]
fn ring_exact() {
    let want = format!("{HEAD3}{}</svg>\n", path_el("1", "M 1.5 0.5 L 2.5 1.5 L 1.5 2.5 L 0.5 1.5 L 1.5 0.5 Z"));
    assert_eq!(render_svg(&ring(), &sobel(361.4), &t0(), None), Ok(want));
}

#[test]
fn ring_with_selection() {
    let keep = Mask::from_bits(3, 3, (0..9).map(|i| i % 3 >= 1).collect()).unwrap();
    let want = format!("{HEAD3}{}</svg>\n", path_el("1", "M 1.5 0.5 L 2.5 1.5 L 1.5 2.5"));
    assert_eq!(render_svg(&ring(), &sobel(361.4), &t0(), Some(&keep)), Ok(want));
}

#[test]
fn ring_everything_selected_is_like_none() {
    let all = Mask::new(3, 3, true);
    assert_eq!(
        render_svg(&ring(), &sobel(361.4), &t0(), Some(&all)),
        render_svg(&ring(), &sobel(361.4), &t0(), None)
    );
}

#[test]
fn ring_min_pixels_drops_it() {
    let s = StrokeOptions { min_pixels: 5, ..t0() };
    assert_eq!(render_svg(&ring(), &sobel(361.4), &s, None), Ok(format!("{HEAD3}</svg>\n")));
    let s = StrokeOptions { min_pixels: 4, ..t0() };
    assert!(render_svg(&ring(), &sobel(361.4), &s, None).unwrap().contains("<path"));
}

#[test]
fn ring_stroke_width() {
    let s = StrokeOptions { width: 2.5, ..t0() };
    let want = format!("{HEAD3}{}</svg>\n", path_el("2.5", "M 1.5 0.5 L 2.5 1.5 L 1.5 2.5 L 0.5 1.5 L 1.5 0.5 Z"));
    assert_eq!(render_svg(&ring(), &sobel(361.4), &s, None), Ok(want));
}

#[test]
fn white_image_has_no_path() {
    let white = DynamicImage::ImageRgb8(RgbImage::from_pixel(4, 4, Rgb([255, 255, 255])));
    assert_eq!(
        render_svg(&white, &sobel(100.0), &StrokeOptions::default(), None),
        Ok("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"4\" height=\"4\" viewBox=\"0 0 4 4\">\n</svg>\n".to_string())
    );
}

#[test]
fn errors_in_order() {
    let bad_opts = LineArtOptions { blur: 60.0, ..LineArtOptions::default() };
    let bad_stroke = StrokeOptions { tolerance: 11.0, ..t0() };
    assert_eq!(
        render_svg(&ring(), &bad_opts, &bad_stroke, None),
        Err(invalid("blur", "must be a number from 0 to 50"))
    );
    assert_eq!(
        render_svg(&DynamicImage::ImageRgb8(RgbImage::new(0, 0)), &sobel(361.4), &bad_stroke, None),
        Err(invalid("tolerance", "must be a number from 0 to 10"))
    );
    assert_eq!(
        render_svg(&DynamicImage::ImageRgb8(RgbImage::new(0, 0)), &LineArtOptions::default(), &t0(), None),
        Err(Error::EmptyImage)
    );
    assert_eq!(
        render_svg(&ring(), &sobel(361.4), &t0(), Some(&Mask::new(2, 3, true))),
        Err(invalid("selection", "is 2x3 but the image is 3x3"))
    );
}

fn my_path(chain: &[(u32, u32)], tol: f64) -> String {
    let pts: Vec<(f64, f64)> = chain.iter().map(|&(x, y)| (x as f64 + 0.5, y as f64 + 0.5)).collect();
    let q = smooth::simplify(&pts, tol);
    let f = svg::fmt_num;
    let mut d = format!("M {} {}", f(q[0].0), f(q[0].1));
    if q.len() == 1 {
        return format!("{d} L {} {}", f(q[0].0), f(q[0].1));
    }
    let closed = q[0] == q[q.len() - 1] && q.len() > 2;
    let m = q.len() - 1;
    for i in 0..m {
        let (a, b) = (q[i], q[i + 1]);
        if tol == 0.0 {
            d += &format!(" L {} {}", f(b.0), f(b.1));
            continue;
        }
        let p0 = if i > 0 { q[i - 1] } else if closed { q[m - 1] } else { a };
        let p3 = if i + 1 < m { q[i + 2] } else if closed { q[1] } else { b };
        d += &format!(
            " C {} {} {} {} {} {}",
            f(a.0 + (b.0 - p0.0) / 6.0),
            f(a.1 + (b.1 - p0.1) / 6.0),
            f(b.0 - (p3.0 - a.0) / 6.0),
            f(b.1 - (p3.1 - a.1) / 6.0),
            f(b.0),
            f(b.1)
        );
    }
    if closed {
        d += " Z";
    }
    d
}

fn scene() -> DynamicImage {
    DynamicImage::ImageRgb8(RgbImage::from_fn(48, 36, |x, y| {
        let (dx, dy) = (x as i32 - 20, y as i32 - 17);
        if dx * dx + dy * dy < 120 {
            Rgb([30, 30, 30])
        } else if x > 34 && y > 6 && y < 28 {
            Rgb([200, 60, 60])
        } else if (x / 6 + y / 6) % 2 == 0 && y > 28 {
            Rgb([240, 240, 240])
        } else {
            Rgb([120, 160, 200])
        }
    }))
}

fn by_hand(img: &DynamicImage, o: &LineArtOptions, s: &StrokeOptions, keep: Option<&Mask>) -> String {
    let g: GrayImage = lineart::render(img, o).unwrap();
    let (w, h) = (g.width() as usize, g.height() as usize);
    let fg: Vec<bool> =
        g.as_raw().iter().enumerate().map(|(i, &v)| v == 0 && keep.map_or(true, |m| m.bits()[i])).collect();
    let mut paths = Vec::new();
    for c in strokes::trace(&thin::thin(&fg, w, h), w, h) {
        let distinct = if c.len() > 1 && c[0] == c[c.len() - 1] { c.len() - 1 } else { c.len() };
        if distinct >= s.min_pixels {
            paths.push(my_path(&c, s.tolerance));
        }
    }
    let mut out = format!("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" viewBox=\"0 0 {w} {h}\">\n");
    if !paths.is_empty() {
        out += &path_el(&svg::fmt_num(s.width), &paths.join(" "));
    }
    out + "</svg>\n"
}

#[test]
fn scene_matches_the_pipeline() {
    let img = scene();
    for o in [LineArtOptions::default(), sobel(150.0), LineArtOptions { filter: EdgeFilter::Sobel, blur: 1.2, low: 90.0, high: 90.0 }] {
        for s in [StrokeOptions::default(), t0(), StrokeOptions { tolerance: 2.0, width: 1.5, min_pixels: 6 }] {
            let got = render_svg(&img, &o, &s, None).unwrap();
            assert_eq!(got, by_hand(&img, &o, &s, None), "{o:?} {s:?}");
        }
    }
}

#[test]
fn scene_selection_matches_the_pipeline() {
    let img = scene();
    let keep = Mask::from_bits(48, 36, (0..48 * 36).map(|i| (i % 48) < 30 && (i / 48) > 5).collect()).unwrap();
    let o = LineArtOptions::default();
    let s = StrokeOptions::default();
    let got = render_svg(&img, &o, &s, Some(&keep)).unwrap();
    assert_eq!(got, by_hand(&img, &o, &s, Some(&keep)));
    assert_ne!(got, render_svg(&img, &o, &s, None).unwrap(), "the selection must change something here");
}
