use image::{GrayAlphaImage, GrayImage, LumaA};
use photo_tools::composite::{blank_outside, erase, flatten, keep, opaque};
use photo_tools::options::Error;
use photo_tools::select::Mask;

fn gray(w: u32, h: u32, v: &[u8]) -> GrayImage {
    GrayImage::from_raw(w, h, v.to_vec()).unwrap()
}

fn mask(w: u32, h: u32, s: &str) -> Mask {
    Mask::from_bits(w, h, s.chars().map(|c| c == '#').collect()).unwrap()
}

fn la(img: &GrayAlphaImage) -> Vec<(u8, u8)> {
    img.pixels().map(|p| (p[0], p[1])).collect()
}

fn sel_err(reason: &str) -> Error {
    Error::InvalidOption { name: "selection", reason: reason.to_string() }
}

#[test]
fn rule_3_opaque() {
    let out = opaque(&gray(2, 1, &[10, 200]));
    assert_eq!((out.width(), out.height()), (2, 1));
    assert_eq!(la(&out), vec![(10, 255), (200, 255)]);
}

#[test]
fn rule_4_keep() {
    let out = keep(&gray(3, 1, &[10, 200, 0]), &mask(3, 1, "#.#")).unwrap();
    assert_eq!(la(&out), vec![(10, 255), (255, 0), (0, 255)]);
}

#[test]
fn rule_4_keep_2d_layout() {
    let out = keep(&gray(2, 2, &[1, 2, 3, 4]), &mask(2, 2, ".##.")).unwrap();
    assert_eq!(out.get_pixel(1, 0), &LumaA([2, 255]));
    assert_eq!(out.get_pixel(0, 1), &LumaA([3, 255]));
    assert_eq!(out.get_pixel(0, 0), &LumaA([255, 0]));
    assert_eq!(out.get_pixel(1, 1), &LumaA([255, 0]));
}

#[test]
fn rule_1_keep_size_mismatch() {
    assert_eq!(keep(&gray(3, 1, &[1, 2, 3]), &mask(2, 1, "##")), Err(sel_err("is 2x1 but the image is 3x1")));
    assert_eq!(keep(&gray(1, 2, &[1, 2]), &mask(2, 1, "##")), Err(sel_err("is 2x1 but the image is 1x2")));
}

#[test]
fn rule_5_erase() {
    let mut img = GrayAlphaImage::from_raw(3, 1, vec![10, 255, 20, 255, 255, 0]).unwrap();
    erase(&mut img, &mask(3, 1, ".##")).unwrap();
    assert_eq!(la(&img), vec![(10, 255), (255, 0), (255, 0)]);
}

#[test]
fn rule_5_erase_leaves_unerased_pixels_alone() {
    let mut img = GrayAlphaImage::from_raw(2, 1, vec![7, 0, 9, 128]).unwrap();
    erase(&mut img, &mask(2, 1, "..")).unwrap();
    assert_eq!(la(&img), vec![(7, 0), (9, 128)]);
}

#[test]
fn rule_1_erase_size_mismatch_changes_nothing() {
    let mut img = GrayAlphaImage::from_raw(2, 2, vec![1, 255, 2, 255, 3, 255, 4, 255]).unwrap();
    let before = img.clone();
    assert_eq!(erase(&mut img, &mask(2, 1, "##")), Err(sel_err("is 2x1 but the image is 2x2")));
    assert_eq!(img, before);
}

#[test]
fn rule_6_flatten() {
    let img = GrayAlphaImage::from_raw(3, 1, vec![10, 255, 37, 0, 90, 128]).unwrap();
    let out = flatten(&img);
    assert_eq!((out.width(), out.height()), (3, 1));
    assert_eq!(out.as_raw(), &vec![10, 255, 90]);
}

#[test]
fn keep_then_flatten_is_white_outside() {
    let out = flatten(&keep(&gray(4, 1, &[0, 0, 50, 50]), &mask(4, 1, "#..#")).unwrap());
    assert_eq!(out.as_raw(), &vec![0, 255, 255, 50]);
}

#[test]
fn rule_7_blank_outside() {
    let mut g = vec![5, 6, 7];
    blank_outside(&mut g, &mask(3, 1, "#.#"), false).unwrap();
    assert_eq!(g, vec![5, 255, 7]);
    let mut g = vec![5, 6, 7];
    blank_outside(&mut g, &mask(3, 1, "#.#"), true).unwrap();
    assert_eq!(g, vec![5, 0, 7]);
}

#[test]
fn rule_2_blank_outside_length_mismatch() {
    let mut g = vec![5, 6, 7];
    assert_eq!(
        blank_outside(&mut g, &mask(2, 2, "####"), false),
        Err(sel_err("has 4 pixels but the image has 3"))
    );
    assert_eq!(g, vec![5, 6, 7]);
}

#[test]
fn empty_images() {
    assert_eq!(la(&opaque(&gray(0, 0, &[]))), vec![]);
    assert_eq!(la(&keep(&gray(0, 0, &[]), &Mask::new(0, 0, true)).unwrap()), vec![]);
    assert!(flatten(&GrayAlphaImage::new(0, 3)).as_raw().is_empty());
}
