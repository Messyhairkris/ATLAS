use photo_tools::contour::{is_junction, trace, Loop};

fn lp(label: u8, points: &[(u32, u32)], junction: &[bool]) -> Loop {
    Loop { label, points: points.to_vec(), junction: junction.to_vec() }
}

const T: bool = true;
const F: bool = false;

#[test]
fn empty_image_has_no_loops() {
    assert_eq!(trace(&[], 0, 0), vec![]);
}

#[test]
fn one_pixel() {
    assert_eq!(trace(&[3], 1, 1), vec![lp(3, &[(0, 0), (1, 0), (1, 1), (0, 1)], &[F; 4])]);
}

#[test]
fn straight_points_are_dropped() {
    assert_eq!(
        trace(&[0, 0], 2, 1),
        vec![lp(0, &[(0, 0), (2, 0), (2, 1), (0, 1)], &[F; 4])]
    );
}

#[test]
fn two_labels_side_by_side() {
    assert_eq!(
        trace(&[0, 1], 2, 1),
        vec![
            lp(0, &[(0, 0), (1, 0), (1, 1), (0, 1)], &[F, T, T, F]),
            lp(1, &[(1, 0), (2, 0), (2, 1), (1, 1)], &[T, F, F, T]),
        ]
    );
}

#[test]
fn a_hole_runs_the_other_way() {
    let labels = [0, 0, 0, 0, 1, 0, 0, 0, 0];
    assert_eq!(
        trace(&labels, 3, 3),
        vec![
            lp(0, &[(0, 0), (3, 0), (3, 3), (0, 3)], &[F; 4]),
            lp(0, &[(1, 1), (1, 2), (2, 2), (2, 1)], &[F; 4]),
            lp(1, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[F; 4]),
        ]
    );
}

#[test]
fn saddle_keeps_diagonal_pixels_apart() {
    let labels = [0, 1, 1, 0];
    assert_eq!(
        trace(&labels, 2, 2),
        vec![
            lp(0, &[(0, 0), (1, 0), (1, 1), (0, 1)], &[F, T, T, T]),
            lp(0, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[T, T, F, T]),
            lp(1, &[(1, 0), (2, 0), (2, 1), (1, 1)], &[T, F, T, T]),
            lp(1, &[(0, 1), (1, 1), (1, 2), (0, 2)], &[T, T, T, F]),
        ]
    );
}

#[test]
fn a_junction_in_a_straight_run_is_kept() {
    let labels = [0, 0, 1, 2];
    assert_eq!(
        trace(&labels, 2, 2),
        vec![
            lp(0, &[(0, 0), (2, 0), (2, 1), (1, 1), (0, 1)], &[F, F, T, T, T]),
            lp(1, &[(0, 1), (1, 1), (1, 2), (0, 2)], &[T, T, T, F]),
            lp(2, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[T, T, F, T]),
        ]
    );
}

#[test]
fn l_shape_corners() {
    // 1 1
    // 1 0
    let labels = [1, 1, 1, 0];
    let loops = trace(&labels, 2, 2);
    // (1, 1) has only labels 0 and 1 around it, not in a checkerboard: no junction.
    assert_eq!(loops[1], lp(1, &[(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)],
                           &[F, F, T, F, T, F]));
    assert_eq!(loops[0], lp(0, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[F, T, F, T]));
}

#[test]
fn junction_rules() {
    let labels = [0, 1, 1, 0];
    assert!(!is_junction(&labels, 2, 2, 0, 0)); // outside + 0
    assert!(is_junction(&labels, 2, 2, 1, 0)); // outside, 0, 1
    assert!(is_junction(&labels, 2, 2, 1, 1)); // saddle
    assert!(!is_junction(&[5], 1, 1, 1, 1));
    let flat = [4, 4, 4, 4];
    assert!(!is_junction(&flat, 2, 2, 1, 1));
    // Two labels in a straight split are not a saddle.
    let split = [0, 1, 0, 1];
    assert!(!is_junction(&split, 2, 2, 1, 1));
}

#[test]
fn every_edge_is_used_once_and_loops_close() {
    let labels: Vec<u8> = (0..48).map(|i| ((i * 7 + i / 6) % 3) as u8).collect();
    let loops = trace(&labels, 8, 6);
    for l in &loops {
        assert_eq!(l.points.len(), l.junction.len());
        assert!(l.points.len() >= 4);
        let n = l.points.len();
        for i in 0..n {
            let (a, b) = (l.points[i], l.points[(i + 1) % n]);
            assert!(a.0 == b.0 || a.1 == b.1, "segments are axis-aligned");
        }
        for (i, p) in l.points.iter().enumerate() {
            assert_eq!(l.junction[i], is_junction(&labels, 8, 6, p.0 as usize, p.1 as usize));
        }
    }
    let keys: Vec<(u8, u32, u32)> =
        loops.iter().map(|l| (l.label, l.points[0].1, l.points[0].0)).collect();
    let sorted = {
        let mut k = keys.clone();
        k.sort();
        k
    };
    assert_eq!(keys, sorted);
}
