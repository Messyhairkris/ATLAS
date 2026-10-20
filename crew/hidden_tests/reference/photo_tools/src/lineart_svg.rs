//! Line art as SVG centerline strokes. Reference for the lineart_svg.rs contract.

use image::DynamicImage;

use crate::lineart;
use crate::options::{Error, LineArtOptions};
use crate::select::Mask;
use crate::smooth::{simplify, Pt};
use crate::strokes::trace;
use crate::svg::fmt_num;
use crate::thin::thin;

/// How the strokes are drawn.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StrokeOptions {
    /// Simplification tolerance in pixels; 0 draws straight lines through every corner
    /// (only points in a straight run are dropped, so nothing is lost).
    pub tolerance: f64,
    /// Stroke width in pixels.
    pub width: f64,
    /// Chains with fewer distinct pixels are dropped (specks).
    pub min_pixels: usize,
}

impl Default for StrokeOptions {
    fn default() -> Self {
        StrokeOptions { tolerance: 1.0, width: 1.0, min_pixels: 3 }
    }
}

fn invalid(name: &'static str, reason: &str) -> Error {
    Error::InvalidOption { name, reason: reason.to_string() }
}

impl StrokeOptions {
    pub fn validate(&self) -> Result<(), Error> {
        if !self.tolerance.is_finite() || !(0.0..=10.0).contains(&self.tolerance) {
            return Err(invalid("tolerance", "must be a number from 0 to 10"));
        }
        if !self.width.is_finite() || !(self.width > 0.0 && self.width <= 20.0) {
            return Err(invalid("stroke-width", "must be above 0 and at most 20"));
        }
        if self.min_pixels > 10_000 {
            return Err(invalid("min-pixels", "must be at most 10000"));
        }
        Ok(())
    }
}

/// One chain as SVG path data: pixel centres, simplified by `tolerance`, then straight
/// lines (tolerance 0) or Catmull-Rom cubics; a closed chain ends with Z.
pub fn chain_path(chain: &[(u32, u32)], tolerance: f64) -> String {
    let pts: Vec<Pt> = chain.iter().map(|&(x, y)| (x as f64 + 0.5, y as f64 + 0.5)).collect();
    let q = simplify(&pts, tolerance);
    let mut d = format!("M {} {}", fmt_num(q[0].0), fmt_num(q[0].1));
    if q.len() == 1 {
        d.push_str(&format!(" L {} {}", fmt_num(q[0].0), fmt_num(q[0].1)));
        return d;
    }
    let closed = q[0] == q[q.len() - 1] && q.len() > 2;
    let m = q.len() - 1;
    for i in 0..m {
        let (a, b) = (q[i], q[i + 1]);
        if tolerance == 0.0 {
            d.push_str(&format!(" L {} {}", fmt_num(b.0), fmt_num(b.1)));
            continue;
        }
        let p0 = if i > 0 { q[i - 1] } else if closed { q[m - 1] } else { a };
        let p3 = if i + 1 < m { q[i + 2] } else if closed { q[1] } else { b };
        let c1 = (a.0 + (b.0 - p0.0) / 6.0, a.1 + (b.1 - p0.1) / 6.0);
        let c2 = (b.0 - (p3.0 - a.0) / 6.0, b.1 - (p3.1 - a.1) / 6.0);
        d.push_str(&format!(
            " C {} {} {} {} {} {}",
            fmt_num(c1.0),
            fmt_num(c1.1),
            fmt_num(c2.0),
            fmt_num(c2.1),
            fmt_num(b.0),
            fmt_num(b.1)
        ));
    }
    if closed {
        d.push_str(" Z");
    }
    d
}

/// Line art (black on white), thinned and traced into stroked centerlines. Only
/// pixels inside `keep` are traced; the document has no background (transparent).
pub fn render_svg(
    img: &DynamicImage,
    opts: &LineArtOptions,
    stroke: &StrokeOptions,
    keep: Option<&Mask>,
) -> Result<String, Error> {
    opts.validate()?;
    stroke.validate()?;
    let gray = lineart::render(img, opts)?;
    let (w, h) = (gray.width(), gray.height());
    if let Some(m) = keep {
        if m.width() != w || m.height() != h {
            return Err(Error::InvalidOption {
                name: "selection",
                reason: format!("is {}x{} but the image is {}x{}", m.width(), m.height(), w, h),
            });
        }
    }
    let fg: Vec<bool> = gray
        .as_raw()
        .iter()
        .enumerate()
        .map(|(i, &v)| v == 0 && keep.is_none_or(|m| m.bits()[i]))
        .collect();
    let thinned = thin(&fg, w as usize, h as usize);
    let mut paths = Vec::new();
    for chain in trace(&thinned, w as usize, h as usize) {
        let distinct = if chain.len() > 1 && chain[0] == chain[chain.len() - 1] {
            chain.len() - 1
        } else {
            chain.len()
        };
        if distinct < stroke.min_pixels {
            continue;
        }
        paths.push(chain_path(&chain, stroke.tolerance));
    }
    let mut out = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" \
         viewBox=\"0 0 {w} {h}\">\n"
    );
    if !paths.is_empty() {
        out.push_str(&format!(
            "<path fill=\"none\" stroke=\"#000000\" stroke-width=\"{}\" \
             stroke-linecap=\"round\" stroke-linejoin=\"round\" d=\"{}\"/>\n",
            fmt_num(stroke.width),
            paths.join(" ")
        ));
    }
    out.push_str("</svg>\n");
    Ok(out)
}
