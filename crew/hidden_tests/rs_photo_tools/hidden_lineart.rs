use image::{DynamicImage, GrayImage, Rgb, RgbImage};
use photo_tools::lineart::render;
use photo_tools::luma::rgb_to_gray;
use photo_tools::options::{EdgeFilter, Error, LineArtOptions};

fn sobel(blur: f32, low: f32) -> LineArtOptions {
    LineArtOptions { filter: EdgeFilter::Sobel, blur, low, high: low.max(1.0) * 2.0 }
}

fn dot() -> DynamicImage {
    let mut img = RgbImage::new(3, 3);
    img.put_pixel(1, 1, Rgb([255, 255, 255]));
    DynamicImage::ImageRgb8(img)
}

fn scene() -> DynamicImage {
    let img = RgbImage::from_fn(24, 16, |x, y| {
        if (6..18).contains(&x) && (4..12).contains(&y) {
            Rgb([220, 180, 40])
        } else if x + y < 10 {
            Rgb([30, 60, 200])
        } else {
            Rgb([90, 90, 90])
        }
    });
    DynamicImage::ImageRgb8(img)
}

fn gray_of(img: &DynamicImage) -> GrayImage {
    let rgb = img.to_rgb8();
    GrayImage::from_raw(img.width(), img.height(), rgb_to_gray(rgb.as_raw())).unwrap()
}

#[test]
fn sobel_marks_edges_black_on_white() {
    let out = render(&dot(), &sobel(0.0, 400.0)).unwrap();
    assert_eq!(out.dimensions(), (3, 3));
    assert_eq!(out.into_raw(), vec![255, 0, 255, 0, 255, 0, 255, 0, 255]);
}

#[test]
fn sobel_threshold_is_the_low_value_rounded() {
    let corners = render(&dot(), &sobel(0.0, 361.4)).unwrap().into_raw();
    assert_eq!(corners, vec![0, 0, 0, 0, 255, 0, 0, 0, 0]);
    let no_corners = render(&dot(), &sobel(0.0, 361.6)).unwrap().into_raw();
    assert_eq!(no_corners, vec![255, 0, 255, 0, 255, 0, 255, 0, 255]);
}

#[test]
fn gray_uses_rec601_luma() {
    // Red is 76 in Rec. 601 (image's own to_luma8 would give 54): |4 * 76| = 304.
    let img = RgbImage::from_fn(3, 1, |x, _| if x < 2 { Rgb([255, 0, 0]) } else { Rgb([0, 0, 0]) });
    let out = render(&DynamicImage::ImageRgb8(img), &sobel(0.0, 300.0)).unwrap();
    assert_eq!(out.into_raw(), vec![255, 0, 0]);
}

#[test]
fn sobel_after_gaussian_blur() {
    let img = scene();
    let blurred = imageproc::filter::gaussian_blur_f32(&gray_of(&img), 1.5);
    let want = photo_tools::sobel::edge_mask(blurred.as_raw(), 24, 16, 120);
    let out = render(&img, &sobel(1.5, 120.0)).unwrap();
    assert_eq!(out.into_raw(), want);
}

#[test]
fn canny_inverted() {
    let img = scene();
    let opts = LineArtOptions { filter: EdgeFilter::Canny, blur: 0.0, low: 40.0, high: 90.0 };
    let edges = imageproc::edges::canny(&gray_of(&img), 40.0, 90.0);
    let want: Vec<u8> = edges.into_raw().into_iter().map(|v| 255 - v).collect();
    let out = render(&img, &opts).unwrap();
    assert_eq!(out.dimensions(), (24, 16));
    assert_eq!(out.into_raw(), want);
}

#[test]
fn canny_after_blur() {
    let img = scene();
    let opts = LineArtOptions { filter: EdgeFilter::Canny, blur: 1.2, low: 45.0, high: 90.0 };
    let blurred = imageproc::filter::gaussian_blur_f32(&gray_of(&img), 1.2);
    let want: Vec<u8> =
        imageproc::edges::canny(&blurred, 45.0, 90.0).into_raw().into_iter().map(|v| 255 - v).collect();
    assert_eq!(render(&img, &opts).unwrap().into_raw(), want);
    let raw = render(&img, &opts).unwrap().into_raw();
    assert!(raw.iter().any(|&v| v == 0) && raw.iter().any(|&v| v == 255));
}

#[test]
fn options_are_checked_first() {
    let empty = DynamicImage::ImageRgb8(RgbImage::new(0, 0));
    let opts = LineArtOptions { blur: 60.0, ..LineArtOptions::default() };
    assert_eq!(
        render(&empty, &opts),
        Err(Error::InvalidOption { name: "blur", reason: "must be a number from 0 to 50".to_string() })
    );
    assert_eq!(render(&empty, &LineArtOptions::default()), Err(Error::EmptyImage));
    let thin = DynamicImage::ImageRgb8(RgbImage::new(5, 0));
    assert_eq!(render(&thin, &LineArtOptions::default()), Err(Error::EmptyImage));
}

#[test]
fn works_for_gray_and_rgba_inputs() {
    let gray = DynamicImage::ImageLuma8(GrayImage::from_fn(6, 4, |x, _| image::Luma([if x < 3 { 0 } else { 255 }])));
    let out = render(&gray, &sobel(0.0, 500.0)).unwrap();
    assert_eq!(out.get_pixel(2, 1).0[0], 0);
    assert_eq!(out.get_pixel(0, 1).0[0], 255);
    let rgba = DynamicImage::ImageRgba8(gray.to_rgba8());
    assert_eq!(render(&rgba, &sobel(0.0, 500.0)).unwrap(), out);
}
