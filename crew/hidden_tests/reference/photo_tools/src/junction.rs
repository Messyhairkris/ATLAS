//! Where region borders meet. Reference for the junction.rs contract.

const OUTSIDE: i32 = -1;

fn cell(labels: &[u8], width: usize, height: usize, x: i64, y: i64) -> i32 {
    if x < 0 || y < 0 || x >= width as i64 || y >= height as i64 {
        OUTSIDE
    } else {
        labels[y as usize * width + x as usize] as i32
    }
}

/// True where three or more values meet (outside counts as one value), or at a
/// checkerboard saddle of two labels with all four cells inside the image.
pub fn is_junction(labels: &[u8], width: usize, height: usize, x: usize, y: usize) -> bool {
    let (x, y) = (x as i64, y as i64);
    let nw = cell(labels, width, height, x - 1, y - 1);
    let ne = cell(labels, width, height, x, y - 1);
    let sw = cell(labels, width, height, x - 1, y);
    let se = cell(labels, width, height, x, y);
    let mut vals = vec![nw, ne, sw, se];
    vals.sort_unstable();
    vals.dedup();
    if vals.len() >= 3 {
        return true;
    }
    vals.len() == 2 && !vals.contains(&OUTSIDE) && nw == se && ne == sw
}
