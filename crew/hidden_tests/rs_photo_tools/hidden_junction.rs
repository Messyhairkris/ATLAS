use photo_tools::junction::is_junction;

#[test]
fn corners_of_a_one_pixel_image_are_not_junctions() {
    for (x, y) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
        assert!(!is_junction(&[5], 1, 1, x, y), "({x}, {y})");
    }
}

#[test]
fn three_values_with_outside_counting_as_one() {
    // 2x1 [0, 1]: (1,0) sees OUTSIDE, OUTSIDE, 0, 1.
    let labels = [0, 1];
    assert!(is_junction(&labels, 2, 1, 1, 0));
    assert!(is_junction(&labels, 2, 1, 1, 1));
    assert!(!is_junction(&labels, 2, 1, 0, 0));
    assert!(!is_junction(&labels, 2, 1, 2, 1));
}

#[test]
fn three_labels_inside_the_image() {
    // 0 0
    // 1 2
    let labels = [0, 0, 1, 2];
    assert!(is_junction(&labels, 2, 2, 1, 1));
    assert!(!is_junction(&labels, 2, 2, 1, 0)); // OUTSIDE, OUTSIDE, 0, 0
}

#[test]
fn four_different_values() {
    let labels = [0, 1, 2, 3];
    assert!(is_junction(&labels, 2, 2, 1, 1));
}

#[test]
fn checkerboard_saddle_inside_the_image() {
    assert!(is_junction(&[0, 1, 1, 0], 2, 2, 1, 1));
    assert!(is_junction(&[7, 3, 3, 7], 2, 2, 1, 1));
}

#[test]
fn two_labels_not_in_a_checkerboard() {
    assert!(!is_junction(&[0, 1, 0, 1], 2, 2, 1, 1)); // straight split
    assert!(!is_junction(&[1, 1, 1, 0], 2, 2, 1, 1)); // L corner
    assert!(!is_junction(&[4, 4, 4, 4], 2, 2, 1, 1)); // flat
}

#[test]
fn a_saddle_needs_all_four_cells_inside() {
    // On the border, OUTSIDE plus a diagonal pair is three values anyway.
    // 2x1 [0, 1]: vertex (1, 1) has 0, 1 above and OUTSIDE below -> three values.
    assert!(is_junction(&[0, 1], 2, 1, 1, 1));
    // OUTSIDE twice and one label twice is only two values.
    assert!(!is_junction(&[3, 3], 2, 1, 1, 1));
}

#[test]
fn border_vertex_between_two_labels() {
    // 3x2:  0 0 1
    //       0 0 1
    let labels = [0, 0, 1, 0, 0, 1];
    assert!(is_junction(&labels, 3, 2, 2, 0)); // OUTSIDE, OUTSIDE, 0, 1
    assert!(!is_junction(&labels, 3, 2, 2, 1)); // 0, 1, 0, 1 - straight split
    assert!(is_junction(&labels, 3, 2, 2, 2)); // 0, 1, OUTSIDE, OUTSIDE
    assert!(!is_junction(&labels, 3, 2, 1, 1)); // all 0
}
