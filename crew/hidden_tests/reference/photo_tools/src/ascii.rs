//! Text art from cell brightness. Reference for the ascii.rs contract.

/// Lightest to darkest.
pub const RAMP: &[u8] = b" .:-=+*#%@";

/// (cell_w, cell_h, cols, rows) for an image and a requested column count.
pub fn grid(width: usize, height: usize, columns: usize) -> (usize, usize, usize, usize) {
    if width == 0 || height == 0 {
        return (0, 0, 0, 0);
    }
    let columns = columns.clamp(1, width);
    let cell_w = width / columns;
    let mut cell_h = cell_w * 2;
    if height < cell_h {
        cell_h = height;
    }
    (cell_w, cell_h, width / cell_w, height / cell_h)
}

/// One line per row of cells, each ending in "\n". With `rgb`, every character is
/// preceded by a 24-bit colour escape and every line ends with a reset.
pub fn render(
    gray: &[u8],
    rgb: Option<&[u8]>,
    width: usize,
    height: usize,
    columns: usize,
    invert: bool,
) -> String {
    let (cw, ch, cols, rows) = grid(width, height, columns);
    let mut out = String::new();
    for row in 0..rows {
        for col in 0..cols {
            let (mut sum, mut rgb_sum, mut count) = (0u32, [0u32; 3], 0u32);
            for y in row * ch..(row + 1) * ch {
                for x in col * cw..(col + 1) * cw {
                    let i = y * width + x;
                    sum += gray[i] as u32;
                    if let Some(c) = rgb {
                        for k in 0..3 {
                            rgb_sum[k] += c[i * 3 + k] as u32;
                        }
                    }
                    count += 1;
                }
            }
            let mean = sum / count;
            let index = if invert { mean * 9 / 255 } else { (255 - mean) * 9 / 255 };
            if rgb.is_some() {
                let [r, g, b] = rgb_sum.map(|s| s / count);
                out.push_str(&format!("\x1b[38;2;{r};{g};{b}m"));
            }
            out.push(RAMP[index as usize] as char);
        }
        if rgb.is_some() {
            out.push_str("\x1b[0m");
        }
        out.push('\n');
    }
    out
}
