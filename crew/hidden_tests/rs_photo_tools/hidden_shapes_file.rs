use photo_tools::options::Error;
use photo_tools::select::{Op, Shape};
use photo_tools::shapes_file::{parse, write, Selection};

fn err(reason: &str) -> Result<Selection, Error> {
    Err(Error::InvalidOption { name: "selection", reason: reason.to_string() })
}

fn poly(p: &[[f32; 2]]) -> Shape {
    Shape::Polygon(p.to_vec())
}

fn stroke(p: &[[f32; 2]], radius: f32) -> Shape {
    Shape::Stroke { points: p.to_vec(), radius }
}

#[test]
fn polygon_line() {
    assert_eq!(
        parse("replace polygon 1,1 3,1 3,3"),
        Ok(Selection { ops: vec![(Op::Replace, poly(&[[1.0, 1.0], [3.0, 1.0], [3.0, 3.0]]))], erased: vec![] })
    );
}

#[test]
fn stroke_comment_blank_and_erase() {
    let s = parse("add stroke 4 10,10 20,10\n  # note\n\nerase stroke 2.5 5,5").unwrap();
    assert_eq!(s.ops, vec![(Op::Add, stroke(&[[10.0, 10.0], [20.0, 10.0]], 4.0))]);
    assert_eq!(s.erased, vec![stroke(&[[5.0, 5.0]], 2.5)]);
}

#[test]
fn tail_comment_and_subtract() {
    assert_eq!(
        parse("subtract polygon 0,0 4,0 4,4 # tail comment").unwrap().ops,
        vec![(Op::Subtract, poly(&[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]]))]
    );
}

#[test]
fn any_whitespace_and_crlf() {
    let s = parse("replace polygon 1,1\t3,1  3,3\r\nadd stroke 2 0,0\r\n").unwrap();
    assert_eq!(s.ops.len(), 2);
    assert_eq!(s.ops[0], (Op::Replace, poly(&[[1.0, 1.0], [3.0, 1.0], [3.0, 3.0]])));
    assert_eq!(s.ops[1], (Op::Add, stroke(&[[0.0, 0.0]], 2.0)));
}

#[test]
fn empty_and_comment_only() {
    assert_eq!(parse(""), Ok(Selection::default()));
    assert_eq!(parse("# only a comment"), Ok(Selection::default()));
    assert_eq!(parse("\n\n   \n#x\n"), Ok(Selection::default()));
}

#[test]
fn negative_and_fractional_numbers() {
    let s = parse("add polygon -1.5,2 3e1,-0.25 .5,7").unwrap();
    assert_eq!(s.ops[0].1, poly(&[[-1.5, 2.0], [30.0, -0.25], [0.5, 7.0]]));
}

#[test]
fn errors_count_lines_from_one_including_blank_ones() {
    assert_eq!(
        parse("\nmove polygon 1,1 2,2 3,3"),
        err("line 2: unknown action \"move\" (use replace, add, subtract or erase)")
    );
    assert_eq!(
        parse("add polygon 1,1 2,2 3,3\n# c\n\nAdd polygon 1,1 2,2 3,3"),
        err("line 4: unknown action \"Add\" (use replace, add, subtract or erase)")
    );
}

#[test]
fn shape_errors() {
    assert_eq!(parse("add"), err("line 1: unknown shape \"\" (use polygon or stroke)"));
    assert_eq!(parse("add circle 1,1"), err("line 1: unknown shape \"circle\" (use polygon or stroke)"));
    assert_eq!(parse("erase polygon 1,1 2,2 3,3"), err("line 1: erase takes a stroke"));
    assert_eq!(parse("erase polygon"), err("line 1: erase takes a stroke"));
}

#[test]
fn radius_errors() {
    assert_eq!(parse("add stroke 0 1,1"), err("line 1: bad radius \"0\""));
    assert_eq!(parse("add stroke -3 1,1"), err("line 1: bad radius \"-3\""));
    assert_eq!(parse("add stroke"), err("line 1: bad radius \"\""));
    assert_eq!(parse("add stroke NaN 1,1"), err("line 1: bad radius \"NaN\""));
    assert_eq!(parse("add stroke inf 1,1"), err("line 1: bad radius \"inf\""));
    assert_eq!(parse("add stroke 1,1 2,2"), err("line 1: bad radius \"1,1\""));
}

#[test]
fn count_errors() {
    assert_eq!(parse("add stroke 3"), err("line 1: a stroke needs at least 1 point"));
    assert_eq!(parse("add polygon 1,1 2,2"), err("line 1: a polygon needs at least 3 points"));
    assert_eq!(parse("add polygon"), err("line 1: a polygon needs at least 3 points"));
}

#[test]
fn point_errors() {
    assert_eq!(parse("add polygon 1,1 2;2 3,3"), err("line 1: bad point \"2;2\" (write x,y)"));
    assert_eq!(parse("add polygon 1,1 2,inf 3,3"), err("line 1: bad point \"2,inf\" (write x,y)"));
    assert_eq!(parse("add polygon 1,1,1 2,2 3,3"), err("line 1: bad point \"1,1,1\" (write x,y)"));
    assert_eq!(parse("add polygon 1, 2,2 3,3"), err("line 1: bad point \"1,\" (write x,y)"));
    assert_eq!(parse("add stroke 2 x,1"), err("line 1: bad point \"x,1\" (write x,y)"));
}

#[test]
fn bad_point_is_reported_before_the_count() {
    assert_eq!(parse("add polygon 1,1 zz"), err("line 1: bad point \"zz\" (write x,y)"));
}

#[test]
fn first_error_wins() {
    assert_eq!(
        parse("add polygon 1,1\nmove x"),
        err("line 1: a polygon needs at least 3 points")
    );
}

#[test]
fn write_exact() {
    let s = Selection {
        ops: vec![
            (Op::Replace, poly(&[[1.0, 1.0], [3.0, 1.0], [3.0, 3.0]])),
            (Op::Subtract, stroke(&[[2.0, 2.0]], 1.5)),
        ],
        erased: vec![stroke(&[[0.25, 7.0], [8.0, 9.0]], 3.0)],
    };
    assert_eq!(
        write(&s),
        "# photo_tools selection\nreplace polygon 1,1 3,1 3,3\nsubtract stroke 1.5 2,2\nerase stroke 3 0.25,7 8,9\n"
    );
}

#[test]
fn write_empty() {
    assert_eq!(write(&Selection::default()), "# photo_tools selection\n");
}

#[test]
fn write_add_word() {
    let s = Selection { ops: vec![(Op::Add, poly(&[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))], erased: vec![] };
    assert_eq!(write(&s), "# photo_tools selection\nadd polygon 0,0 1,0 0,1\n");
}

#[test]
fn round_trip_of_awkward_numbers() {
    let mut x: u32 = 12345;
    let mut next = || {
        x = x.wrapping_mul(1664525).wrapping_add(1013904223);
        (x as f32 / u32::MAX as f32) * 4000.0 - 500.0
    };
    for _ in 0..20 {
        let s = Selection {
            ops: vec![
                (Op::Replace, Shape::Polygon((0..7).map(|_| [next(), next()]).collect())),
                (Op::Add, Shape::Stroke { points: (0..3).map(|_| [next(), next()]).collect(), radius: next().abs() + 0.001 }),
                (Op::Subtract, Shape::Polygon(vec![[0.1, 0.2], [1e-7, 3.4028235e38], [-0.0, 7.0]])),
            ],
            erased: vec![Shape::Stroke { points: vec![[next(), next()]], radius: 0.3 }],
        };
        assert_eq!(parse(&write(&s)), Ok(s));
    }
}
