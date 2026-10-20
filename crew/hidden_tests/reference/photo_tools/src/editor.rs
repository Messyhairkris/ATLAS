//! Selection and eraser tools as plain data: lasso, polyline and blob brush select
//! (Shift adds, Ctrl removes); the eraser removes parts of the rendered result. No UI:
//! a GUI or a host program feeds pointer and key events in image coordinates and
//! draws what the editor reports. Reference for the editor.rs contract.

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
    /// Pointer button pressed.
    Press { at: [f32; 2], mods: Mods },
    /// Pointer moved with the button held.
    Drag { at: [f32; 2] },
    /// Pointer button released.
    Release { at: [f32; 2] },
    /// Polyline: finish the shape (Enter, or a double-click).
    Close,
    /// Polyline: remove the last vertex (Backspace).
    Back,
    /// Drop the shape in progress (Escape).
    Cancel,
    Undo,
    Redo,
    /// Clear the whole selection (Ctrl+D).
    Deselect,
}

/// A finished (or in-progress) shape and what it does.
#[derive(Debug, Clone, PartialEq)]
pub enum Item {
    Select(Op, Shape),
    Erase(Shape),
}

#[derive(Debug, Clone, PartialEq)]
enum Action {
    Item(Item),
    Deselect(Vec<(Op, Shape)>),
}

#[derive(Debug, Clone, PartialEq)]
struct Pending {
    tool: Tool,
    op: Op,
    points: Vec<[f32; 2]>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Editor {
    tool: Tool,
    radius: f32,
    close_radius: f32,
    pending: Option<Pending>,
    selection: Vec<(Op, Shape)>,
    erased: Vec<Shape>,
    done: Vec<Action>,
    undone: Vec<Action>,
}

impl Default for Editor {
    fn default() -> Self {
        Editor::new()
    }
}

fn op_for(mods: Mods) -> Op {
    if mods.ctrl {
        Op::Subtract
    } else if mods.shift {
        Op::Add
    } else {
        Op::Replace
    }
}

fn far(a: [f32; 2], b: [f32; 2], min: f32) -> bool {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    dx * dx + dy * dy >= min * min
}

impl Editor {
    /// Lasso, brush radius 12, close radius 8, nothing selected or erased.
    pub fn new() -> Editor {
        Editor {
            tool: Tool::Lasso,
            radius: 12.0,
            close_radius: 8.0,
            pending: None,
            selection: Vec::new(),
            erased: Vec::new(),
            done: Vec::new(),
            undone: Vec::new(),
        }
    }

    pub fn tool(&self) -> Tool {
        self.tool
    }

    /// Changing tool drops the shape in progress.
    pub fn set_tool(&mut self, tool: Tool) {
        self.pending = None;
        self.tool = tool;
    }

    pub fn radius(&self) -> f32 {
        self.radius
    }

    /// Brush and eraser radius, clamped to 1..=500; not finite is ignored.
    pub fn set_radius(&mut self, radius: f32) {
        if radius.is_finite() {
            self.radius = radius.clamp(1.0, 500.0);
        }
    }

    pub fn close_radius(&self) -> f32 {
        self.close_radius
    }

    /// How near the first vertex a polyline press closes it, clamped to 0..=100; not
    /// finite is ignored.
    pub fn set_close_radius(&mut self, radius: f32) {
        if radius.is_finite() {
            self.close_radius = radius.clamp(0.0, 100.0);
        }
    }

    pub fn selection(&self) -> &[(Op, Shape)] {
        &self.selection
    }

    pub fn erased(&self) -> &[Shape] {
        &self.erased
    }

    pub fn can_undo(&self) -> bool {
        !self.done.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.undone.is_empty()
    }

    /// The shape in progress, as it would be committed now.
    pub fn pending(&self) -> Option<Item> {
        let p = self.pending.as_ref()?;
        Some(match p.tool {
            Tool::Lasso | Tool::Polyline => Item::Select(p.op, Shape::Polygon(p.points.clone())),
            Tool::Brush => Item::Select(
                p.op,
                Shape::Stroke { points: p.points.clone(), radius: self.radius },
            ),
            Tool::Eraser => Item::Erase(Shape::Stroke { points: p.points.clone(), radius: self.radius }),
        })
    }

    /// select::build over the selection; None when nothing is selected.
    pub fn selection_mask(&self, width: u32, height: u32) -> Option<Mask> {
        build(width, height, &self.selection)
    }

    /// Every erased pixel; None when nothing is erased.
    pub fn erase_mask(&self, width: u32, height: u32) -> Option<Mask> {
        let ops: Vec<(Op, Shape)> = self.erased.iter().map(|s| (Op::Add, s.clone())).collect();
        build(width, height, &ops)
    }

    fn apply(&mut self, action: &Action) {
        match action {
            Action::Item(Item::Select(op, shape)) => self.selection.push((*op, shape.clone())),
            Action::Item(Item::Erase(shape)) => self.erased.push(shape.clone()),
            Action::Deselect(_) => self.selection.clear(),
        }
    }

    fn revert(&mut self, action: &Action) {
        match action {
            Action::Item(Item::Select(..)) => {
                self.selection.pop();
            }
            Action::Item(Item::Erase(_)) => {
                self.erased.pop();
            }
            Action::Deselect(saved) => self.selection = saved.clone(),
        }
    }

    fn commit(&mut self, action: Action) {
        self.apply(&action);
        self.done.push(action);
        self.undone.clear();
    }

    fn finish(&mut self) {
        let Some(item) = self.pending() else { return };
        let p = self.pending.take().unwrap();
        let enough = match p.tool {
            Tool::Lasso | Tool::Polyline => p.points.len() >= 3,
            Tool::Brush | Tool::Eraser => true,
        };
        if enough {
            self.commit(Action::Item(item));
        }
    }

    pub fn handle(&mut self, event: Event) {
        match event {
            Event::Press { at, mods } => {
                // Polyline in progress: Some(true) closes it, Some(false) adds a vertex.
                let closes = match (&self.pending, self.tool) {
                    (Some(p), Tool::Polyline) => {
                        Some(p.points.len() >= 3 && !far(p.points[0], at, self.close_radius))
                    }
                    _ => None,
                };
                match closes {
                    Some(true) => self.finish(),
                    Some(false) => {
                        let p = self.pending.as_mut().unwrap();
                        if far(*p.points.last().unwrap(), at, 1.0) {
                            p.points.push(at);
                        }
                    }
                    None => {
                        let tool = self.tool;
                        let op = if tool == Tool::Eraser { Op::Subtract } else { op_for(mods) };
                        self.pending = Some(Pending { tool, op, points: vec![at] });
                    }
                }
            }
            Event::Drag { at } => {
                let min = match self.tool {
                    Tool::Lasso => 1.0,
                    Tool::Brush | Tool::Eraser => (self.radius / 4.0).max(1.0),
                    Tool::Polyline => return,
                };
                if let Some(p) = &mut self.pending {
                    if far(*p.points.last().unwrap(), at, min) {
                        p.points.push(at);
                    }
                }
            }
            Event::Release { at } => {
                if self.tool == Tool::Polyline {
                    return;
                }
                if let Some(p) = &mut self.pending {
                    if *p.points.last().unwrap() != at {
                        p.points.push(at);
                    }
                    self.finish();
                }
            }
            Event::Close => {
                if self.tool == Tool::Polyline && self.pending.is_some() {
                    self.finish();
                    self.pending = None;
                }
            }
            Event::Back => {
                if self.tool == Tool::Polyline {
                    if let Some(p) = &mut self.pending {
                        p.points.pop();
                        if p.points.is_empty() {
                            self.pending = None;
                        }
                    }
                }
            }
            Event::Cancel => self.pending = None,
            Event::Undo => {
                if self.pending.take().is_some() {
                    return;
                }
                if let Some(a) = self.done.pop() {
                    self.revert(&a);
                    self.undone.push(a);
                }
            }
            Event::Redo => {
                self.pending = None;
                if let Some(a) = self.undone.pop() {
                    self.apply(&a);
                    self.done.push(a);
                }
            }
            Event::Deselect => {
                self.pending = None;
                if !self.selection.is_empty() {
                    let saved = self.selection.clone();
                    self.commit(Action::Deselect(saved));
                }
            }
        }
    }
}
