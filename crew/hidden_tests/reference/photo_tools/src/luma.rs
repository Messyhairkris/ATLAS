//! Gray levels from RGB, and inversion. Reference for the luma.rs contract.

/// Rec. 601 luma of one pixel, rounded: `(299 r + 587 g + 114 b + 500) / 1000`.
pub fn luma(r: u8, g: u8, b: u8) -> u8 {
    ((299 * r as u32 + 587 * g as u32 + 114 * b as u32 + 500) / 1000) as u8
}

/// One gray byte per complete RGB triple; a trailing partial triple is ignored.
pub fn rgb_to_gray(rgb: &[u8]) -> Vec<u8> {
    rgb.chunks_exact(3).map(|p| luma(p[0], p[1], p[2])).collect()
}

/// `255 - v` for every byte.
pub fn invert(gray: &[u8]) -> Vec<u8> {
    gray.iter().map(|&v| 255 - v).collect()
}
