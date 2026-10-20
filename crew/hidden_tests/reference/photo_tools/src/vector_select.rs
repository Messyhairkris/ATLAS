//! Flat-colour SVG of the selected area only; the rest is left transparent.
//! Reference for the vector_select.rs contract.

use image::DynamicImage;

use crate::contour::trace;
use crate::despeckle::despeckle;
use crate::kmeans::quantize;
use crate::options::{Error, VectorOptions};
use crate::select::Mask;
use crate::smooth::smooth_loop;
use crate::svg::{hex, path_data};

/// Like vector::render, but the palette is fitted to the selected pixels only and
/// nothing outside the selection is drawn (no background rectangle).
pub fn render_selected(img: &DynamicImage, opts: &VectorOptions, keep: &Mask) -> Result<String, Error> {
    opts.validate()?;
    let (w, h) = (img.width(), img.height());
    if w == 0 || h == 0 {
        return Err(Error::EmptyImage);
    }
    if keep.width() != w || keep.height() != h {
        return Err(Error::InvalidOption {
            name: "selection",
            reason: format!("is {}x{} but the image is {}x{}", keep.width(), keep.height(), w, h),
        });
    }
    let mut out = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" \
         viewBox=\"0 0 {w} {h}\">\n"
    );
    if keep.count() > 0 {
        let (wu, hu) = (w as usize, h as usize);
        let rgb = img.to_rgb8();
        let mut chosen = Vec::with_capacity(keep.count() * 3);
        for (i, px) in rgb.as_raw().chunks_exact(3).enumerate() {
            if keep.bits()[i] {
                chosen.extend_from_slice(px);
            }
        }
        let palette = quantize(&chosen, opts.colors as usize, opts.max_iterations as usize);
        let outside = palette.colors.len() as u8;
        let mut next = palette.labels.iter();
        let labels: Vec<u8> = keep
            .bits()
            .iter()
            .map(|&k| if k { *next.next().unwrap() } else { outside })
            .collect();
        let mut labels = despeckle(&labels, wu, hu, opts.speckle as usize);
        for (l, &k) in labels.iter_mut().zip(keep.bits()) {
            if !k {
                *l = outside;
            }
        }
        let loops = trace(&labels, wu, hu);
        for (label, color) in palette.colors.iter().enumerate() {
            let segs: Vec<Vec<[f64; 8]>> = loops
                .iter()
                .filter(|l| l.label as usize == label)
                .map(|l| {
                    smooth_loop(&l.points, &l.junction, opts.smoothness as f64)
                        .iter()
                        .map(|c| [c.from.0, c.from.1, c.c1.0, c.c1.1, c.c2.0, c.c2.1, c.to.0, c.to.1])
                        .collect()
                })
                .collect();
            let d = path_data(&segs);
            if !d.is_empty() {
                out.push_str(&format!(
                    "<path fill=\"{}\" fill-rule=\"evenodd\" d=\"{d}\"/>\n",
                    hex(*color)
                ));
            }
        }
    }
    out.push_str("</svg>\n");
    Ok(out)
}
