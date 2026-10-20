use photo_tools::despeckle::despeckle;

#[test]
fn min_area_one_or_less_changes_nothing() {
    let labels = [0, 1, 0, 1, 0, 1];
    assert_eq!(despeckle(&labels, 3, 2, 0), labels.to_vec());
    assert_eq!(despeckle(&labels, 3, 2, 1), labels.to_vec());
}

#[test]
fn a_single_pixel_island_joins_its_surroundings() {
    let labels = [0, 0, 0, 0, 1, 0, 0, 0, 0];
    assert_eq!(despeckle(&labels, 3, 3, 2), vec![0; 9]);
}

#[test]
fn ties_go_to_the_smaller_label() {
    let labels = [1, 1, 1, 2, 0, 1, 2, 2, 2];
    // The centre touches label 1 twice and label 2 twice.
    assert_eq!(despeckle(&labels, 3, 3, 2), vec![1, 1, 1, 2, 1, 1, 2, 2, 2]);
}

#[test]
fn one_pass_in_raster_order_with_current_labels() {
    // [0] joins 5; then [5] sees 5 (just merged) and 2 once each -> 2; then [2] sees 2.
    assert_eq!(despeckle(&[0, 5, 2], 3, 1, 2), vec![5, 2, 2]);
}

#[test]
fn areas_are_measured_once_before_merging() {
    let labels = [1, 1, 1, 2, 0, 1, 2, 2, 2];
    // Every component is smaller than 5; see the contract's walk-through.
    assert_eq!(despeckle(&labels, 3, 3, 5), vec![0; 9]);
}

#[test]
fn diagonal_pixels_are_separate_components() {
    // The two 7s touch only at a corner: each is its own 1-pixel component.
    let labels = [7, 3, 3, 7];
    assert_eq!(despeckle(&labels, 2, 2, 2), vec![3, 3, 3, 3]);
}

#[test]
fn nothing_to_merge_into_keeps_the_label() {
    assert_eq!(despeckle(&[7], 1, 1, 5), vec![7]);
    assert_eq!(despeckle(&[3; 4], 2, 2, 10), vec![3; 4]);
}

#[test]
fn large_regions_are_untouched() {
    let mut labels = vec![4u8; 40];
    for v in labels.iter_mut().skip(20) {
        *v = 9;
    }
    labels[5] = 1;
    let out = despeckle(&labels, 10, 4, 3);
    let mut want = labels.clone();
    want[5] = 4;
    assert_eq!(out, want);
}
