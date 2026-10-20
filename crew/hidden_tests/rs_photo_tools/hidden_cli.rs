use photo_tools::cli::{parse, Exit, Invocation};
use photo_tools::options::{EdgeFilter, EffectOptions, Job, LineArtOptions, Style, VectorOptions};

fn argv(rest: &str) -> Vec<String> {
    std::iter::once("photo_tools".to_string())
        .chain(rest.split_whitespace().map(str::to_string))
        .collect()
}

fn job(rest: &str) -> Job {
    parse(&argv(rest)).unwrap().job
}

fn err(rest: &str) -> Exit {
    parse(&argv(rest)).unwrap_err()
}

#[test]
fn spec_example_one_canny() {
    assert_eq!(
        parse(&argv("--input photo.jpg --output lineart.png --mode lineart --filter canny --blur 1.2 --threshold 45")),
        Ok(Invocation {
            input: "photo.jpg".to_string(),
            output: "lineart.png".to_string(),
            job: Job::LineArt(LineArtOptions { filter: EdgeFilter::Canny, blur: 1.2, low: 45.0, high: 90.0 }),
        })
    );
}

#[test]
fn spec_example_two_vector() {
    assert_eq!(
        job("--input landscape.png --output vector.svg --mode vector --colors 8 --smoothness 1.5"),
        Job::Vector(VectorOptions { colors: 8, smoothness: 1.5, speckle: 8, max_iterations: 20 })
    );
}

#[test]
fn defaults_per_mode() {
    assert_eq!(job("--input a --output b --mode lineart"), Job::LineArt(LineArtOptions::default()));
    assert_eq!(job("--input a --output b --mode vector"), Job::Vector(VectorOptions::default()));
    assert_eq!(job("--input a --output b --mode fx"), Job::Effect(EffectOptions::default()));
}

#[test]
fn line_art_flags() {
    assert_eq!(
        job("--input a --output b --mode lineart --filter sobel --threshold 20,60 --blur 0"),
        Job::LineArt(LineArtOptions { filter: EdgeFilter::Sobel, blur: 0.0, low: 20.0, high: 60.0 })
    );
}

#[test]
fn vector_flags() {
    assert_eq!(
        job("--input a --output b --mode vector --colors 3 --smoothness 0 --speckle 0 --iterations 5"),
        Job::Vector(VectorOptions { colors: 3, smoothness: 0.0, speckle: 0, max_iterations: 5 })
    );
}

#[test]
fn fx_flags() {
    assert_eq!(
        job("--input a --output - --mode fx --style ascii --columns 80 --ansi --invert"),
        Job::Effect(EffectOptions { style: Style::Ascii, blur: 8.0, cell: 6, columns: 80, ansi: true, invert: true })
    );
    for (name, style) in [("sketch", Style::Sketch), ("dither", Style::Dither),
                          ("halftone", Style::Halftone), ("hatch", Style::Hatch)] {
        assert_eq!(
            job(&format!("--input a --output b --mode fx --style {name} --cell 9 --blur 3")),
            Job::Effect(EffectOptions { style, blur: 3.0, cell: 9, ..EffectOptions::default() })
        );
    }
}

#[test]
fn flags_for_another_mode_are_refused_in_field_order() {
    assert_eq!(
        err("--input a --output b --mode vector --blur 2"),
        Exit { code: 2, message: "error: --blur does not apply to --mode vector".to_string() }
    );
    assert_eq!(
        err("--input a --output b --mode lineart --cell 3 --colors 4"),
        Exit { code: 2, message: "error: --colors does not apply to --mode lineart".to_string() }
    );
    assert_eq!(
        err("--input a --output b --mode fx --threshold 3"),
        Exit { code: 2, message: "error: --threshold does not apply to --mode fx".to_string() }
    );
    assert_eq!(
        err("--input a --output b --mode vector --invert"),
        Exit { code: 2, message: "error: --invert does not apply to --mode vector".to_string() }
    );
}

#[test]
fn every_flag_is_refused_outside_its_modes() {
    let flags: [(&str, &str, [bool; 3]); 12] = [
        ("filter", "--filter sobel", [true, false, false]),
        ("blur", "--blur 2", [true, false, true]),
        ("threshold", "--threshold 30", [true, false, false]),
        ("colors", "--colors 4", [false, true, false]),
        ("smoothness", "--smoothness 1", [false, true, false]),
        ("speckle", "--speckle 3", [false, true, false]),
        ("iterations", "--iterations 9", [false, true, false]),
        ("style", "--style dither", [false, false, true]),
        ("cell", "--cell 4", [false, false, true]),
        ("columns", "--columns 40", [false, false, true]),
        ("ansi", "--ansi", [false, false, true]),
        ("invert", "--invert", [false, false, true]),
    ];
    for (name, arg, applies) in flags {
        for (i, mode) in ["lineart", "vector", "fx"].iter().enumerate() {
            let got = parse(&argv(&format!("--input a --output b --mode {mode} {arg}")));
            if applies[i] {
                assert!(got.is_ok(), "{arg} with --mode {mode}: {got:?}");
            } else {
                let message = format!("error: --{name} does not apply to --mode {mode}");
                assert_eq!(got, Err(Exit { code: 2, message }), "{arg} with --mode {mode}");
            }
        }
    }
}

#[test]
fn validation_errors_use_the_library_text() {
    assert_eq!(
        err("--input a --output b --mode vector --colors 1"),
        Exit { code: 2, message: "error: invalid --colors: must be from 2 to 64".to_string() }
    );
    assert_eq!(
        err("--input a --output b --mode lineart --threshold 20,10"),
        Exit { code: 2, message: "error: invalid --threshold: the high limit must not be below the low limit".to_string() }
    );
    assert_eq!(
        err("--input a --output b --mode lineart --threshold x"),
        Exit { code: 2, message: "error: invalid --threshold: expected a number like 45 or two like 20,60".to_string() }
    );
    assert_eq!(
        err("--input a --output b --mode fx --cell 1"),
        Exit { code: 2, message: "error: invalid --cell: must be from 2 to 64".to_string() }
    );
}

#[test]
fn help_and_version_exit_zero() {
    let help = err("--help");
    assert_eq!(help.code, 0);
    assert!(help.message.contains("--input") && help.message.contains("--mode"), "{}", help.message);
    let version = err("--version");
    assert_eq!(version.code, 0);
    assert!(version.message.contains("photo_tools"), "{}", version.message);
}

#[test]
fn clap_errors_exit_two() {
    let missing = err("--input a --output b");
    assert_eq!(missing.code, 2);
    assert!(missing.message.contains("--mode"), "{}", missing.message);
    assert_eq!(err("--input a --output b --mode paint").code, 2);
    assert_eq!(err("--input a --output b --mode vector --colors 300").code, 2);
    assert_eq!(err("--input a --output b --mode lineart --frobnicate").code, 2);
}
