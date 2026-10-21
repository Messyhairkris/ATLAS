// 3.14159 is a rounding input for fmt_num, not an approximation of PI.
#![allow(clippy::approx_constant)]

use photo_tools::svg::{document, fmt_num, hex, path_data};

#[test]
fn number_formatting_table() {
    let rows: [(f64, &str); 16] = [
        (0.0, "0"),
        (1.5, "1.5"),
        (2.0, "2"),
        (-0.001, "0"),
        (-0.0, "0"),
        (3.14159, "3.14"),
        (-1.25, "-1.25"),
        (10.1, "10.1"),
        (0.07, "0.07"),
        (-0.5, "-0.5"),
        (1234.5678, "1234.57"),
        (0.005, "0.01"),
        (0.004999, "0"),
        (2.0 / 3.0, "0.67"),
        (100.0, "100"),
        (-7.999, "-8"),
    ];
    for (v, want) in rows {
        assert_eq!(fmt_num(v), want, "fmt_num({v})");
    }
}

#[test]
fn hex_is_lowercase_and_padded() {
    assert_eq!(hex([255, 0, 16]), "#ff0010");
    assert_eq!(hex([0, 0, 0]), "#000000");
    assert_eq!(hex([171, 205, 239]), "#abcdef");
}

#[test]
fn path_data_one_loop() {
    let loops = vec![vec![[0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0]]];
    assert_eq!(path_data(&loops), "M 0 0 C 1 0 2 0 3 0 Z");
}

#[test]
fn path_data_moves_to_the_first_segment_start() {
    let loops = vec![vec![
        [1.0, 2.0, 1.5, 2.0, 2.5, 2.5, 3.0, 3.0],
        [3.0, 3.0, 2.0, 3.333, 1.0, 2.666, 1.0, 2.0],
    ]];
    assert_eq!(
        path_data(&loops),
        "M 1 2 C 1.5 2 2.5 2.5 3 3 C 2 3.33 1 2.67 1 2 Z"
    );
}

#[test]
fn path_data_several_loops_and_empty_ones() {
    let a = vec![[0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0]];
    let b = vec![[5.0, 5.0, 6.0, 5.0, 6.0, 6.0, 5.0, 6.0]];
    assert_eq!(
        path_data(&[a, vec![], b]),
        "M 0 0 C 0 1 1 1 1 0 Z M 5 5 C 6 5 6 6 5 6 Z"
    );
    assert_eq!(path_data(&[]), "");
    assert_eq!(path_data(&[vec![]]), "");
}

#[test]
fn document_exact_text() {
    let shapes = vec![
        ([255, 0, 0], "M 0 0 C 1 0 1 0 1 1 Z".to_string()),
        ([0, 0, 255], String::new()),
        ([0, 128, 0], "M 1 1 C 2 1 2 1 2 2 Z".to_string()),
    ];
    let want = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"3\" height=\"2\" viewBox=\"0 0 3 2\">\n\
<rect width=\"3\" height=\"2\" fill=\"#ffffff\"/>\n\
<path fill=\"#ff0000\" fill-rule=\"evenodd\" d=\"M 0 0 C 1 0 1 0 1 1 Z\"/>\n\
<path fill=\"#008000\" fill-rule=\"evenodd\" d=\"M 1 1 C 2 1 2 1 2 2 Z\"/>\n\
</svg>\n";
    assert_eq!(document(3, 2, [255, 255, 255], &shapes), want);
}

#[test]
fn document_with_no_shapes() {
    assert_eq!(
        document(1, 1, [1, 2, 3], &[]),
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1\" height=\"1\" viewBox=\"0 0 1 1\">\n\
<rect width=\"1\" height=\"1\" fill=\"#010203\"/>\n</svg>\n"
    );
}
