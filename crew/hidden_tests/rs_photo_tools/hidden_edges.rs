use photo_tools::edges::{boundary_edges, raw_loops, RawLoop};

fn raw(label: u8, verts: &[(u32, u32)], dirs: &[u8]) -> RawLoop {
    RawLoop { label, verts: verts.to_vec(), dirs: dirs.to_vec() }
}

#[test]
fn empty_image() {
    assert_eq!(boundary_edges(&[], 0, 0), vec![]);
    assert_eq!(raw_loops(&[], 0, 0), vec![]);
}

#[test]
fn one_pixel_edges_in_vertex_then_direction_order() {
    // Vertex indices (width + 1 = 2): (0,0)=0, (1,0)=1, (0,1)=2, (1,1)=3.
    assert_eq!(
        boundary_edges(&[3], 1, 1),
        vec![(3, (0, 0), 0), (3, (1, 0), 1), (3, (0, 1), 3), (3, (1, 1), 2)]
    );
}

#[test]
fn two_labels_share_a_vertex_and_sort_by_direction() {
    assert_eq!(
        boundary_edges(&[0, 1], 2, 1),
        vec![
            (0, (0, 0), 0),
            (1, (1, 0), 0),
            (0, (1, 0), 1),
            (1, (2, 0), 1),
            (0, (0, 1), 3),
            (0, (1, 1), 2),
            (1, (1, 1), 3),
            (1, (2, 1), 2),
        ]
    );
}

#[test]
fn no_edge_between_equal_labels() {
    let edges = boundary_edges(&[0, 0], 2, 1);
    assert_eq!(edges.len(), 6);
    assert!(!edges.contains(&(0, (1, 0), 1)));
    assert!(!edges.contains(&(0, (1, 1), 3)));
}

#[test]
fn one_loop_keeps_every_vertex() {
    assert_eq!(
        raw_loops(&[0, 0], 2, 1),
        vec![raw(0, &[(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1)], &[0, 0, 1, 2, 2, 3])]
    );
}

#[test]
fn loops_in_order_of_their_first_edge() {
    assert_eq!(
        raw_loops(&[0, 1], 2, 1),
        vec![
            raw(0, &[(0, 0), (1, 0), (1, 1), (0, 1)], &[0, 1, 2, 3]),
            raw(1, &[(1, 0), (2, 0), (2, 1), (1, 1)], &[0, 1, 2, 3]),
        ]
    );
}

#[test]
fn hole_loop_runs_the_other_way() {
    let labels = [0, 0, 0, 0, 1, 0, 0, 0, 0];
    assert_eq!(
        raw_loops(&labels, 3, 3),
        vec![
            raw(
                0,
                &[(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (0, 3),
                  (0, 2), (0, 1)],
                &[0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3],
            ),
            raw(1, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[0, 1, 2, 3]),
            raw(0, &[(1, 1), (1, 2), (2, 2), (2, 1)], &[1, 0, 3, 2]),
        ]
    );
}

#[test]
fn saddle_turns_right() {
    let labels = [0, 1, 1, 0];
    assert_eq!(
        raw_loops(&labels, 2, 2),
        vec![
            raw(0, &[(0, 0), (1, 0), (1, 1), (0, 1)], &[0, 1, 2, 3]),
            raw(1, &[(1, 0), (2, 0), (2, 1), (1, 1)], &[0, 1, 2, 3]),
            raw(1, &[(0, 1), (1, 1), (1, 2), (0, 2)], &[0, 1, 2, 3]),
            raw(0, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[0, 1, 2, 3]),
        ]
    );
}

#[test]
fn l_shape_turns_left_at_the_inner_corner() {
    // 1 1
    // 1 0
    let loops = raw_loops(&[1, 1, 1, 0], 2, 2);
    assert_eq!(
        loops[0],
        raw(1, &[(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2), (0, 1)],
            &[0, 0, 1, 2, 1, 2, 3, 3])
    );
    assert_eq!(loops[1], raw(0, &[(1, 1), (2, 1), (2, 2), (1, 2)], &[0, 1, 2, 3]));
    assert_eq!(loops.len(), 2);
}

#[test]
fn every_edge_is_in_exactly_one_loop_and_loops_close() {
    let labels: Vec<u8> = (0..48).map(|i| ((i * 7 + i / 6) % 3) as u8).collect();
    let edges = boundary_edges(&labels, 8, 6);
    let loops = raw_loops(&labels, 8, 6);
    let mut seen: Vec<(u8, (u32, u32), u8)> = Vec::new();
    for l in &loops {
        assert_eq!(l.verts.len(), l.dirs.len());
        let n = l.verts.len();
        for i in 0..n {
            seen.push((l.label, l.verts[i], l.dirs[i]));
            let (x, y) = l.verts[i];
            let step = [(1i64, 0i64), (0, 1), (-1, 0), (0, -1)][l.dirs[i] as usize];
            let next = l.verts[(i + 1) % n];
            assert_eq!((x as i64 + step.0, y as i64 + step.1), (next.0 as i64, next.1 as i64));
        }
    }
    seen.sort();
    let mut all = edges.clone();
    all.sort();
    assert_eq!(seen, all);
}
