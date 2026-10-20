use photo_tools::options::{
    parse_threshold, EdgeFilter, EffectOptions, Error, Job, LineArtOptions, Style, VectorOptions,
};

fn bad(name: &'static str, reason: &str) -> Error {
    Error::InvalidOption { name, reason: reason.to_string() }
}

#[test]
fn defaults() {
    assert_eq!(
        LineArtOptions::default(),
        LineArtOptions { filter: EdgeFilter::Canny, blur: 1.0, low: 50.0, high: 100.0 }
    );
    assert_eq!(
        VectorOptions::default(),
        VectorOptions { colors: 8, smoothness: 1.0, speckle: 8, max_iterations: 20 }
    );
    assert_eq!(
        EffectOptions::default(),
        EffectOptions { style: Style::Sketch, blur: 8.0, cell: 6, columns: 100, ansi: false, invert: false }
    );
    assert_eq!(LineArtOptions::default().validate(), Ok(()));
    assert_eq!(VectorOptions::default().validate(), Ok(()));
    assert_eq!(EffectOptions::default().validate(), Ok(()));
}

#[test]
fn display_texts() {
    assert_eq!(bad("colors", "must be from 2 to 64").to_string(), "invalid --colors: must be from 2 to 64");
    assert_eq!(Error::EmptyImage.to_string(), "the image has no pixels");
    let as_std: &dyn std::error::Error = &Error::EmptyImage;
    assert_eq!(as_std.to_string(), "the image has no pixels");
}

#[test]
fn line_art_rules() {
    let ok = LineArtOptions::default();
    let blur = "must be a number from 0 to 50";
    for b in [-0.1, 50.1, f32::NAN, f32::INFINITY] {
        assert_eq!(LineArtOptions { blur: b, ..ok }.validate(), Err(bad("blur", blur)));
    }
    assert_eq!(LineArtOptions { blur: 0.0, ..ok }.validate(), Ok(()));
    assert_eq!(LineArtOptions { blur: 50.0, ..ok }.validate(), Ok(()));
    let range = "must be a number of 0 or more";
    assert_eq!(LineArtOptions { low: -1.0, ..ok }.validate(), Err(bad("threshold", range)));
    assert_eq!(LineArtOptions { high: f32::NAN, ..ok }.validate(), Err(bad("threshold", range)));
    assert_eq!(
        LineArtOptions { low: 60.0, high: 50.0, ..ok }.validate(),
        Err(bad("threshold", "the high limit must not be below the low limit"))
    );
    assert_eq!(LineArtOptions { low: 0.0, high: 0.0, ..ok }.validate(), Ok(()));
    // The first broken field wins.
    assert_eq!(LineArtOptions { blur: 99.0, low: -1.0, ..ok }.validate(), Err(bad("blur", blur)));
}

#[test]
fn vector_rules() {
    let ok = VectorOptions::default();
    let colors = bad("colors", "must be from 2 to 64");
    assert_eq!(VectorOptions { colors: 1, ..ok }.validate(), Err(colors.clone()));
    assert_eq!(VectorOptions { colors: 65, ..ok }.validate(), Err(colors));
    assert_eq!(VectorOptions { colors: 2, ..ok }.validate(), Ok(()));
    assert_eq!(VectorOptions { colors: 64, ..ok }.validate(), Ok(()));
    let smooth = bad("smoothness", "must be a number from 0 to 10");
    for s in [-0.1, 10.1, f32::NAN] {
        assert_eq!(VectorOptions { smoothness: s, ..ok }.validate(), Err(smooth.clone()));
    }
    assert_eq!(VectorOptions { smoothness: 0.0, ..ok }.validate(), Ok(()));
    assert_eq!(
        VectorOptions { speckle: 10_001, ..ok }.validate(),
        Err(bad("speckle", "must be from 0 to 10000"))
    );
    assert_eq!(VectorOptions { speckle: 0, ..ok }.validate(), Ok(()));
    let iters = bad("iterations", "must be from 1 to 100");
    assert_eq!(VectorOptions { max_iterations: 0, ..ok }.validate(), Err(iters.clone()));
    assert_eq!(VectorOptions { max_iterations: 101, ..ok }.validate(), Err(iters));
    assert_eq!(
        VectorOptions { colors: 0, max_iterations: 0, ..ok }.validate(),
        Err(bad("colors", "must be from 2 to 64"))
    );
}

#[test]
fn effect_rules() {
    let ok = EffectOptions::default();
    let blur = bad("blur", "must be a number from 0.5 to 100");
    for b in [0.4, 100.5, f32::NAN] {
        assert_eq!(EffectOptions { blur: b, ..ok }.validate(), Err(blur.clone()));
    }
    assert_eq!(EffectOptions { blur: 0.5, ..ok }.validate(), Ok(()));
    let cell = bad("cell", "must be from 2 to 64");
    assert_eq!(EffectOptions { cell: 1, ..ok }.validate(), Err(cell.clone()));
    assert_eq!(EffectOptions { cell: 65, ..ok }.validate(), Err(cell));
    let cols = bad("columns", "must be from 1 to 1000");
    assert_eq!(EffectOptions { columns: 0, ..ok }.validate(), Err(cols.clone()));
    assert_eq!(EffectOptions { columns: 1001, ..ok }.validate(), Err(cols));
    assert_eq!(EffectOptions { style: Style::Ascii, ansi: true, invert: true, ..ok }.validate(), Ok(()));
}

#[test]
fn threshold_parsing() {
    assert_eq!(parse_threshold("45"), Ok((45.0, 90.0)));
    assert_eq!(parse_threshold(" 20 , 60 "), Ok((20.0, 60.0)));
    assert_eq!(parse_threshold("0"), Ok((0.0, 0.0)));
    assert_eq!(parse_threshold("12.5"), Ok((12.5, 25.0)));
    let syntax = bad("threshold", "expected a number like 45 or two like 20,60");
    for t in ["a", "", "1,2,3", "1,", ",2", "4 5"] {
        assert_eq!(parse_threshold(t), Err(syntax.clone()), "{t:?}");
    }
    let range = bad("threshold", "must be a number of 0 or more");
    for t in ["-5", "nan", "inf", "1,-1"] {
        assert_eq!(parse_threshold(t), Err(range.clone()), "{t:?}");
    }
    assert_eq!(
        parse_threshold("20,10"),
        Err(bad("threshold", "the high limit must not be below the low limit"))
    );
}

#[test]
fn job_holds_each_kind() {
    let jobs = [
        Job::LineArt(LineArtOptions::default()),
        Job::Vector(VectorOptions::default()),
        Job::Effect(EffectOptions { style: Style::Hatch, ..EffectOptions::default() }),
    ];
    assert_eq!(jobs[2], Job::Effect(EffectOptions { style: Style::Hatch, ..EffectOptions::default() }));
    assert_ne!(jobs[0], jobs[1]);
    let copy = jobs[0];
    assert_eq!(copy, jobs[0]);
    assert_eq!(EdgeFilter::Sobel, EdgeFilter::Sobel);
    assert_ne!(Style::Dither, Style::Halftone);
}
