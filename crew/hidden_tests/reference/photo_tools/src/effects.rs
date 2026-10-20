//! Sketch, dither, halftone, hatch and ASCII effects. Reference for effects.rs.

use image::{DynamicImage, GrayImage};

use crate::ascii;
use crate::dither::floyd_steinberg;
use crate::dodge::dodge_layers;
use crate::halftone::halftone;
use crate::hatch::hatch;
use crate::luma::{invert, rgb_to_gray};
use crate::options::{EffectOptions, Error, Style};

/// An effect's result: a gray image, or text for the ASCII style.
#[derive(Debug, Clone, PartialEq)]
pub enum EffectOutput {
    Image(GrayImage),
    Text(String),
}

pub fn render(img: &DynamicImage, opts: &EffectOptions) -> Result<EffectOutput, Error> {
    opts.validate()?;
    let (w, h) = (img.width(), img.height());
    if w == 0 || h == 0 {
        return Err(Error::EmptyImage);
    }
    let rgb = img.to_rgb8();
    let gray = rgb_to_gray(rgb.as_raw());
    let (wu, hu, cell) = (w as usize, h as usize, opts.cell as usize);
    let pixels = match opts.style {
        Style::Sketch => {
            let inv = GrayImage::from_raw(w, h, invert(&gray)).ok_or(Error::EmptyImage)?;
            let blurred = imageproc::filter::gaussian_blur_f32(&inv, opts.blur);
            dodge_layers(&gray, blurred.as_raw())
        }
        Style::Dither => floyd_steinberg(&gray, wu, hu),
        Style::Halftone => halftone(&gray, wu, hu, cell),
        Style::Hatch => hatch(&gray, wu, hu, cell),
        Style::Ascii => {
            let colour = if opts.ansi { Some(rgb.as_raw().as_slice()) } else { None };
            return Ok(EffectOutput::Text(ascii::render(
                &gray,
                colour,
                wu,
                hu,
                opts.columns as usize,
                opts.invert,
            )));
        }
    };
    GrayImage::from_raw(w, h, pixels).map(EffectOutput::Image).ok_or(Error::EmptyImage)
}
