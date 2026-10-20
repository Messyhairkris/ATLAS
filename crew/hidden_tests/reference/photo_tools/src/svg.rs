//! SVG text output. Reference for the svg.rs contract.

/// `v` rounded to 2 decimals, without trailing zeros: 1.5 -> "1.5", 2.0 -> "2",
/// -0.001 -> "0", 3.14159 -> "3.14".
pub fn fmt_num(v: f64) -> String {
    let r = (v * 100.0).round() as i64;
    let (whole, frac) = (r.abs() / 100, r.abs() % 100);
    let sign = if r < 0 { "-" } else { "" };
    if frac == 0 {
        format!("{sign}{whole}")
    } else if frac % 10 == 0 {
        format!("{sign}{whole}.{}", frac / 10)
    } else {
        format!("{sign}{whole}.{frac:02}")
    }
}

/// "#rrggbb", lowercase.
pub fn hex(color: [u8; 3]) -> String {
    format!("#{:02x}{:02x}{:02x}", color[0], color[1], color[2])
}

/// Path data for closed loops of cubic segments [x0, y0, c1x, c1y, c2x, c2y, x1, y1].
pub fn path_data(loops: &[Vec<[f64; 8]>]) -> String {
    let mut parts = Vec::new();
    for segs in loops.iter().filter(|s| !s.is_empty()) {
        let mut d = format!("M {} {}", fmt_num(segs[0][0]), fmt_num(segs[0][1]));
        for s in segs {
            d.push_str(" C");
            for v in &s[2..] {
                d.push(' ');
                d.push_str(&fmt_num(*v));
            }
        }
        d.push_str(" Z");
        parts.push(d);
    }
    parts.join(" ")
}

/// A whole SVG document: a background rectangle, then one path per shape.
pub fn document(width: u32, height: u32, background: [u8; 3], shapes: &[([u8; 3], String)]) -> String {
    let mut out = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" \
         viewBox=\"0 0 {width} {height}\">\n<rect width=\"{width}\" height=\"{height}\" \
         fill=\"{}\"/>\n",
        hex(background)
    );
    for (color, d) in shapes.iter().filter(|(_, d)| !d.is_empty()) {
        out.push_str(&format!(
            "<path fill=\"{}\" fill-rule=\"evenodd\" d=\"{d}\"/>\n",
            hex(*color)
        ));
    }
    out.push_str("</svg>\n");
    out
}
