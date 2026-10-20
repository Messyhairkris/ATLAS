//! Selections: lasso and polyline polygons, round brush strokes, and the pixel mask
//! they make. Reference for the select.rs contract.

use image::GrayImage;

/// One selection shape, in image pixel coordinates (pixel (x, y) covers x..x+1, y..y+1).
#[derive(Debug, Clone, PartialEq)]
pub enum Shape {
    /// A closed polygon (lasso or polyline): the last point joins the first.
    Polygon(Vec<[f32; 2]>),
    /// A round brush of `radius` dragged through `points` in order.
    Stroke { points: Vec<[f32; 2]>, radius: f32 },
}

/// How a shape changes the selection: no key, Shift, Ctrl.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Op {
    Replace,
    Add,
    Subtract,
}

/// One bool per pixel, row-major; true = selected.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Mask {
    width: u32,
    height: u32,
    bits: Vec<bool>,
}

impl Mask {
    /// Every pixel set to `value`.
    pub fn new(width: u32, height: u32, value: bool) -> Mask {
        Mask { width, height, bits: vec![value; width as usize * height as usize] }
    }

    /// None when `bits.len()` is not width * height.
    pub fn from_bits(width: u32, height: u32, bits: Vec<bool>) -> Option<Mask> {
        (bits.len() == width as usize * height as usize).then_some(Mask { width, height, bits })
    }

    /// A mask image: gray 128 and above is selected.
    pub fn from_luma(img: &GrayImage) -> Mask {
        Mask {
            width: img.width(),
            height: img.height(),
            bits: img.as_raw().iter().map(|&v| v >= 128).collect(),
        }
    }

    pub fn width(&self) -> u32 {
        self.width
    }

    pub fn height(&self) -> u32 {
        self.height
    }

    pub fn bits(&self) -> &[bool] {
        &self.bits
    }

    /// false outside the mask.
    pub fn get(&self, x: u32, y: u32) -> bool {
        x < self.width && y < self.height && self.bits[y as usize * self.width as usize + x as usize]
    }

    /// The number of selected pixels.
    pub fn count(&self) -> usize {
        self.bits.iter().filter(|&&b| b).count()
    }

    /// Replace: the shape alone. Add: union. Subtract: remove the shape's pixels.
    pub fn apply(&mut self, op: Op, shape: &Shape) {
        let r = rasterize(shape, self.width, self.height);
        for (b, s) in self.bits.iter_mut().zip(r) {
            *b = match op {
                Op::Replace => s,
                Op::Add => *b || s,
                Op::Subtract => *b && !s,
            };
        }
    }
}

fn finite(points: &[[f32; 2]]) -> bool {
    points.iter().all(|p| p[0].is_finite() && p[1].is_finite())
}

/// The pixels whose centres (x + 0.5, y + 0.5) the shape covers.
pub fn rasterize(shape: &Shape, width: u32, height: u32) -> Vec<bool> {
    let (w, h) = (width as usize, height as usize);
    let mut out = vec![false; w * h];
    match shape {
        Shape::Polygon(pts) => {
            if pts.len() < 3 || !finite(pts) {
                return out;
            }
            let p: Vec<(f64, f64)> = pts.iter().map(|q| (q[0] as f64, q[1] as f64)).collect();
            let mut cross: Vec<(f64, i32)> = Vec::new();
            for y in 0..h {
                let py = y as f64 + 0.5;
                cross.clear();
                for i in 0..p.len() {
                    let (a, b) = (p[i], p[(i + 1) % p.len()]);
                    let dir = if a.1 <= py && b.1 > py {
                        1
                    } else if b.1 <= py && a.1 > py {
                        -1
                    } else {
                        continue;
                    };
                    let x = a.0 + (py - a.1) * (b.0 - a.0) / (b.1 - a.1);
                    cross.push((x, dir));
                }
                if cross.is_empty() {
                    continue;
                }
                cross.sort_by(|s, t| s.0.partial_cmp(&t.0).unwrap());
                let total: i32 = cross.iter().map(|c| c.1).sum();
                let (mut k, mut passed) = (0, 0);
                for x in 0..w {
                    let px = x as f64 + 0.5;
                    while k < cross.len() && cross[k].0 <= px {
                        passed += cross[k].1;
                        k += 1;
                    }
                    out[y * w + x] = total - passed != 0;
                }
            }
        }
        Shape::Stroke { points, radius } => {
            if points.is_empty() || !finite(points) || !radius.is_finite() || *radius <= 0.0 {
                return out;
            }
            let r = *radius as f64;
            let p: Vec<(f64, f64)> = points.iter().map(|q| (q[0] as f64, q[1] as f64)).collect();
            let segs: Vec<((f64, f64), (f64, f64))> = if p.len() == 1 {
                vec![(p[0], p[0])]
            } else {
                p.windows(2).map(|s| (s[0], s[1])).collect()
            };
            for (a, b) in segs {
                let x0 = (a.0.min(b.0) - r - 1.0).floor().max(0.0);
                let x1 = (a.0.max(b.0) + r + 1.0).ceil().min(w as f64);
                let y0 = (a.1.min(b.1) - r - 1.0).floor().max(0.0);
                let y1 = (a.1.max(b.1) + r + 1.0).ceil().min(h as f64);
                if x0 >= x1 || y0 >= y1 {
                    continue;
                }
                let (dx, dy) = (b.0 - a.0, b.1 - a.1);
                let len2 = dx * dx + dy * dy;
                for y in y0 as usize..y1 as usize {
                    for x in x0 as usize..x1 as usize {
                        let (px, py) = (x as f64 + 0.5, y as f64 + 0.5);
                        let t = if len2 == 0.0 {
                            0.0
                        } else {
                            (((px - a.0) * dx + (py - a.1) * dy) / len2).clamp(0.0, 1.0)
                        };
                        let (qx, qy) = (a.0 + t * dx - px, a.1 + t * dy - py);
                        if qx * qx + qy * qy <= r * r {
                            out[y * w + x] = true;
                        }
                    }
                }
            }
        }
    }
    out
}

/// The selection a list of operations makes, applied in order. No operations: None
/// (nothing is selected, so everything is used). It starts empty, or full when the
/// first operation is Subtract (Ctrl with no selection removes from the whole image).
pub fn build(width: u32, height: u32, ops: &[(Op, Shape)]) -> Option<Mask> {
    let first = ops.first()?;
    let mut mask = Mask::new(width, height, first.0 == Op::Subtract);
    for (op, shape) in ops {
        mask.apply(*op, shape);
    }
    Some(mask)
}
