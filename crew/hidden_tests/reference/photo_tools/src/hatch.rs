//! Cross-hatching. Reference for the hatch.rs contract.

/// Black (0) hatch lines on white (255); darker pixels collect more layers.
pub fn hatch(gray: &[u8], width: usize, height: usize, spacing: usize) -> Vec<u8> {
    let s = spacing.max(2);
    let mut out = vec![255u8; width * height];
    for y in 0..height {
        for x in 0..width {
            let v = gray[y * width + x];
            let black = (v < 192 && (x + y) % s == 0)
                || (v < 128 && x % s == y % s)
                || (v < 64 && y % s == 0)
                || (v < 32 && x % s == 0);
            if black {
                out[y * width + x] = 0;
            }
        }
    }
    out
}
