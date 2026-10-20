use photo_tools::sobel::{edge_mask, magnitude};

#[test]
fn flat_image_has_no_gradient() {
    assert_eq!(magnitude(&[90; 12], 4, 3), vec![0u16; 12]);
    assert_eq!(edge_mask(&[90; 12], 4, 3, 1), vec![255; 12]);
}

#[test]
fn threshold_zero_marks_everything() {
    assert_eq!(edge_mask(&[90; 6], 3, 2, 0), vec![0; 6]);
}

#[test]
fn vertical_step_with_clamped_borders() {
    let row = [0, 0, 255, 255];
    let gray: Vec<u8> = row.iter().cycle().take(12).copied().collect();
    let want_row = [0u16, 1020, 1020, 0];
    let want: Vec<u16> = want_row.iter().cycle().take(12).copied().collect();
    assert_eq!(magnitude(&gray, 4, 3), want);
}

#[test]
fn horizontal_step_uses_gy() {
    // Two rows: 0 above, 255 below; clamping repeats each row once.
    let gray = [0, 0, 0, 255, 255, 255];
    assert_eq!(magnitude(&gray, 3, 2), vec![1020; 6]);
}

#[test]
fn single_bright_pixel() {
    let mut gray = [0u8; 9];
    gray[4] = 255;
    assert_eq!(
        magnitude(&gray, 3, 3),
        vec![361, 510, 361, 510, 0, 510, 361, 510, 361]
    );
}

#[test]
fn mask_compares_with_greater_or_equal() {
    let mut gray = [0u8; 9];
    gray[4] = 255;
    assert_eq!(edge_mask(&gray, 3, 3, 400), vec![255, 0, 255, 0, 255, 0, 255, 0, 255]);
    assert_eq!(edge_mask(&gray, 3, 3, 361), vec![0, 0, 0, 0, 255, 0, 0, 0, 0]);
    assert_eq!(edge_mask(&gray, 3, 3, 362), vec![255, 0, 255, 0, 255, 0, 255, 0, 255]);
    assert_eq!(edge_mask(&gray, 3, 3, 511), vec![255; 9]);
}

#[test]
fn one_pixel_image() {
    assert_eq!(magnitude(&[200], 1, 1), vec![0]);
}

#[test]
fn magnitude_is_rounded_not_truncated() {
    // gx = 4, gy = 4 at (0,0) of this 2x2: sqrt(32) = 5.66 -> 6.
    let gray = [0, 1, 1, 2];
    assert_eq!(magnitude(&gray, 2, 2)[0], 6);
}
