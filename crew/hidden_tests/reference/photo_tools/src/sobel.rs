//! Sobel gradient magnitude and edge mask. Reference for the sobel.rs contract.

const KX: [[i32; 3]; 3] = [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]];
const KY: [[i32; 3]; 3] = [[-1, -2, -1], [0, 0, 0], [1, 2, 1]];

/// round(sqrt(gx^2 + gy^2)) per pixel; samples outside the image use the nearest
/// edge pixel (coordinates clamped).
pub fn magnitude(gray: &[u8], width: usize, height: usize) -> Vec<u16> {
    let mut out = Vec::with_capacity(width * height);
    for y in 0..height {
        for x in 0..width {
            let (mut gx, mut gy) = (0i32, 0i32);
            for (j, (rx, ry)) in KX.iter().zip(KY.iter()).enumerate() {
                let sy = (y + j).saturating_sub(1).min(height - 1);
                for i in 0..3 {
                    let sx = (x + i).saturating_sub(1).min(width - 1);
                    let p = gray[sy * width + sx] as i32;
                    gx += rx[i] * p;
                    gy += ry[i] * p;
                }
            }
            out.push(((gx * gx + gy * gy) as f64).sqrt().round() as u16);
        }
    }
    out
}

/// 0 (black) where magnitude >= threshold, else 255 (white).
pub fn edge_mask(gray: &[u8], width: usize, height: usize, threshold: u16) -> Vec<u8> {
    magnitude(gray, width, height)
        .into_iter()
        .map(|m| if m >= threshold { 0 } else { 255 })
        .collect()
}
