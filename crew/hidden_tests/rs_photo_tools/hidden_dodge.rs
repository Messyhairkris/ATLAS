use photo_tools::dodge::{color_dodge, dodge_layers};

#[test]
fn rule_table() {
    let rows: [(u8, u8, u8); 11] = [
        (0, 255, 0),    // rule 1 before rule 2
        (0, 0, 0),
        (10, 255, 255), // rule 2
        (128, 128, 255),
        (100, 100, 165),
        (200, 0, 200),
        (1, 254, 255),
        (50, 200, 232),
        (255, 0, 255),
        (77, 3, 78),
        (1, 0, 1),
    ];
    for (base, blend, want) in rows {
        assert_eq!(color_dodge(base, blend), want, "color_dodge({base}, {blend})");
    }
}

#[test]
fn rounds_to_nearest_with_half_of_d() {
    // d = 2: (1 * 255 + 1) / 2 = 128; plain truncation would give 127.
    assert_eq!(color_dodge(1, 253), 128);
}

#[test]
fn matches_formula_on_a_grid() {
    for base in (1..=255u32).step_by(7) {
        for blend in (0..255u32).step_by(11) {
            let d = 255 - blend;
            let want = ((base * 255 + d / 2) / d).min(255) as u8;
            assert_eq!(color_dodge(base as u8, blend as u8), want);
        }
    }
}

#[test]
fn layers_pairwise_and_as_long_as_the_shorter() {
    assert_eq!(dodge_layers(&[0, 100, 200], &[255, 100]), vec![0, 165]);
    assert_eq!(dodge_layers(&[10], &[255, 1, 2]), vec![255]);
    assert_eq!(dodge_layers(&[], &[1]), Vec::<u8>::new());
}
