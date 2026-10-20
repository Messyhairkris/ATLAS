//! Floyd-Steinberg error diffusion to one bit. Reference for the dither.rs contract.

/// Every output byte is 0 or 255. Rows top to bottom, each left to right.
pub fn floyd_steinberg(gray: &[u8], width: usize, height: usize) -> Vec<u8> {
    let mut buf: Vec<i32> = gray.iter().map(|&v| v as i32).collect();
    let mut out = vec![0u8; width * height];
    for y in 0..height {
        for x in 0..width {
            let i = y * width + x;
            let old = buf[i];
            let new = if old >= 128 { 255 } else { 0 };
            out[i] = new as u8;
            let err = old - new;
            if x + 1 < width {
                buf[i + 1] += err * 7 / 16;
            }
            if y + 1 < height {
                if x > 0 {
                    buf[i + width - 1] += err * 3 / 16;
                }
                buf[i + width] += err * 5 / 16;
                if x + 1 < width {
                    buf[i + width + 1] += err / 16;
                }
            }
        }
    }
    out
}
