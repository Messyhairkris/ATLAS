//! Selections as text, one shape per line, so the CLI can use selections drawn in the
//! editor. Reference for the shapes_file.rs contract.

use crate::options::Error;
use crate::select::{Op, Shape};

/// A saved selection: the selection operations in order, and the eraser strokes.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Selection {
    pub ops: Vec<(Op, Shape)>,
    pub erased: Vec<Shape>,
}

fn fail(line: usize, reason: String) -> Error {
    Error::InvalidOption { name: "selection", reason: format!("line {line}: {reason}") }
}

fn point(tok: &str, line: usize) -> Result<[f32; 2], Error> {
    let bad = || fail(line, format!("bad point \"{tok}\" (write x,y)"));
    let (x, y) = tok.split_once(',').ok_or_else(bad)?;
    let x: f32 = x.parse().map_err(|_| bad())?;
    let y: f32 = y.parse().map_err(|_| bad())?;
    if x.is_finite() && y.is_finite() {
        Ok([x, y])
    } else {
        Err(bad())
    }
}

/// Parse the text. Blank lines and everything after `#` are ignored.
pub fn parse(text: &str) -> Result<Selection, Error> {
    let mut sel = Selection::default();
    for (i, raw) in text.split('\n').enumerate() {
        let n = i + 1;
        let body = raw.split('#').next().unwrap_or("");
        let toks: Vec<&str> = body.split_whitespace().collect();
        if toks.is_empty() {
            continue;
        }
        let op = match toks[0] {
            "replace" => Some(Op::Replace),
            "add" => Some(Op::Add),
            "subtract" => Some(Op::Subtract),
            "erase" => None,
            other => {
                return Err(fail(
                    n,
                    format!("unknown action \"{other}\" (use replace, add, subtract or erase)"),
                ))
            }
        };
        let kind = toks.get(1).copied().unwrap_or("");
        let shape = match kind {
            "polygon" => {
                if op.is_none() {
                    return Err(fail(n, "erase takes a stroke".to_string()));
                }
                let pts = toks[2..].iter().map(|t| point(t, n)).collect::<Result<Vec<_>, _>>()?;
                if pts.len() < 3 {
                    return Err(fail(n, "a polygon needs at least 3 points".to_string()));
                }
                Shape::Polygon(pts)
            }
            "stroke" => {
                let tok = toks.get(2).copied().unwrap_or("");
                let radius: f32 = tok
                    .parse()
                    .ok()
                    .filter(|r: &f32| r.is_finite() && *r > 0.0)
                    .ok_or_else(|| fail(n, format!("bad radius \"{tok}\"")))?;
                let pts = toks[3.min(toks.len())..]
                    .iter()
                    .map(|t| point(t, n))
                    .collect::<Result<Vec<_>, _>>()?;
                if pts.is_empty() {
                    return Err(fail(n, "a stroke needs at least 1 point".to_string()));
                }
                Shape::Stroke { points: pts, radius }
            }
            other => {
                return Err(fail(n, format!("unknown shape \"{other}\" (use polygon or stroke)")))
            }
        };
        match op {
            Some(op) => sel.ops.push((op, shape)),
            None => sel.erased.push(shape),
        }
    }
    Ok(sel)
}

fn points(pts: &[[f32; 2]]) -> String {
    pts.iter().map(|p| format!(" {},{}", p[0], p[1])).collect()
}

fn shape_text(shape: &Shape) -> String {
    match shape {
        Shape::Polygon(pts) => format!("polygon{}", points(pts)),
        Shape::Stroke { points: pts, radius } => format!("stroke {radius}{}", points(pts)),
    }
}

/// The text form: a header comment, the operations in order, then the eraser strokes.
/// parse(write(s)) == s for any selection parse could have produced.
pub fn write(sel: &Selection) -> String {
    let mut out = String::from("# photo_tools selection\n");
    for (op, shape) in &sel.ops {
        let word = match op {
            Op::Replace => "replace",
            Op::Add => "add",
            Op::Subtract => "subtract",
        };
        out.push_str(&format!("{word} {}\n", shape_text(shape)));
    }
    for shape in &sel.erased {
        out.push_str(&format!("erase {}\n", shape_text(shape)));
    }
    out
}
