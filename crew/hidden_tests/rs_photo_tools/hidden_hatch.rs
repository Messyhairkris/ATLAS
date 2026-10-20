use photo_tools::hatch::hatch;

const W: u8 = 255;

#[test]
fn white_stays_white() {
    assert_eq!(hatch(&[255; 12], 4, 3, 3), vec![W; 12]);
    assert_eq!(hatch(&[192; 12], 4, 3, 3), vec![W; 12]);
}

#[test]
fn layer_one_diagonals() {
    let want = vec![0, W, W, 0, W, W, 0, W, W, 0, W, W];
    assert_eq!(hatch(&[150; 12], 4, 3, 3), want);
    assert_eq!(hatch(&[191; 12], 4, 3, 3), want);
    assert_eq!(hatch(&[128; 12], 4, 3, 3), want);
}

#[test]
fn layer_two_adds_the_other_diagonal() {
    let want = vec![0, W, W, 0, W, 0, 0, W, W, 0, 0, W];
    assert_eq!(hatch(&[100; 12], 4, 3, 3), want);
    assert_eq!(hatch(&[64; 12], 4, 3, 3), want);
}

#[test]
fn layer_three_adds_rows() {
    let want = vec![0, 0, 0, 0, W, 0, 0, W, W, 0, 0, W];
    assert_eq!(hatch(&[50; 12], 4, 3, 3), want);
    assert_eq!(hatch(&[32; 12], 4, 3, 3), want);
}

#[test]
fn layer_four_adds_columns() {
    // With spacing 3 the four layers cover every pixel.
    assert_eq!(hatch(&[20; 12], 4, 3, 3), vec![0; 12]);
    let want = vec![
        0, 0, 0, 0, 0, //
        0, 0, W, 0, 0, //
        0, W, 0, W, 0, //
        0, 0, W, 0, 0,
    ];
    assert_eq!(hatch(&[0; 20], 5, 4, 4), want);
    assert_eq!(hatch(&[31; 20], 5, 4, 4), want);
}

#[test]
fn each_pixel_uses_its_own_value() {
    // Left column dark (layer 4 everywhere on x % 3 == 0), right part white.
    let gray = [0, 255, 255, 255, 0, 255, 255, 255];
    assert_eq!(hatch(&gray, 4, 2, 3), vec![0, W, W, W, 0, W, W, W]);
}

#[test]
fn spacing_below_two_is_exactly_two() {
    // Layer 1 only, spacing 2: (x + y) % 2 == 0 -> x = 0 and 2. (Spacing 3 would give x = 0, 3.)
    assert_eq!(hatch(&[150; 4], 4, 1, 0), vec![0, W, 0, W]);
    assert_eq!(hatch(&[150; 4], 4, 1, 1), vec![0, W, 0, W]);
    assert_eq!(hatch(&[150; 4], 4, 1, 2), vec![0, W, 0, W]);
}

#[test]
fn spacing_below_two_counts_as_two() {
    let gray: Vec<u8> = (0..30).map(|i| (i * 9) as u8).collect();
    let two = hatch(&gray, 6, 5, 2);
    assert_eq!(hatch(&gray, 6, 5, 0), two);
    assert_eq!(hatch(&gray, 6, 5, 1), two);
}

#[test]
fn output_is_only_black_or_white() {
    let gray: Vec<u8> = (0..64).map(|i| (i * 4) as u8).collect();
    assert!(hatch(&gray, 8, 8, 4).iter().all(|&v| v == 0 || v == 255));
}
