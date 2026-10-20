use photo_tools::luma::{invert, luma, rgb_to_gray};

#[test]
fn luma_table() {
    let rows: [((u8, u8, u8), u8); 9] = [
        ((0, 0, 0), 0),
        ((255, 255, 255), 255),
        ((255, 0, 0), 76),
        ((0, 255, 0), 150),
        ((0, 0, 255), 29),
        ((10, 20, 30), 18),
        ((1, 1, 1), 1),
        ((128, 128, 128), 128),
        ((0, 0, 5), 1),
    ];
    for ((r, g, b), want) in rows {
        assert_eq!(luma(r, g, b), want, "luma({r}, {g}, {b})");
    }
}

#[test]
fn luma_rounds_half_up_not_down() {
    // 587 + 500 = 1087 -> 1; truncating 0.587 would give 0.
    assert_eq!(luma(0, 1, 0), 1);
    // 114 * 4 = 456, + 500 = 956 -> 0.
    assert_eq!(luma(0, 0, 4), 0);
}

#[test]
fn luma_matches_formula_everywhere_on_a_grid() {
    for r in (0..=255u32).step_by(15) {
        for g in (0..=255u32).step_by(17) {
            for b in (0..=255u32).step_by(51) {
                let want = ((299 * r + 587 * g + 114 * b + 500) / 1000) as u8;
                assert_eq!(luma(r as u8, g as u8, b as u8), want);
            }
        }
    }
}

#[test]
fn rgb_to_gray_ignores_a_partial_triple() {
    assert_eq!(rgb_to_gray(&[255, 0, 0, 0, 255, 0, 7]), vec![76, 150]);
    assert_eq!(rgb_to_gray(&[1, 2]), Vec::<u8>::new());
    assert_eq!(rgb_to_gray(&[]), Vec::<u8>::new());
}

#[test]
fn invert_every_byte() {
    assert_eq!(invert(&[0, 255, 100, 1]), vec![255, 0, 155, 254]);
    assert_eq!(invert(&[]), Vec::<u8>::new());
}
