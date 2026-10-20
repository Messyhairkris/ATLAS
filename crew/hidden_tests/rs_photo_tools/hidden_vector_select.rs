use image::{DynamicImage, Rgb, RgbImage};
use photo_tools::options::{Error, VectorOptions};
use photo_tools::select::Mask;
use photo_tools::vector_select::render_selected;
use photo_tools::{contour, despeckle, kmeans, smooth, svg, vector};

fn rb() -> DynamicImage {
    DynamicImage::ImageRgb8(RgbImage::from_fn(2, 1, |x, _| if x == 0 { Rgb([255, 0, 0]) } else { Rgb([0, 0, 255]) }))
}

fn vo() -> VectorOptions {
    VectorOptions { colors: 2, smoothness: 0.0, speckle: 0, max_iterations: 5 }
}

const HEAD: &str = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"1\" viewBox=\"0 0 2 1\">\n";
const RED: &str = "<path fill=\"#ff0000\" fill-rule=\"evenodd\" d=\"M 1 0 C 1 0.33 1 0.67 1 1 C 0.67 1 0.33 1 0 1 C 0 0.67 0 0.33 0 0 C 0.33 0 0.67 0 1 0 Z\"/>\n";
const BLUE: &str = "<path fill=\"#0000ff\" fill-rule=\"evenodd\" d=\"M 1 0 C 1.33 0 1.67 0 2 0 C 2 0.33 2 0.67 2 1 C 1.67 1 1.33 1 1 1 C 1 0.67 1 0.33 1 0 Z\"/>\n";

#[test]
fn left_pixel_only() {
    let keep = Mask::from_bits(2, 1, vec![true, false]).unwrap();
    assert_eq!(render_selected(&rb(), &vo(), &keep), Ok(format!("{HEAD}{RED}</svg>\n")));
}

#[test]
fn right_pixel_only() {
    let keep = Mask::from_bits(2, 1, vec![false, true]).unwrap();
    let got = render_selected(&rb(), &vo(), &keep).unwrap();
    assert_eq!(got, format!("{HEAD}{BLUE}</svg>\n"));
}

#[test]
fn both_pixels() {
    assert_eq!(render_selected(&rb(), &vo(), &Mask::new(2, 1, true)), Ok(format!("{HEAD}{BLUE}{RED}</svg>\n")));
}

#[test]
fn nothing_selected() {
    assert_eq!(render_selected(&rb(), &vo(), &Mask::new(2, 1, false)), Ok(format!("{HEAD}</svg>\n")));
}

#[test]
fn errors_in_order() {
    assert_eq!(
        render_selected(&rb(), &vo(), &Mask::new(1, 1, true)),
        Err(Error::InvalidOption { name: "selection", reason: "is 1x1 but the image is 2x1".to_string() })
    );
    let bad = VectorOptions { colors: 1, ..vo() };
    assert!(matches!(
        render_selected(&rb(), &bad, &Mask::new(1, 1, true)),
        Err(Error::InvalidOption { name: "colors", .. })
    ));
    let empty = DynamicImage::ImageRgb8(RgbImage::new(0, 0));
    assert_eq!(render_selected(&empty, &vo(), &Mask::new(3, 3, true)), Err(Error::EmptyImage));
}

#[test]
fn rule_2_only_a_zero_side_is_empty() {
    let thin = DynamicImage::ImageRgb8(RgbImage::from_pixel(1, 2, Rgb([10, 200, 30])));
    let got = render_selected(&thin, &vo(), &Mask::new(1, 2, true)).unwrap();
    assert!(got.starts_with("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1\" height=\"2\""), "{got}");
    assert!(got.contains("#0ac81e"), "{got}");
    for (w, h) in [(0, 3), (3, 0)] {
        let empty = DynamicImage::ImageRgb8(RgbImage::new(w, h));
        assert_eq!(render_selected(&empty, &vo(), &Mask::new(w, h, true)), Err(Error::EmptyImage), "{w}x{h}");
    }
}

fn scene() -> RgbImage {
    RgbImage::from_fn(20, 14, |x, y| {
        let (dx, dy) = (x as i32 - 9, y as i32 - 7);
        if dx * dx + dy * dy < 18 {
            Rgb([230, 40, 40])
        } else if y < 4 {
            Rgb([40, 90, 220])
        } else if (x + y) % 7 == 0 {
            Rgb([250, 250, 250])
        } else if x > 15 {
            Rgb([10, 10, 10])
        } else {
            Rgb([30, 160, 60])
        }
    })
}

fn by_hand(img: &RgbImage, o: &VectorOptions, keep: &Mask) -> String {
    let (w, h) = (img.width() as usize, img.height() as usize);
    let mut out = format!("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" viewBox=\"0 0 {w} {h}\">\n");
    if keep.count() == 0 {
        return out + "</svg>\n";
    }
    let chosen: Vec<u8> = img
        .as_raw()
        .chunks(3)
        .zip(keep.bits())
        .filter(|(_, &k)| k)
        .flat_map(|(px, _)| px.iter().copied())
        .collect();
    let p = kmeans::quantize(&chosen, o.colors as usize, o.max_iterations as usize);
    let outside = p.colors.len() as u8;
    let mut it = p.labels.iter();
    let labels: Vec<u8> = keep.bits().iter().map(|&k| if k { *it.next().unwrap() } else { outside }).collect();
    let labels: Vec<u8> = despeckle::despeckle(&labels, w, h, o.speckle as usize)
        .into_iter()
        .zip(keep.bits())
        .map(|(l, &k)| if k { l } else { outside })
        .collect();
    let loops = contour::trace(&labels, w, h);
    for (label, c) in p.colors.iter().enumerate() {
        let segs: Vec<Vec<[f64; 8]>> = loops
            .iter()
            .filter(|l| l.label as usize == label)
            .map(|l| {
                smooth::smooth_loop(&l.points, &l.junction, o.smoothness as f64)
                    .iter()
                    .map(|s| [s.from.0, s.from.1, s.c1.0, s.c1.1, s.c2.0, s.c2.1, s.to.0, s.to.1])
                    .collect()
            })
            .collect();
        let d = svg::path_data(&segs);
        if !d.is_empty() {
            out += &format!("<path fill=\"{}\" fill-rule=\"evenodd\" d=\"{d}\"/>\n", svg::hex(*c));
        }
    }
    out + "</svg>\n"
}

fn ring_mask(w: u32, h: u32) -> Mask {
    // a selection with a hole in it: everything within 8 of the centre, minus within 3
    Mask::from_bits(
        w,
        h,
        (0..w * h)
            .map(|i| {
                let (dx, dy) = ((i % w) as i32 - 10, (i / w) as i32 - 7);
                let d = dx * dx + dy * dy;
                d <= 64 && d > 9
            })
            .collect(),
    )
    .unwrap()
}

#[test]
fn scene_with_a_holed_selection_matches_the_pipeline() {
    let img = scene();
    let keep = ring_mask(20, 14);
    for o in [
        VectorOptions { colors: 4, smoothness: 1.0, speckle: 3, max_iterations: 20 },
        VectorOptions { colors: 3, smoothness: 0.0, speckle: 0, max_iterations: 5 },
        VectorOptions { colors: 6, smoothness: 2.0, speckle: 10, max_iterations: 20 },
    ] {
        let got = render_selected(&DynamicImage::ImageRgb8(img.clone()), &o, &keep).unwrap();
        assert_eq!(got, by_hand(&img, &o, &keep), "{o:?}");
        assert!(!got.contains("<rect"), "no background rectangle");
    }
}

#[test]
fn rule_7_despeckle_does_not_fill_the_hole() {
    let img = scene();
    let keep = ring_mask(20, 14);
    // speckle far bigger than the hole: the hole must still stay out of every shape.
    let o = VectorOptions { colors: 3, smoothness: 0.0, speckle: 500, max_iterations: 20 };
    let got = render_selected(&DynamicImage::ImageRgb8(img.clone()), &o, &keep).unwrap();
    assert_eq!(got, by_hand(&img, &o, &keep));
}

#[test]
fn everything_selected_is_vector_render_without_the_rect() {
    let img = DynamicImage::ImageRgb8(scene());
    for o in [
        VectorOptions { colors: 4, smoothness: 1.0, speckle: 3, max_iterations: 20 },
        VectorOptions { colors: 2, smoothness: 0.0, speckle: 0, max_iterations: 5 },
    ] {
        let full = vector::render(&img, &o).unwrap();
        let no_rect: String = full.lines().filter(|l| !l.starts_with("<rect")).map(|l| format!("{l}\n")).collect();
        assert_eq!(render_selected(&img, &o, &Mask::new(20, 14, true)).unwrap(), no_rect, "{o:?}");
    }
}

#[test]
fn rule_5_palette_comes_from_the_selection_only() {
    // left half red, right half a blue-green gradient; select only the right half
    let img = RgbImage::from_fn(8, 2, |x, _| if x < 4 { Rgb([255, 0, 0]) } else { Rgb([0, (30 * x) as u8, 200]) });
    let keep = Mask::from_bits(8, 2, (0..16).map(|i| i % 8 >= 4).collect()).unwrap();
    let o = VectorOptions { colors: 2, smoothness: 0.0, speckle: 0, max_iterations: 20 };
    let got = render_selected(&DynamicImage::ImageRgb8(img.clone()), &o, &keep).unwrap();
    assert!(!got.contains("#ff0000"), "red is outside the selection: {got}");
    assert_eq!(got, by_hand(&img, &o, &keep));
}
