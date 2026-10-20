//! Color Dodge blending. Reference for the dodge.rs contract.

/// Color Dodge of one channel. Rules in order, first match wins:
/// 1. base == 0 -> 0. 2. blend == 255 -> 255.
/// 3. min(255, (base * 255 + d / 2) / d) with d = 255 - blend, in u32.
pub fn color_dodge(base: u8, blend: u8) -> u8 {
    if base == 0 {
        return 0;
    }
    if blend == 255 {
        return 255;
    }
    let d = 255 - blend as u32;
    ((base as u32 * 255 + d / 2) / d).min(255) as u8
}

/// color_dodge pairwise; the result is as long as the shorter input.
pub fn dodge_layers(base: &[u8], blend: &[u8]) -> Vec<u8> {
    base.iter().zip(blend).map(|(&a, &b)| color_dodge(a, b)).collect()
}
