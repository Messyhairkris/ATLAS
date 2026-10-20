use photo_tools::kmeans::{quantize, Palette};

fn px(colors: &[[u8; 3]]) -> Vec<u8> {
    colors.iter().flatten().copied().collect()
}

#[test]
fn empty_input_gives_an_empty_palette() {
    let p = quantize(&[], 4, 10);
    assert_eq!(p, Palette { colors: vec![], labels: vec![] });
}

#[test]
fn two_clear_clusters() {
    let rgb = px(&[[10, 10, 10], [10, 10, 10], [200, 50, 50], [10, 10, 10], [200, 50, 50]]);
    let p = quantize(&rgb, 2, 10);
    assert_eq!(p.colors, vec![[10, 10, 10], [200, 50, 50]]);
    assert_eq!(p.labels, vec![0, 0, 1, 0, 1]);
}

#[test]
fn k_above_the_number_of_bins_shrinks_the_palette() {
    let p = quantize(&px(&[[9, 9, 9]; 6]), 8, 10);
    assert_eq!(p.colors, vec![[9, 9, 9]]);
    assert_eq!(p.labels, vec![0; 6]);
}

#[test]
fn k_zero_counts_as_one() {
    let rgb = px(&[[10, 10, 10], [10, 10, 10], [10, 10, 10], [200, 50, 50], [200, 50, 50]]);
    let p = quantize(&rgb, 0, 5);
    assert_eq!(p.colors, vec![[86, 26, 26]]);
}

#[test]
fn zero_iterations_keep_the_initial_bin_means_rounded_half_away() {
    // Same 5-bit bin: mean 11.5 -> 12.
    let p = quantize(&px(&[[8, 8, 8], [15, 15, 15]]), 1, 0);
    assert_eq!(p.colors, vec![[12, 12, 12]]);
}

#[test]
fn centres_move_to_weighted_means() {
    let rgb = px(&[[0, 0, 0], [40, 0, 0], [48, 0, 0], [200, 0, 0]]);
    let p = quantize(&rgb, 2, 10);
    assert_eq!(p.colors, vec![[29, 0, 0], [200, 0, 0]]);
    assert_eq!(p.labels, vec![0, 0, 0, 1]);
}

#[test]
fn third_centre_is_the_farthest_bin() {
    let rgb = px(&[[0, 0, 0], [40, 0, 0], [48, 0, 0], [200, 0, 0]]);
    let p = quantize(&rgb, 3, 10);
    assert_eq!(p.colors, vec![[0, 0, 0], [200, 0, 0], [44, 0, 0]]);
    assert_eq!(p.labels, vec![0, 2, 2, 1]);
}

#[test]
fn farthest_ties_prefer_the_smaller_key_then_count() {
    let g = [128, 128, 128];
    let rgb = px(&[g, g, g, [64, 128, 128], [192, 128, 128]]);
    let p = quantize(&rgb, 2, 10);
    assert_eq!(p.colors, vec![[144, 128, 128], [64, 128, 128]]);
    assert_eq!(p.labels, vec![0, 0, 0, 1, 0]);

    let rgb = px(&[g, g, g, [64, 128, 128], [192, 128, 128], [192, 128, 128]]);
    let p = quantize(&rgb, 2, 10);
    assert_eq!(p.colors[1], [192, 128, 128]);
}

#[test]
fn first_centre_is_the_most_common_bin_ties_to_smaller_key() {
    let rgb = px(&[[0, 0, 0], [0, 0, 0], [100, 0, 0], [200, 0, 0], [200, 0, 0]]);
    let p = quantize(&rgb, 2, 10);
    assert_eq!(p.colors, vec![[33, 0, 0], [200, 0, 0]]);
    assert_eq!(p.labels, vec![0, 0, 0, 1, 1]);
}

#[test]
fn labels_use_the_real_pixel_not_its_bin() {
    // (16,0,0) and (23,0,0) share a bin; with k=2 they are split by the other cluster.
    let rgb = px(&[[16, 0, 0], [23, 0, 0], [16, 0, 0], [200, 0, 0]]);
    let p = quantize(&rgb, 2, 10);
    assert_eq!(p.colors, vec![[18, 0, 0], [200, 0, 0]]);
    assert_eq!(p.labels, vec![0, 0, 0, 1]);
}

#[test]
fn labels_are_valid_indices_on_a_photo_like_input() {
    let rgb: Vec<u8> = (0..30 * 20)
        .flat_map(|i| {
            let (x, y) = ((i % 30) as u32, (i / 30) as u32);
            [(x * 8) as u8, (y * 12) as u8, ((x + y) * 4) as u8]
        })
        .collect();
    let p = quantize(&rgb, 6, 20);
    assert_eq!(p.colors.len(), 6);
    assert_eq!(p.labels.len(), 600);
    assert!(p.labels.iter().all(|&l| (l as usize) < 6));
    // Each pixel's label is a nearest palette colour.
    for (i, c) in rgb.chunks(3).enumerate() {
        let d = |k: usize| -> i32 {
            (0..3).map(|ch| (c[ch] as i32 - p.colors[k][ch] as i32).pow(2)).sum()
        };
        let best = (0..6).map(d).min().unwrap();
        assert_eq!(d(p.labels[i] as usize), best);
    }
}
