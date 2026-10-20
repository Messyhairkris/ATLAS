//! Raster to flat-colour SVG. Reference for the vector.rs contract.

use image::DynamicImage;

use crate::contour::trace;
use crate::despeckle::despeckle;
use crate::kmeans::quantize;
use crate::options::{Error, VectorOptions};
use crate::smooth::smooth_loop;
use crate::svg::{document, path_data};

pub fn render(img: &DynamicImage, opts: &VectorOptions) -> Result<String, Error> {
    opts.validate()?;
    let (w, h) = (img.width(), img.height());
    if w == 0 || h == 0 {
        return Err(Error::EmptyImage);
    }
    let (wu, hu) = (w as usize, h as usize);
    let rgb = img.to_rgb8();
    let palette = quantize(rgb.as_raw(), opts.colors as usize, opts.max_iterations as usize);
    let labels = despeckle(&palette.labels, wu, hu, opts.speckle as usize);
    let mut counts = vec![0usize; palette.colors.len()];
    for &l in &labels {
        counts[l as usize] += 1;
    }
    let mut biggest = 0;
    for (i, &c) in counts.iter().enumerate() {
        if c > counts[biggest] {
            biggest = i;
        }
    }
    let loops = trace(&labels, wu, hu);
    let mut shapes = Vec::new();
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
        shapes.push((*color, path_data(&segs)));
    }
    Ok(document(w, h, palette.colors[biggest], &shapes))
}
