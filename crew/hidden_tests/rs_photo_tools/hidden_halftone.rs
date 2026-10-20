use photo_tools::halftone::halftone;

const W: u8 = 255;

#[test]
fn white_has_no_dots() {
    assert_eq!(halftone(&[255; 16], 4, 4, 4), vec![W; 16]);
    // Odd cell: a pixel centre sits exactly on the cell centre; radius 0 must not mark it.
    assert_eq!(halftone(&[255; 9], 3, 3, 3), vec![W; 9]);
}

#[test]
fn black_fills_the_cell() {
    assert_eq!(halftone(&[0; 16], 4, 4, 4), vec![0; 16]);
    assert_eq!(halftone(&[0; 4], 2, 2, 2), vec![0; 4]);
}

#[test]
fn mid_gray_leaves_the_corners() {
    // mean 128: r^2 = 3.98; corners are 4.5 from the centre, the rest 0.5 or 2.5.
    let want = vec![W, 0, 0, W, 0, 0, 0, 0, 0, 0, 0, 0, W, 0, 0, W];
    assert_eq!(halftone(&[128; 16], 4, 4, 4), want);
}

#[test]
fn partial_cells_keep_the_full_cell_centre() {
    // One 4x4 cell clipped to 3x3: centre stays at (2, 2), so only (0, 0) is outside.
    assert_eq!(halftone(&[128; 9], 3, 3, 4), vec![W, 0, 0, 0, 0, 0, 0, 0, 0]);
}

#[test]
fn mean_is_taken_over_the_pixels_inside_the_image() {
    // 5x1, cell 4: cell 0 covers x 0..4 (mean 0), cell 1 covers x 4 only (mean 255).
    assert_eq!(halftone(&[0, 0, 0, 0, 255], 5, 1, 4), vec![0, 0, 0, 0, W]);
}

#[test]
fn cells_are_independent() {
    // Left 2x2 cell black, right 2x2 cell white.
    let gray = [0, 0, 255, 255, 0, 0, 255, 255];
    assert_eq!(halftone(&gray, 4, 2, 2), vec![0, 0, W, W, 0, 0, W, W]);
}

#[test]
fn second_row_of_cells_averages_its_own_pixels() {
    // 2 wide, 4 high, cell 2: top cell black, bottom cell white.
    let gray = [0, 0, 0, 0, 255, 255, 255, 255];
    assert_eq!(halftone(&gray, 2, 4, 2), vec![0, 0, 0, 0, W, W, W, W]);
}

#[test]
fn cell_below_two_counts_as_two() {
    let gray: Vec<u8> = (0..36).map(|i| (i * 7) as u8).collect();
    let two = halftone(&gray, 6, 6, 2);
    assert_eq!(halftone(&gray, 6, 6, 0), two);
    assert_eq!(halftone(&gray, 6, 6, 1), two);
}

#[test]
fn darker_cells_have_bigger_dots() {
    let mut last = 0;
    for v in [230u8, 180, 120, 60, 10] {
        let black = halftone(&[v; 64], 8, 8, 8).iter().filter(|&&p| p == 0).count();
        assert!(black >= last, "value {v}: {black} < {last}");
        last = black;
    }
    assert!(last > 40);
}
