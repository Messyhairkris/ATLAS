use image::{DynamicImage, Rgb, RgbImage};
use photo_tools::options::{Error, VectorOptions};
use photo_tools::vector::render;
use photo_tools::{contour, despeckle, kmeans, smooth, svg};

fn opts(colors: u8, smoothness: f32, speckle: u32) -> VectorOptions {
    VectorOptions { colors, smoothness, speckle, max_iterations: 20 }
}

#[test]
fn two_pixels_exact_document() {
    let img = RgbImage::from_fn(2, 1, |x, _| if x == 0 { Rgb([255, 0, 0]) } else { Rgb([0, 0, 255]) });
    let want = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"2\" height=\"1\" viewBox=\"0 0 2 1\">\n\
<rect width=\"2\" height=\"1\" fill=\"#0000ff\"/>\n\
<path fill=\"#0000ff\" fill-rule=\"evenodd\" d=\"M 1 0 C 1.33 0 1.67 0 2 0 C 2 0.33 2 0.67 2 1 C 1.67 1 1.33 1 1 1 C 1 0.67 1 0.33 1 0 Z\"/>\n\
<path fill=\"#ff0000\" fill-rule=\"evenodd\" d=\"M 1 0 C 1 0.33 1 0.67 1 1 C 0.67 1 0.33 1 0 1 C 0 0.67 0 0.33 0 0 C 0.33 0 0.67 0 1 0 Z\"/>\n\
</svg>\n";
    assert_eq!(render(&DynamicImage::ImageRgb8(img), &opts(2, 0.0, 0)).unwrap(), want);
}

fn scene() -> RgbImage {
    RgbImage::from_fn(16, 12, |x, y| {
        let dx = x as i32 - 8;
        let dy = y as i32 - 6;
        if dx * dx + dy * dy < 16 {
            Rgb([230, 40, 40])
        } else if y < 4 {
            Rgb([40, 90, 220])
        } else if (x + y) % 7 == 0 {
            Rgb([250, 250, 250])
        } else {
            Rgb([30, 160, 60])
        }
    })
}

fn by_hand(img: &RgbImage, o: &VectorOptions) -> String {
    let (w, h) = (img.width() as usize, img.height() as usize);
    let p = kmeans::quantize(img.as_raw(), o.colors as usize, o.max_iterations as usize);
    let labels = despeckle::despeckle(&p.labels, w, h, o.speckle as usize);
    let mut counts = vec![0usize; p.colors.len()];
    for &l in &labels {
        counts[l as usize] += 1;
    }
    let biggest = (0..counts.len()).fold(0, |b, i| if counts[i] > counts[b] { i } else { b });
    let loops = contour::trace(&labels, w, h);
    let shapes: Vec<([u8; 3], String)> = p
        .colors
        .iter()
        .enumerate()
        .map(|(label, c)| {
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
            (*c, svg::path_data(&segs))
        })
        .collect();
    svg::document(w as u32, h as u32, p.colors[biggest], &shapes)
}

#[test]
fn pipeline_matches_its_parts() {
    let img = scene();
    for o in [opts(4, 1.0, 0), opts(3, 0.0, 4), opts(5, 2.5, 6), opts(2, 1.5, 30)] {
        assert_eq!(render(&DynamicImage::ImageRgb8(img.clone()), &o).unwrap(), by_hand(&img, &o), "{o:?}");
    }
}

#[test]
fn speckle_removes_a_lone_pixel() {
    let mut img = RgbImage::from_pixel(6, 6, Rgb([20, 20, 20]));
    for y in 0..6 {
        for x in 3..6 {
            img.put_pixel(x, y, Rgb([240, 240, 240]));
        }
    }
    img.put_pixel(1, 1, Rgb([240, 240, 240]));
    let with = render(&DynamicImage::ImageRgb8(img.clone()), &opts(2, 0.0, 2)).unwrap();
    let without = render(&DynamicImage::ImageRgb8(img), &opts(2, 0.0, 0)).unwrap();
    assert_eq!(with.matches(" Z").count(), 2);
    assert_eq!(without.matches(" Z").count(), 4);
}

#[test]
fn background_is_the_most_common_label() {
    let img = RgbImage::from_fn(5, 1, |x, _| if x < 2 { Rgb([255, 255, 0]) } else { Rgb([0, 0, 0]) });
    let out = render(&DynamicImage::ImageRgb8(img), &opts(2, 1.0, 0)).unwrap();
    assert!(out.contains("<rect width=\"5\" height=\"1\" fill=\"#000000\"/>"), "{out}");
}

#[test]
fn validation_then_empty_check() {
    let empty = DynamicImage::ImageRgb8(RgbImage::new(0, 0));
    assert_eq!(
        render(&empty, &opts(1, 1.0, 0)),
        Err(Error::InvalidOption { name: "colors", reason: "must be from 2 to 64".to_string() })
    );
    assert_eq!(render(&empty, &opts(8, 1.0, 0)), Err(Error::EmptyImage));
}

#[test]
fn single_colour_image() {
    let img = RgbImage::from_pixel(3, 2, Rgb([10, 200, 30]));
    let out = render(&DynamicImage::ImageRgb8(img), &opts(8, 0.0, 0)).unwrap();
    assert!(out.contains("fill=\"#0ac81e\""));
    assert_eq!(out.matches("<path").count(), 1);
}
