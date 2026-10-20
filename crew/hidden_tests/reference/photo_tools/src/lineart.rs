//! Line art: black edges on white. Reference for the lineart.rs contract.

use image::{DynamicImage, GrayImage};

use crate::luma::rgb_to_gray;
use crate::options::{EdgeFilter, Error, LineArtOptions};
use crate::sobel::edge_mask;

/// Validate, convert to gray (Rec. 601), blur, then Sobel or Canny.
pub fn render(img: &DynamicImage, opts: &LineArtOptions) -> Result<GrayImage, Error> {
    opts.validate()?;
    let (w, h) = (img.width(), img.height());
    if w == 0 || h == 0 {
        return Err(Error::EmptyImage);
    }
    let rgb = img.to_rgb8();
    let mut gray = GrayImage::from_raw(w, h, rgb_to_gray(rgb.as_raw())).ok_or(Error::EmptyImage)?;
    if opts.blur > 0.0 {
        gray = imageproc::filter::gaussian_blur_f32(&gray, opts.blur);
    }
    let out = match opts.filter {
        EdgeFilter::Sobel => {
            let threshold = opts.low.round().min(u16::MAX as f32) as u16;
            edge_mask(gray.as_raw(), w as usize, h as usize, threshold)
        }
        EdgeFilter::Canny => imageproc::edges::canny(&gray, opts.low, opts.high)
            .into_raw()
            .into_iter()
            .map(|v| 255 - v)
            .collect(),
    };
    GrayImage::from_raw(w, h, out).ok_or(Error::EmptyImage)
}
