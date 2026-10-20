use image::{DynamicImage, GrayImage, Rgb, RgbImage};
use photo_tools::effects::{render, EffectOutput};
use photo_tools::options::{EffectOptions, Error, Style};
use photo_tools::{ascii, dither, dodge, halftone, hatch, luma};

fn scene() -> DynamicImage {
    DynamicImage::ImageRgb8(RgbImage::from_fn(20, 12, |x, y| {
        Rgb([(x * 12) as u8, (y * 20) as u8, ((x + y) * 6) as u8])
    }))
}

fn gray(img: &DynamicImage) -> Vec<u8> {
    luma::rgb_to_gray(img.to_rgb8().as_raw())
}

fn opts(style: Style) -> EffectOptions {
    EffectOptions { style, ..EffectOptions::default() }
}

fn image_of(out: EffectOutput) -> GrayImage {
    match out {
        EffectOutput::Image(g) => g,
        EffectOutput::Text(t) => panic!("expected an image, got text {t:?}"),
    }
}

#[test]
fn sketch_is_dodge_of_gray_over_blurred_inverse() {
    let img = scene();
    let g = gray(&img);
    let inv = GrayImage::from_raw(20, 12, luma::invert(&g)).unwrap();
    let blurred = imageproc::filter::gaussian_blur_f32(&inv, 3.0);
    let want = dodge::dodge_layers(&g, blurred.as_raw());
    let out = image_of(render(&img, &EffectOptions { blur: 3.0, ..opts(Style::Sketch) }).unwrap());
    assert_eq!(out.dimensions(), (20, 12));
    assert_eq!(out.into_raw(), want);
}

#[test]
fn dither_halftone_hatch_use_their_modules() {
    let img = scene();
    let g = gray(&img);
    let o = |s| EffectOptions { cell: 5, ..opts(s) };
    assert_eq!(image_of(render(&img, &o(Style::Dither)).unwrap()).into_raw(),
               dither::floyd_steinberg(&g, 20, 12));
    assert_eq!(image_of(render(&img, &o(Style::Halftone)).unwrap()).into_raw(),
               halftone::halftone(&g, 20, 12, 5));
    assert_eq!(image_of(render(&img, &o(Style::Hatch)).unwrap()).into_raw(),
               hatch::hatch(&g, 20, 12, 5));
}

#[test]
fn ascii_returns_text() {
    let img = scene();
    let g = gray(&img);
    let o = EffectOptions { columns: 7, ..opts(Style::Ascii) };
    assert_eq!(render(&img, &o).unwrap(), EffectOutput::Text(ascii::render(&g, None, 20, 12, 7, false)));
    let rgb = img.to_rgb8();
    let o = EffectOptions { columns: 5, ansi: true, invert: true, ..opts(Style::Ascii) };
    assert_eq!(
        render(&img, &o).unwrap(),
        EffectOutput::Text(ascii::render(&g, Some(rgb.as_raw()), 20, 12, 5, true))
    );
}

#[test]
fn gray_is_rec601_from_rgb() {
    // (0, 200, 0): Rec. 601 gives 117 -> dither 0; image's own to_luma8 gives 143 -> 255.
    let img = DynamicImage::ImageRgb8(RgbImage::from_pixel(1, 1, Rgb([0, 200, 0])));
    assert_eq!(image_of(render(&img, &opts(Style::Dither)).unwrap()).into_raw(), vec![0]);
    let img = DynamicImage::ImageRgb8(RgbImage::from_pixel(1, 1, Rgb([0, 255, 0])));
    assert_eq!(image_of(render(&img, &opts(Style::Dither)).unwrap()).into_raw(), vec![255]);
}

#[test]
fn validation_then_empty_check() {
    let empty = DynamicImage::ImageRgb8(RgbImage::new(0, 3));
    assert_eq!(
        render(&empty, &EffectOptions { cell: 1, ..opts(Style::Halftone) }),
        Err(Error::InvalidOption { name: "cell", reason: "must be from 2 to 64".to_string() })
    );
    assert_eq!(render(&empty, &opts(Style::Dither)), Err(Error::EmptyImage));
}

#[test]
fn gray_input_works() {
    let img = DynamicImage::ImageLuma8(GrayImage::from_fn(8, 8, |x, y| image::Luma([((x * y) * 4) as u8])));
    let g: Vec<u8> = img.to_luma8().into_raw();
    // A gray image converts to RGB with equal channels, so Rec. 601 luma is the value itself.
    assert_eq!(image_of(render(&img, &opts(Style::Dither)).unwrap()).into_raw(),
               dither::floyd_steinberg(&g, 8, 8));
}
