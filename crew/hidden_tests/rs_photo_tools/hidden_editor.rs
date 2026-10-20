use photo_tools::editor::{Editor, Event, Item, Mods, Tool};
use photo_tools::select::{build, Op, Shape};

fn p(x: f32, y: f32) -> Event {
    Event::Press { at: [x, y], mods: Mods::default() }
}
fn ps(x: f32, y: f32) -> Event {
    Event::Press { at: [x, y], mods: Mods { shift: true, ctrl: false } }
}
fn pc(x: f32, y: f32) -> Event {
    Event::Press { at: [x, y], mods: Mods { shift: false, ctrl: true } }
}
fn d(x: f32, y: f32) -> Event {
    Event::Drag { at: [x, y] }
}
fn r(x: f32, y: f32) -> Event {
    Event::Release { at: [x, y] }
}

fn run(ed: &mut Editor, events: &[Event]) {
    for &e in events {
        ed.handle(e);
    }
}

fn poly(pts: &[[f32; 2]]) -> Shape {
    Shape::Polygon(pts.to_vec())
}

fn lasso(ed: &mut Editor, x: f32) {
    run(ed, &[p(x, 0.0), d(x + 4.0, 0.0), d(x + 4.0, 4.0), r(x, 4.0)]);
}

#[test]
fn new_defaults() {
    let ed = Editor::new();
    assert_eq!(ed.tool(), Tool::Lasso);
    assert_eq!(ed.radius(), 12.0);
    assert_eq!(ed.close_radius(), 8.0);
    assert!(ed.selection().is_empty() && ed.erased().is_empty());
    assert!(!ed.can_undo() && !ed.can_redo());
    assert_eq!(ed.pending(), None);
    assert_eq!(Editor::default(), Editor::new());
}

#[test]
fn rule_1_settings_clamp_and_ignore_non_finite() {
    let mut ed = Editor::new();
    ed.set_radius(0.2);
    assert_eq!(ed.radius(), 1.0);
    ed.set_radius(f32::NAN);
    assert_eq!(ed.radius(), 1.0);
    ed.set_radius(900.0);
    assert_eq!(ed.radius(), 500.0);
    ed.set_radius(f32::INFINITY);
    assert_eq!(ed.radius(), 500.0);
    ed.set_radius(33.5);
    assert_eq!(ed.radius(), 33.5);
    ed.set_close_radius(-4.0);
    assert_eq!(ed.close_radius(), 0.0);
    ed.set_close_radius(250.0);
    assert_eq!(ed.close_radius(), 100.0);
    ed.set_close_radius(f32::NAN);
    assert_eq!(ed.close_radius(), 100.0);
    ed.set_tool(Tool::Eraser);
    assert_eq!(ed.tool(), Tool::Eraser);
}

#[test]
fn lasso_skips_close_points_and_a_repeated_release() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(0.5, 0.0), d(4.0, 0.0), d(4.0, 4.0), r(4.0, 4.0)]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]]))]);
    assert!(ed.can_undo());
    assert_eq!(ed.pending(), None);
}

#[test]
fn lasso_drag_exactly_one_pixel_counts() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(1.0, 0.0), d(1.0, 1.0), r(1.0, 1.0)]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]))]);
}

#[test]
fn rule_3_far_measures_differences_away_from_the_origin() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(10.0, 10.0), d(10.5, 10.0), d(14.0, 10.0), d(14.0, 10.5), d(14.0, 14.0), r(14.0, 14.0)]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[10.0, 10.0], [14.0, 10.0], [14.0, 14.0]]))]);
    ed.set_tool(Tool::Brush);
    ed.set_radius(8.0);
    run(&mut ed, &[p(100.0, 50.0), d(101.0, 50.0), d(101.0, 51.0), d(102.0, 50.0), r(102.0, 50.0)]);
    assert_eq!(
        ed.selection()[1],
        (Op::Replace, Shape::Stroke { points: vec![[100.0, 50.0], [102.0, 50.0]], radius: 8.0 })
    );
    ed.set_tool(Tool::Polyline);
    ed.set_close_radius(8.0);
    run(&mut ed, &[p(50.0, 50.0), p(80.0, 50.0), p(80.0, 80.0), p(53.0, 53.0)]);
    assert_eq!(ed.selection()[2].1, poly(&[[50.0, 50.0], [80.0, 50.0], [80.0, 80.0]]));
}

#[test]
fn lasso_release_adds_its_point() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(4.0, 0.0), r(4.0, 4.0)]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]]))]);
}

#[test]
fn lasso_with_two_points_is_dropped() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(4.0, 0.0), r(4.0, 0.0)]);
    assert!(ed.selection().is_empty());
    assert!(!ed.can_undo());
    assert_eq!(ed.pending(), None);
}

#[test]
fn rule_2_keys() {
    let mut ed = Editor::new();
    run(&mut ed, &[ps(0.0, 0.0), d(4.0, 0.0), r(4.0, 4.0)]);
    run(&mut ed, &[pc(0.0, 0.0), d(4.0, 0.0), r(4.0, 4.0)]);
    let both = Event::Press { at: [0.0, 0.0], mods: Mods { shift: true, ctrl: true } };
    run(&mut ed, &[both, d(4.0, 0.0), r(4.0, 4.0)]);
    let ops: Vec<Op> = ed.selection().iter().map(|s| s.0).collect();
    assert_eq!(ops, vec![Op::Add, Op::Subtract, Op::Subtract]);
}

#[test]
fn pending_previews() {
    let mut ed = Editor::new();
    run(&mut ed, &[ps(0.0, 0.0), d(4.0, 0.0)]);
    assert_eq!(ed.pending(), Some(Item::Select(Op::Add, poly(&[[0.0, 0.0], [4.0, 0.0]]))));
    ed.set_tool(Tool::Eraser);
    assert_eq!(ed.pending(), None, "changing tool drops it");
    ed.set_radius(5.0);
    run(&mut ed, &[pc(1.0, 1.0), d(9.0, 1.0)]);
    assert_eq!(ed.pending(), Some(Item::Erase(Shape::Stroke { points: vec![[1.0, 1.0], [9.0, 1.0]], radius: 5.0 })));
    ed.set_radius(7.0);
    assert_eq!(
        ed.pending(),
        Some(Item::Erase(Shape::Stroke { points: vec![[1.0, 1.0], [9.0, 1.0]], radius: 7.0 })),
        "the radius is read at that moment"
    );
}

#[test]
fn polyline_closes_near_the_first_point() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    run(&mut ed, &[p(0.0, 0.0), p(10.0, 0.0), p(10.0, 10.0), p(0.5, 0.5)]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]))]);
    assert_eq!(ed.pending(), None);
}

#[test]
fn polyline_double_click_then_close() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    run(&mut ed, &[p(0.0, 0.0), p(10.0, 0.0), p(10.0, 0.0), p(10.0, 10.0), Event::Close]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]))]);
}

#[test]
fn polyline_ignores_drag_and_release() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    run(&mut ed, &[p(0.0, 0.0), d(3.0, 3.0), r(5.0, 5.0), p(10.0, 0.0), r(10.0, 0.0), p(10.0, 10.0), Event::Close]);
    assert_eq!(ed.selection(), &[(Op::Replace, poly(&[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]))]);
}

#[test]
fn polyline_keys_come_from_the_first_press() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    run(&mut ed, &[pc(0.0, 0.0), ps(10.0, 0.0), p(10.0, 10.0), Event::Close]);
    assert_eq!(ed.selection()[0].0, Op::Subtract);
}

#[test]
fn polyline_back_and_short_close() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    run(&mut ed, &[p(0.0, 0.0), p(10.0, 0.0), Event::Back, p(5.0, 5.0)]);
    assert_eq!(ed.pending(), Some(Item::Select(Op::Replace, poly(&[[0.0, 0.0], [5.0, 5.0]]))));
    ed.handle(Event::Close);
    assert!(ed.selection().is_empty());
    assert_eq!(ed.pending(), None);
    run(&mut ed, &[p(0.0, 0.0), Event::Back]);
    assert_eq!(ed.pending(), None);
}

#[test]
fn polyline_close_radius_zero_never_closes() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    ed.set_close_radius(0.0);
    run(&mut ed, &[p(0.0, 0.0), p(10.0, 0.0), p(10.0, 10.0), p(0.0, 0.0)]);
    assert!(ed.selection().is_empty());
    assert_eq!(
        ed.pending(),
        Some(Item::Select(Op::Replace, poly(&[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 0.0]])))
    );
}

#[test]
fn polyline_press_exactly_at_close_radius_adds_a_point() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Polyline);
    run(&mut ed, &[p(0.0, 0.0), p(20.0, 0.0), p(20.0, 20.0), p(0.0, 8.0)]);
    assert!(ed.selection().is_empty(), "distance 8 is not closer than 8");
    ed.handle(p(0.0, 7.9));
    assert_eq!(ed.selection().len(), 1);
    assert_eq!(ed.selection()[0].1, poly(&[[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 8.0]]));
}

#[test]
fn close_back_ignored_for_other_tools() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(4.0, 0.0), d(4.0, 4.0), Event::Close, Event::Back]);
    assert_eq!(
        ed.pending(),
        Some(Item::Select(Op::Replace, poly(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]])))
    );
}

#[test]
fn brush_click_is_a_dot() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Brush);
    run(&mut ed, &[p(5.0, 5.0), r(5.0, 5.0)]);
    assert_eq!(ed.selection(), &[(Op::Replace, Shape::Stroke { points: vec![[5.0, 5.0]], radius: 12.0 })]);
}

#[test]
fn brush_spacing_is_a_quarter_radius() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Brush);
    ed.set_radius(8.0);
    run(&mut ed, &[p(0.0, 0.0), d(1.0, 0.0), d(2.0, 0.0), d(3.0, 0.0), r(3.0, 0.0)]);
    assert_eq!(
        ed.selection(),
        &[(Op::Replace, Shape::Stroke { points: vec![[0.0, 0.0], [2.0, 0.0], [3.0, 0.0]], radius: 8.0 })]
    );
}

#[test]
fn brush_spacing_never_below_one() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Brush);
    ed.set_radius(2.0);
    run(&mut ed, &[ps(0.0, 0.0), d(0.6, 0.0), d(1.0, 0.0), r(1.0, 0.0)]);
    assert_eq!(
        ed.selection(),
        &[(Op::Add, Shape::Stroke { points: vec![[0.0, 0.0], [1.0, 0.0]], radius: 2.0 })]
    );
}

#[test]
fn eraser_ignores_keys_and_fills_erased() {
    let mut ed = Editor::new();
    ed.set_tool(Tool::Eraser);
    run(&mut ed, &[pc(1.0, 1.0), r(2.0, 1.0)]);
    assert_eq!(ed.erased(), &[Shape::Stroke { points: vec![[1.0, 1.0], [2.0, 1.0]], radius: 12.0 }]);
    assert!(ed.selection().is_empty());
    assert!(ed.can_undo());
}

#[test]
fn drag_and_release_without_press_do_nothing() {
    let mut ed = Editor::new();
    run(&mut ed, &[d(1.0, 1.0), r(2.0, 2.0)]);
    assert_eq!(ed, Editor::new());
}

#[test]
fn cancel_drops_the_shape() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(4.0, 0.0), d(4.0, 4.0), Event::Cancel, r(0.0, 4.0)]);
    assert!(ed.selection().is_empty());
    assert_eq!(ed.pending(), None);
}

#[test]
fn a_new_press_replaces_an_unfinished_lasso() {
    let mut ed = Editor::new();
    run(&mut ed, &[p(0.0, 0.0), d(4.0, 0.0), p(9.0, 9.0)]);
    assert_eq!(ed.pending(), Some(Item::Select(Op::Replace, poly(&[[9.0, 9.0]]))));
}

#[test]
fn undo_with_a_shape_in_progress_only_drops_it() {
    let mut ed = Editor::new();
    lasso(&mut ed, 0.0);
    run(&mut ed, &[p(0.0, 0.0), d(4.0, 0.0), d(4.0, 4.0), Event::Undo]);
    assert_eq!(ed.pending(), None);
    assert_eq!(ed.selection().len(), 1, "the finished lasso is still there");
    ed.handle(Event::Undo);
    assert!(ed.selection().is_empty());
}

#[test]
fn undo_redo() {
    let mut ed = Editor::new();
    lasso(&mut ed, 0.0);
    lasso(&mut ed, 10.0);
    let a = ed.selection()[0].clone();
    let b = ed.selection()[1].clone();
    ed.handle(Event::Undo);
    assert_eq!(ed.selection(), &[a.clone()]);
    assert!(ed.can_redo() && ed.can_undo());
    ed.handle(Event::Redo);
    assert_eq!(ed.selection(), &[a.clone(), b]);
    assert!(!ed.can_redo());
    ed.handle(Event::Undo);
    ed.handle(Event::Undo);
    assert!(ed.selection().is_empty() && !ed.can_undo());
    ed.handle(Event::Undo);
    assert!(ed.selection().is_empty());
}

#[test]
fn a_commit_clears_redo() {
    let mut ed = Editor::new();
    lasso(&mut ed, 0.0);
    ed.handle(Event::Undo);
    lasso(&mut ed, 10.0);
    assert_eq!(ed.selection().len(), 1);
    assert_eq!(ed.selection()[0].1, poly(&[[10.0, 0.0], [14.0, 0.0], [14.0, 4.0], [10.0, 4.0]]));
    assert!(!ed.can_redo());
    ed.handle(Event::Redo);
    assert_eq!(ed.selection().len(), 1);
}

#[test]
fn undo_spans_selection_and_erase() {
    let mut ed = Editor::new();
    lasso(&mut ed, 0.0);
    ed.set_tool(Tool::Eraser);
    run(&mut ed, &[p(1.0, 1.0), r(1.0, 1.0)]);
    ed.set_tool(Tool::Lasso);
    lasso(&mut ed, 20.0);
    ed.handle(Event::Undo);
    assert_eq!((ed.selection().len(), ed.erased().len()), (1, 1));
    ed.handle(Event::Undo);
    assert_eq!((ed.selection().len(), ed.erased().len()), (1, 0));
    ed.handle(Event::Redo);
    assert_eq!((ed.selection().len(), ed.erased().len()), (1, 1));
}

#[test]
fn deselect_is_undoable() {
    let mut ed = Editor::new();
    lasso(&mut ed, 0.0);
    lasso(&mut ed, 10.0);
    let before = ed.selection().to_vec();
    ed.handle(Event::Deselect);
    assert!(ed.selection().is_empty());
    ed.handle(Event::Undo);
    assert_eq!(ed.selection(), before.as_slice());
    ed.handle(Event::Redo);
    assert!(ed.selection().is_empty());
    ed.handle(Event::Undo);
    ed.handle(Event::Undo);
    assert_eq!(ed.selection(), &before[..1]);
}

#[test]
fn deselect_with_nothing_selected_does_nothing() {
    let mut ed = Editor::new();
    ed.handle(Event::Deselect);
    assert!(!ed.can_undo());
    ed.set_tool(Tool::Eraser);
    run(&mut ed, &[p(1.0, 1.0), r(1.0, 1.0)]);
    ed.handle(Event::Undo);
    ed.handle(Event::Deselect);
    assert!(ed.can_redo(), "a deselect that does nothing does not clear redo");
}

#[test]
fn deselect_and_redo_drop_the_pending_shape() {
    let mut ed = Editor::new();
    lasso(&mut ed, 0.0);
    run(&mut ed, &[p(0.0, 0.0), d(5.0, 5.0), Event::Deselect]);
    assert_eq!(ed.pending(), None);
    assert!(ed.selection().is_empty());
    run(&mut ed, &[p(0.0, 0.0), d(5.0, 5.0), Event::Redo]);
    assert_eq!(ed.pending(), None);
}

#[test]
fn masks() {
    let mut ed = Editor::new();
    assert_eq!(ed.selection_mask(8, 8), None);
    assert_eq!(ed.erase_mask(8, 8), None);
    run(&mut ed, &[pc(1.0, 1.0), d(5.0, 1.0), r(5.0, 5.0)]);
    assert_eq!(ed.selection_mask(8, 8), build(8, 8, ed.selection()));
    let m = ed.selection_mask(8, 8).unwrap();
    assert!(m.get(7, 7), "Ctrl first: starts from everything");
    assert!(!m.get(4, 2), "inside the removed triangle");
    ed.set_tool(Tool::Eraser);
    ed.set_radius(1.0);
    run(&mut ed, &[p(2.0, 2.0), r(2.0, 2.0), p(6.0, 6.0), r(6.0, 6.0)]);
    let want = build(
        8,
        8,
        &ed.erased().iter().map(|s| (Op::Add, s.clone())).collect::<Vec<_>>(),
    );
    assert_eq!(ed.erase_mask(8, 8), want);
    assert_eq!(ed.erase_mask(8, 8).unwrap().count(), 8);
}
