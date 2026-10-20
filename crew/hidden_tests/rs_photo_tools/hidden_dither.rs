use photo_tools::dither::floyd_steinberg;

#[test]
fn single_pixels_threshold_at_128() {
    assert_eq!(floyd_steinberg(&[100], 1, 1), vec![0]);
    assert_eq!(floyd_steinberg(&[127], 1, 1), vec![0]);
    assert_eq!(floyd_steinberg(&[128], 1, 1), vec![255]);
    assert_eq!(floyd_steinberg(&[255], 1, 1), vec![255]);
}

#[test]
fn error_goes_right() {
    // 100 -> 0, error 100; 100 * 7 / 16 = 43 -> 143 -> 255.
    assert_eq!(floyd_steinberg(&[100, 100], 2, 1), vec![0, 255]);
}

#[test]
fn negative_error_truncates_toward_zero() {
    // 200 -> 255, error -55; -55 * 7 / 16 = -24 (not -25) -> 152 - 24 = 128 -> 255.
    assert_eq!(floyd_steinberg(&[200, 152], 2, 1), vec![255, 255]);
}

#[test]
fn two_by_two() {
    assert_eq!(floyd_steinberg(&[64; 4], 2, 2), vec![0, 0, 0, 255]);
}

#[test]
fn three_by_three_worked_by_hand() {
    assert_eq!(
        floyd_steinberg(&[100; 9], 3, 3),
        vec![0, 255, 0, 0, 255, 0, 0, 0, 255]
    );
}

#[test]
fn every_row_runs_left_to_right() {
    // Scanning row 1 right to left (serpentine) would give [255, 0, 0, 0].
    assert_eq!(floyd_steinberg(&[128, 128, 100, 100], 2, 2), vec![255, 0, 0, 255]);
}

#[test]
fn the_error_buffer_is_not_clamped() {
    // 255 + 43 = 298 is kept, so its error 43 adds 18 to the last pixel: 133 -> 255.
    // Clamping 298 to 255 would pass no error on and give 0.
    assert_eq!(floyd_steinberg(&[100, 255, 115], 3, 1), vec![0, 255, 255]);
}

#[test]
fn every_output_is_black_or_white_and_tone_is_kept() {
    let gray: Vec<u8> = (0..32 * 32).map(|i| ((i % 32) * 8) as u8).collect();
    let out = floyd_steinberg(&gray, 32, 32);
    assert!(out.iter().all(|&v| v == 0 || v == 255));
    let mean_in: f64 = gray.iter().map(|&v| v as f64).sum::<f64>() / gray.len() as f64;
    let mean_out: f64 = out.iter().map(|&v| v as f64).sum::<f64>() / out.len() as f64;
    assert!((mean_in - mean_out).abs() < 4.0, "{mean_in} vs {mean_out}");
}

#[test]
fn empty_image() {
    assert_eq!(floyd_steinberg(&[], 0, 0), Vec::<u8>::new());
}
