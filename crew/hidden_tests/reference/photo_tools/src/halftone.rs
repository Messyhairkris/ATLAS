//! Amplitude-modulated halftone dots. Reference for the halftone.rs contract.

/// One black dot per cell, its area following the cell's darkness.
pub fn halftone(gray: &[u8], width: usize, height: usize, cell: usize) -> Vec<u8> {
    let c = cell.max(2);
    let mut out = vec![255u8; width * height];
    for cy in 0..height.div_ceil(c) {
        for cx in 0..width.div_ceil(c) {
            let (x0, y0) = (cx * c, cy * c);
            let (x1, y1) = ((x0 + c).min(width), (y0 + c).min(height));
            let mut sum = 0u32;
            for y in y0..y1 {
                for x in x0..x1 {
                    sum += gray[y * width + x] as u32;
                }
            }
            let mean = sum / ((x1 - x0) * (y1 - y0)) as u32;
            let darkness = (255 - mean) as f64 / 255.0;
            let r = c as f64 * 0.5 * std::f64::consts::SQRT_2 * darkness.sqrt();
            let (mx, my) = (x0 as f64 + c as f64 / 2.0, y0 as f64 + c as f64 / 2.0);
            for y in y0..y1 {
                for x in x0..x1 {
                    let (dx, dy) = (x as f64 + 0.5 - mx, y as f64 + 0.5 - my);
                    if dx * dx + dy * dy < r * r {
                        out[y * width + x] = 0;
                    }
                }
            }
        }
    }
    out
}
