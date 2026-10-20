//! Selections and erasing applied to rendered images: outside is transparent white.
//! Reference for the composite.rs contract.

use image::{GrayAlphaImage, GrayImage, LumaA};

use crate::options::Error;
use crate::select::Mask;

fn same_size(mask: &Mask, width: u32, height: u32) -> Result<(), Error> {
    if mask.width() == width && mask.height() == height {
        Ok(())
    } else {
        Err(Error::InvalidOption {
            name: "selection",
            reason: format!(
                "is {}x{} but the image is {}x{}",
                mask.width(),
                mask.height(),
                width,
                height
            ),
        })
    }
}

/// Every pixel opaque: (v, 255).
pub fn opaque(img: &GrayImage) -> GrayAlphaImage {
    GrayAlphaImage::from_fn(img.width(), img.height(), |x, y| LumaA([img.get_pixel(x, y)[0], 255]))
}

/// Selected pixels keep their value, opaque; the rest become transparent white (255, 0).
pub fn keep(img: &GrayImage, keep: &Mask) -> Result<GrayAlphaImage, Error> {
    same_size(keep, img.width(), img.height())?;
    Ok(GrayAlphaImage::from_fn(img.width(), img.height(), |x, y| {
        if keep.get(x, y) {
            LumaA([img.get_pixel(x, y)[0], 255])
        } else {
            LumaA([255, 0])
        }
    }))
}

/// Erased pixels (true in `erased`) become transparent white (255, 0).
pub fn erase(img: &mut GrayAlphaImage, erased: &Mask) -> Result<(), Error> {
    same_size(erased, img.width(), img.height())?;
    for (x, y, p) in img.enumerate_pixels_mut() {
        if erased.get(x, y) {
            *p = LumaA([255, 0]);
        }
    }
    Ok(())
}

/// For formats without transparency (JPEG): transparent pixels become white 255.
pub fn flatten(img: &GrayAlphaImage) -> GrayImage {
    GrayImage::from_fn(img.width(), img.height(), |x, y| {
        let p = img.get_pixel(x, y);
        image::Luma([if p[1] == 0 { 255 } else { p[0] }])
    })
}

/// Before ASCII art: unselected pixels of a row-major gray buffer become blank -
/// 255, or 0 when the art is inverted - so cells outside the selection print spaces.
pub fn blank_outside(gray: &mut [u8], keep: &Mask, invert: bool) -> Result<(), Error> {
    if gray.len() != keep.bits().len() {
        return Err(Error::InvalidOption {
            name: "selection",
            reason: format!("has {} pixels but the image has {}", keep.bits().len(), gray.len()),
        });
    }
    let blank = if invert { 0 } else { 255 };
    for (g, &k) in gray.iter_mut().zip(keep.bits()) {
        if !k {
            *g = blank;
        }
    }
    Ok(())
}
