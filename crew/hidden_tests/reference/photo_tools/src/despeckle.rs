//! Merge small regions of a label map into a neighbour. Reference for despeckle.rs.

/// Components are found once, on the input; small ones are merged in raster
/// order of their first pixel, each into the most common neighbouring label.
pub fn despeckle(labels: &[u8], width: usize, height: usize, min_area: usize) -> Vec<u8> {
    let mut out = labels.to_vec();
    if min_area <= 1 {
        return out;
    }
    let n = width * height;
    let mut comp = vec![usize::MAX; n];
    let mut members: Vec<Vec<usize>> = Vec::new();
    for start in 0..n {
        if comp[start] != usize::MAX {
            continue;
        }
        let id = members.len();
        let mut list = vec![start];
        comp[start] = id;
        let mut k = 0;
        while k < list.len() {
            let i = list[k];
            k += 1;
            for j in neighbours(i, width, height) {
                if comp[j] == usize::MAX && labels[j] == labels[start] {
                    comp[j] = id;
                    list.push(j);
                }
            }
        }
        members.push(list);
    }
    for (id, list) in members.iter().enumerate() {
        if list.len() >= min_area {
            continue;
        }
        let mut counts = [0usize; 256];
        let mut any = false;
        for &i in list {
            for j in neighbours(i, width, height) {
                if comp[j] != id {
                    counts[out[j] as usize] += 1;
                    any = true;
                }
            }
        }
        if !any {
            continue;
        }
        let mut best = 0usize;
        for (label, &c) in counts.iter().enumerate() {
            if c > counts[best] {
                best = label;
            }
        }
        for &i in list {
            out[i] = best as u8;
        }
    }
    out
}

fn neighbours(i: usize, width: usize, height: usize) -> Vec<usize> {
    let (x, y) = (i % width, i / width);
    let mut v = Vec::with_capacity(4);
    if x > 0 {
        v.push(i - 1);
    }
    if x + 1 < width {
        v.push(i + 1);
    }
    if y > 0 {
        v.push(i - width);
    }
    if y + 1 < height {
        v.push(i + width);
    }
    v
}
