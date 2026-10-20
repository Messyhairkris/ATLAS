use photo_tools::smooth::{simplify, simplify_canonical, smooth_loop, split_chains, Cubic};

fn close(a: (f64, f64), b: (f64, f64)) -> bool {
    (a.0 - b.0).abs() < 1e-9 && (a.1 - b.1).abs() < 1e-9
}

fn reversed(c: &Cubic) -> Cubic {
    Cubic { from: c.to, c1: c.c2, c2: c.c1, to: c.from }
}

#[test]
fn simplify_short_chains_unchanged() {
    assert_eq!(simplify(&[], 1.0), vec![]);
    assert_eq!(simplify(&[(1.0, 2.0)], 1.0), vec![(1.0, 2.0)]);
    assert_eq!(simplify(&[(0.0, 0.0), (5.0, 5.0)], 9.0), vec![(0.0, 0.0), (5.0, 5.0)]);
}

#[test]
fn simplify_drops_points_within_epsilon() {
    let pts = [(0.0, 0.0), (1.0, 0.1), (2.0, 0.0)];
    assert_eq!(simplify(&pts, 0.5), vec![(0.0, 0.0), (2.0, 0.0)]);
    assert_eq!(simplify(&pts, 0.05), pts.to_vec());
}

#[test]
fn simplify_keeps_a_point_only_when_strictly_farther() {
    let pts = [(0.0, 0.0), (1.0, 1.0), (3.0, -1.0), (4.0, 0.0)];
    assert_eq!(simplify(&pts, 1.0), vec![(0.0, 0.0), (4.0, 0.0)]);
    assert_eq!(simplify(&pts, 0.99), pts.to_vec());
}

#[test]
fn simplify_recurses_on_both_sides() {
    let pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 3.0), (3.0, 0.0), (4.0, 0.2), (5.0, 0.0)];
    assert_eq!(
        simplify(&pts, 0.5),
        vec![(0.0, 0.0), (1.0, 0.0), (2.0, 3.0), (3.0, 0.0), (5.0, 0.0)]
    );
}

#[test]
fn simplify_closed_chain_measures_from_the_start_point() {
    let sq = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)];
    assert_eq!(simplify(&sq, 0.5), sq.to_vec());
    assert_eq!(simplify(&sq, 3.0), vec![(0.0, 0.0), (0.0, 0.0)]);
}

#[test]
fn canonical_direction_is_symmetric() {
    let chain: Vec<(f64, f64)> =
        vec![(5.0, 1.0), (4.0, 1.0), (4.0, 2.0), (3.0, 2.0), (3.0, 3.0), (1.0, 3.0), (0.0, 4.0)];
    for eps in [0.0, 0.4, 0.8, 1.5] {
        let fwd = simplify_canonical(&chain, eps);
        let rev: Vec<_> = chain.iter().rev().copied().collect();
        let mut back = simplify_canonical(&rev, eps);
        back.reverse();
        assert_eq!(fwd, back, "eps {eps}");
    }
}

#[test]
fn canonical_runs_from_the_smaller_end() {
    // Starting from (0,4) or from (4,0): the canonical run starts at (4,0), whose y is 0.
    let chain = vec![(0.0, 4.0), (1.0, 3.0), (2.0, 2.2), (3.0, 1.0), (4.0, 0.0)];
    let rev: Vec<_> = chain.iter().rev().copied().collect();
    let mut want = simplify(&rev, 0.3);
    want.reverse();
    assert_eq!(simplify_canonical(&chain, 0.3), want);
}

#[test]
fn split_without_junctions_is_one_closed_chain() {
    let pts = [(0, 0), (2, 0), (2, 1), (0, 1)];
    assert_eq!(
        split_chains(&pts, &[false; 4]),
        vec![vec![(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0), (0.0, 0.0)]]
    );
}

#[test]
fn split_runs_junction_to_junction_and_wraps() {
    let pts = [(0, 0), (2, 0), (2, 1), (1, 1), (0, 1)];
    let junction = [false, false, true, true, true];
    assert_eq!(
        split_chains(&pts, &junction),
        vec![
            vec![(2.0, 1.0), (1.0, 1.0)],
            vec![(1.0, 1.0), (0.0, 1.0)],
            vec![(0.0, 1.0), (0.0, 0.0), (2.0, 0.0), (2.0, 1.0)],
        ]
    );
    let one = split_chains(&pts, &[false, false, true, false, false]);
    assert_eq!(one, vec![vec![(2.0, 1.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0), (2.0, 0.0), (2.0, 1.0)]]);
}

#[test]
fn epsilon_zero_gives_straight_segments() {
    let segs = smooth_loop(&[(0, 0), (1, 0), (1, 1), (0, 1)], &[false; 4], 0.0);
    assert_eq!(segs.len(), 4);
    let s = segs[0];
    assert_eq!(s.from, (0.0, 0.0));
    assert!(close(s.c1, (1.0 / 3.0, 0.0)) && close(s.c2, (2.0 / 3.0, 0.0)));
    assert_eq!(s.to, (1.0, 0.0));
    assert_eq!(segs[3].to, (0.0, 0.0));
}

#[test]
fn closed_loops_wrap_the_catmull_rom_neighbours() {
    let segs = smooth_loop(&[(0, 0), (1, 0), (1, 1), (0, 1)], &[false; 4], 0.5);
    assert_eq!(segs.len(), 4);
    assert!(close(segs[0].c1, (1.0 / 6.0, -1.0 / 6.0)));
    assert!(close(segs[0].c2, (5.0 / 6.0, -1.0 / 6.0)));
    assert!(close(segs[2].c1, (5.0 / 6.0, 7.0 / 6.0)));
}

#[test]
fn open_chains_clamp_their_ends() {
    let pts = [(0, 0), (2, 0), (2, 1), (1, 1), (0, 1)];
    let junction = [false, false, true, true, true];
    let segs = smooth_loop(&pts, &junction, 0.5);
    assert_eq!(segs.len(), 5);
    assert_eq!(segs[0].from, (2.0, 1.0));
    assert!(close(segs[0].c1, (2.0 - 1.0 / 6.0, 1.0)));
    assert!(close(segs[0].c2, (1.0 + 1.0 / 6.0, 1.0)));
    // Third chain (0,1) (0,0) (2,0) (2,1): its first segment starts at the junction
    // with P0 = the start itself.
    assert_eq!(segs[2].from, (0.0, 1.0));
    assert!(close(segs[2].c1, (0.0, 1.0 - 1.0 / 6.0)));
    assert!(close(segs[2].c2, (0.0 - 2.0 / 6.0, 1.0 / 6.0)));
    assert_eq!(segs[4].to, (2.0, 1.0));
}

#[test]
fn shared_borders_come_out_identical_from_both_sides() {
    // A staircase loop with junctions; walking it the other way must give the same
    // segments reversed, bit for bit, for every epsilon.
    let pts = [(0, 0), (3, 0), (3, 1), (2, 1), (2, 2), (1, 2), (1, 3), (0, 3)];
    let junction = [false, true, false, false, false, false, true, false];
    for eps in [0.0, 0.3, 0.75, 1.2, 2.5] {
        let fwd = smooth_loop(&pts, &junction, eps);
        let rp: Vec<_> = pts.iter().rev().copied().collect();
        let rj: Vec<_> = junction.iter().rev().copied().collect();
        let mut back: Vec<Cubic> = smooth_loop(&rp, &rj, eps).iter().map(reversed).collect();
        let key = |c: &Cubic| format!("{:?}", c);
        let mut a: Vec<String> = fwd.iter().map(key).collect();
        let mut b: Vec<String> = back.drain(..).map(|c| key(&c)).collect();
        a.sort();
        b.sort();
        assert_eq!(a, b, "eps {eps}");
    }
}

#[test]
fn segments_join_end_to_start_and_close() {
    let pts = [(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)];
    let junction = [false, false, true, false, true, false];
    let segs = smooth_loop(&pts, &junction, 0.6);
    for w in segs.windows(2) {
        assert_eq!(w[0].to, w[1].from);
    }
    assert_eq!(segs.last().unwrap().to, segs[0].from);
}
