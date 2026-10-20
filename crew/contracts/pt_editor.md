# Contract: editor.rs - selection and eraser tools as plain data

Module `src/editor.rs` of the crate `photo_tools`. The editor window (and any program that
embeds the library) feeds pointer and key events, in IMAGE coordinates, to an `Editor`,
then draws what it reports. Lasso, polyline and blob brush select (no key = replace,
Shift = add, Ctrl = remove); the eraser removes parts of the rendered result. Every
finished action can be undone and redone. No UI and no I/O here.

## API (exact)

```rust
//! Selection and eraser tools as plain data: lasso, polyline and blob brush select
//! (Shift adds, Ctrl removes); the eraser removes parts of the rendered result.

use crate::select::{build, Mask, Op, Shape};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tool {
    Lasso,
    Polyline,
    Brush,
    Eraser,
}

/// Modifier keys held at a press.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Mods {
    pub shift: bool,
    pub ctrl: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Event {
    Press { at: [f32; 2], mods: Mods },
    Drag { at: [f32; 2] },
    Release { at: [f32; 2] },
    Close,
    Back,
    Cancel,
    Undo,
    Redo,
    Deselect,
}

/// A finished (or in-progress) shape and what it does.
#[derive(Debug, Clone, PartialEq)]
pub enum Item {
    Select(Op, Shape),
    Erase(Shape),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Editor { /* private fields of your choice */ }

impl Default for Editor { /* Editor::new() */ }

impl Editor {
    pub fn new() -> Editor
    pub fn tool(&self) -> Tool
    pub fn set_tool(&mut self, tool: Tool)
    pub fn radius(&self) -> f32
    pub fn set_radius(&mut self, radius: f32)
    pub fn close_radius(&self) -> f32
    pub fn set_close_radius(&mut self, radius: f32)
    pub fn selection(&self) -> &[(Op, Shape)]
    pub fn erased(&self) -> &[Shape]
    pub fn can_undo(&self) -> bool
    pub fn can_redo(&self) -> bool
    pub fn pending(&self) -> Option<Item>
    pub fn selection_mask(&self, width: u32, height: u32) -> Option<Mask>
    pub fn erase_mask(&self, width: u32, height: u32) -> Option<Mask>
    pub fn handle(&mut self, event: Event)
}
```

Imports allowed: exactly the `use` line above, plus std. `select.rs` (source shown below
the contract) gives `Shape`, `Op`, `Mask` and `build`. Keep every field private.

## State

An editor holds: the TOOL; the brush RADIUS; the CLOSE RADIUS; at most one PENDING shape
(the shape being drawn: its tool, its op, its points); the SELECTION (a list of
`(Op, Shape)`); the ERASED list (eraser strokes); and two history stacks, DONE and UNDONE.
A history entry is one of: a selection item, an erase item, or a deselect (which
remembers the selection list it cleared).

`new()`: tool `Lasso`, radius `12.0`, close radius `8.0`, nothing pending, all lists
empty. `Default` is `new()`.

## Rules

1. SETTINGS.
   - `set_tool(t)`: drops the pending shape, then sets the tool.
   - `set_radius(r)`: if `r` is finite, radius = `r.clamp(1.0, 500.0)`; otherwise ignored.
   - `set_close_radius(r)`: if finite, close radius = `r.clamp(0.0, 100.0)`; otherwise
     ignored.
2. OP FROM KEYS (read at a press): `ctrl` -> `Op::Subtract` (even with shift); else
   `shift` -> `Op::Add`; else `Op::Replace`. The eraser ignores the keys.
3. FAR: `far(a, b, min)` is `dx * dx + dy * dy >= min * min` with `dx = b[0] - a[0]`,
   `dy = b[1] - a[1]`, in `f32`. "Last" below is the pending shape's last point.
4. COMMIT (when a rule says "finish"): take the pending shape away. A lasso or polyline
   with fewer than 3 points is dropped (nothing happens). Otherwise its item - see rule
   12 - is applied (a selection item is pushed onto SELECTION, an erase item onto ERASED),
   pushed onto DONE, and UNDONE is cleared.
5. `Press { at, mods }`:
   - tool `Polyline` with a polyline pending: if it has at least 3 points and
     `far(first point, at, close_radius)` is FALSE (the press is closer than the close
     radius to the first point), FINISH. Otherwise add `at` as a point only if
     `far(last, at, 1.0)` (a second press on the same spot - a double-click - adds
     nothing).
   - every other case (any tool, nothing pending; or a lasso/brush/eraser press while
     something is pending): the pending shape becomes a new one of the current tool with
     the op of rule 2 and the single point `at` (anything pending before is dropped).
6. `Drag { at }`: ignored for `Polyline` and when nothing is pending. Otherwise add `at`
   if `far(last, at, min)`, where `min` is `1.0` for `Lasso` and
   `max(radius / 4.0, 1.0)` for `Brush` and `Eraser`.
7. `Release { at }`: ignored for `Polyline` and when nothing is pending. Otherwise add
   `at` if it is not EQUAL to the last point (`!=`, exact), then FINISH. (A brush or
   eraser click with no drag is a one-point stroke: a dot.)
8. `Close`: tool `Polyline` with a polyline pending: FINISH (under 3 points: dropped).
   Otherwise ignored.
9. `Back`: tool `Polyline` with a polyline pending: remove its last point; if none are
   left, nothing is pending any more. Otherwise ignored.
10. `Cancel`: drop the pending shape (if any).
11. HISTORY.
    - `Undo`: if something is pending, drop it, and that is ALL this undo does. Otherwise
      pop DONE (if empty, nothing happens), revert it - a selection item pops SELECTION,
      an erase item pops ERASED, a deselect puts its remembered list back as SELECTION -
      and push it onto UNDONE.
    - `Redo`: drop the pending shape (if any); then pop UNDONE (if empty, nothing more),
      apply it again - a deselect clears SELECTION again - and push it onto DONE.
    - `Deselect`: drop the pending shape (if any); if SELECTION is empty, nothing more.
      Otherwise push a deselect remembering the current SELECTION onto DONE, clear
      SELECTION, and clear UNDONE.
    - `can_undo()`: DONE is not empty. `can_redo()`: UNDONE is not empty.
12. ITEM of a pending shape (used by `pending()` and by FINISH), with its points in
    order: lasso or polyline -> `Item::Select(op, Shape::Polygon(points))`; brush ->
    `Item::Select(op, Shape::Stroke { points, radius })`; eraser ->
    `Item::Erase(Shape::Stroke { points, radius })`, where `radius` is the editor's
    radius AT THAT MOMENT. `pending()` is `None` when nothing is pending.
13. MASKS. `selection_mask(w, h)` = `build(w, h, selection)`. `erase_mask(w, h)` =
    `build(w, h, ops)` where `ops` is every erased stroke paired with `Op::Add`, in order
    (so `None` when nothing is erased).

## Worked examples

`P(x,y)` = `Press { at: [x, y], mods: Mods::default() }`; `P+shift`, `P+ctrl` with that
key; `D(x,y)` = Drag; `R(x,y)` = Release. Each row starts from `Editor::new()` plus the
setup.

| setup | events | result |
|---|---|---|
| - | `P(0,0) D(0.5,0) D(4,0) D(4,4) R(4,4)` | selection `[(Replace, Polygon([[0,0],[4,0],[4,4]]))]`: D(0.5,0) is under 1.0 from (0,0) so skipped; R(4,4) equals the last point so not added again |
| - | `P(0,0) D(4,0) R(4,0)` | nothing selected (2 points: dropped); `can_undo()` false |
| - | `P+shift(0,0) D(4,0) R(4,4)` | `[(Add, Polygon([[0,0],[4,0],[4,4]]))]` |
| - | `P+ctrl(0,0) ...` (with shift too) | op `Subtract` |
| tool Polyline | `P(0,0) P(10,0) P(10,10) P(0.5,0.5)` | closed by the press near the first point: `[(Replace, Polygon([[0,0],[10,0],[10,10]]))]` |
| tool Polyline | `P(0,0) P(10,0) P(10,0) P(10,10) Close` | `[(Replace, Polygon([[0,0],[10,0],[10,10]]))]` (the repeated press added nothing) |
| tool Polyline | `P(0,0) P(10,0) Back P(5,5) Close` | dropped (2 points: (0,0), (5,5)) |
| tool Polyline | `P(0,0) Back` | nothing pending |
| tool Polyline, `set_close_radius(0.0)` | `P(0,0) P(10,0) P(10,10) P(0,0)` | not closed: 4 points pending, nothing selected yet |
| tool Brush | `P(5,5) R(5,5)` | `[(Replace, Stroke { points: [[5,5]], radius: 12 })]` |
| tool Brush, `set_radius(8.0)` | `P(0,0) D(1,0) D(2,0) D(3,0) R(3,0)` | points `[[0,0],[2,0],[3,0]]` (min step 2.0: D(1,0) skipped; R adds (3,0)) |
| tool Eraser | `P+ctrl(1,1) R(2,1)` | erased `[Stroke { points: [[1,1],[2,1]], radius: 12 }]`, selection empty |
| - | `set_radius(0.2)`, then `set_radius(f32::NAN)` | radius `1.0` |
| - | `P(0,0) D(4,0) D(4,4) Undo` | nothing pending, nothing selected, `can_undo()` false |
| - | lasso A committed, lasso B committed, `Undo` | selection `[A]`, `can_redo()` true; then `Redo` -> `[A, B]` |
| - | A committed, `Undo`, B committed | selection `[B]`, `can_redo()` false (a commit clears UNDONE) |
| - | A, B committed, `Deselect` | selection `[]`; `Undo` -> `[A, B]`; `Redo` -> `[]` |
| - | `Deselect` with nothing selected | nothing; `can_undo()` false |
| tool Lasso | `P(0,0) D(4,0)`, then `set_tool(Brush)` | nothing pending |

`pending()` during `P+shift(0,0) D(4,0)` with the lasso: `Some(Item::Select(Add, Polygon([[0,0],[4,0]])))`.
`pending()` during an eraser drag: `Some(Item::Erase(Stroke { points, radius }))`.
