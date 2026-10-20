use photo_tools::ascii::{grid, render, RAMP};

#[test]
fn ramp_is_exact() {
    assert_eq!(RAMP, b" .:-=+*#%@");
}

#[test]
fn grid_table() {
    assert_eq!(grid(4, 2, 2), (2, 2, 2, 1));
    assert_eq!(grid(10, 10, 3), (3, 6, 3, 1));
    assert_eq!(grid(0, 5, 3), (0, 0, 0, 0));
    assert_eq!(grid(5, 0, 3), (0, 0, 0, 0));
    assert_eq!(grid(4, 8, 0), (4, 8, 1, 1));
    assert_eq!(grid(3, 6, 10), (1, 2, 3, 3));
    assert_eq!(grid(100, 30, 25), (4, 8, 25, 3));
}

#[test]
fn black_white_and_inverted() {
    assert_eq!(render(&[0; 8], None, 4, 2, 2, false), "@@\n");
    assert_eq!(render(&[255; 8], None, 4, 2, 2, false), "  \n");
    assert_eq!(render(&[0; 8], None, 4, 2, 2, true), "  \n");
    assert_eq!(render(&[255; 8], None, 4, 2, 2, true), "@@\n");
}

#[test]
fn index_table() {
    // mean -> (255 - mean) * 9 / 255
    for (mean, want) in [(255u8, ' '), (0, '@'), (128, '='), (200, '.'), (28, '%'), (100, '+')] {
        assert_eq!(render(&[mean; 2], None, 1, 2, 1, false), format!("{want}\n"), "mean {mean}");
    }
}

#[test]
fn two_rows_of_cells() {
    let gray = [0, 255, 0, 255, 128, 200, 128, 200];
    assert_eq!(render(&gray, None, 2, 4, 2, false), "@ \n=.\n");
}

#[test]
fn cell_mean_truncates() {
    // (0 + 1) / 2 = 0 -> '@'; a rounded mean of 1 would give '%'.
    assert_eq!(render(&[0, 1], None, 1, 2, 1, false), "@\n");
}

#[test]
fn pixels_past_the_last_full_cell_are_ignored() {
    // 5 wide, 2 columns: cells are 2 wide, column x = 4 is never read.
    let mut gray = [0u8; 20];
    for y in 0..4 {
        gray[y * 5 + 4] = 255;
    }
    assert_eq!(render(&gray, None, 5, 4, 2, false), "@@\n");
}

#[test]
fn ansi_colour_per_character_and_reset_per_line() {
    let rgb = [10, 20, 30, 11, 21, 31];
    assert_eq!(
        render(&[0, 0], Some(&rgb), 1, 2, 1, false),
        "\x1b[38;2;10;20;30m@\x1b[0m\n"
    );
    let rgb4 = [255, 0, 0, 0, 0, 255, 255, 0, 0, 0, 0, 255];
    assert_eq!(
        render(&[76, 29, 76, 29], Some(&rgb4), 2, 2, 2, false),
        "\x1b[38;2;255;0;0m*\x1b[38;2;0;0;255m#\x1b[0m\n"
    );
}

#[test]
fn empty_image_is_empty_text() {
    assert_eq!(render(&[], None, 0, 0, 10, false), "");
}
