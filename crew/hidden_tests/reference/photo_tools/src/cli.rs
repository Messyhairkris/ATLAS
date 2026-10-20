//! Command-line parsing into a Job. Reference for the cli.rs contract.

use clap::error::ErrorKind;
use clap::{Parser, ValueEnum};

use crate::options::{
    parse_threshold, EdgeFilter, EffectOptions, Job, LineArtOptions, Style, VectorOptions,
};

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModeArg {
    Lineart,
    Vector,
    Fx,
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum FilterArg {
    Sobel,
    Canny,
}

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum StyleArg {
    Sketch,
    Dither,
    Halftone,
    Hatch,
    Ascii,
}

/// Non-AI image effects: line art, flat-colour SVG, sketch, dither, halftone,
/// hatching and ASCII art.
#[derive(Parser, Debug)]
#[command(name = "photo_tools", version)]
pub struct Args {
    /// Image to read (PNG or JPEG).
    #[arg(long)]
    pub input: String,
    /// File to write: .png for images, .svg for vector, .txt or - for ASCII.
    #[arg(long)]
    pub output: String,
    #[arg(long, value_enum)]
    pub mode: ModeArg,
    #[arg(long, value_enum)]
    pub filter: Option<FilterArg>,
    #[arg(long)]
    pub blur: Option<f32>,
    #[arg(long)]
    pub threshold: Option<String>,
    #[arg(long)]
    pub colors: Option<u8>,
    #[arg(long)]
    pub smoothness: Option<f32>,
    #[arg(long)]
    pub speckle: Option<u32>,
    #[arg(long)]
    pub iterations: Option<u32>,
    #[arg(long, value_enum)]
    pub style: Option<StyleArg>,
    #[arg(long)]
    pub cell: Option<u32>,
    #[arg(long)]
    pub columns: Option<u32>,
    #[arg(long)]
    pub ansi: bool,
    #[arg(long)]
    pub invert: bool,
}

/// A parsed command line.
#[derive(Debug, Clone, PartialEq)]
pub struct Invocation {
    pub input: String,
    pub output: String,
    pub job: Job,
}

/// Why parsing stopped: help or version text (code 0) or an error (code 2).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Exit {
    pub code: i32,
    pub message: String,
}

fn usage(message: String) -> Exit {
    Exit { code: 2, message }
}

pub fn parse(argv: &[String]) -> Result<Invocation, Exit> {
    let args = match Args::try_parse_from(argv.iter()) {
        Ok(a) => a,
        Err(e) => {
            let code = match e.kind() {
                ErrorKind::DisplayHelp | ErrorKind::DisplayVersion => 0,
                _ => 2,
            };
            return Err(Exit { code, message: e.to_string() });
        }
    };
    let mode_name = match args.mode {
        ModeArg::Lineart => "lineart",
        ModeArg::Vector => "vector",
        ModeArg::Fx => "fx",
    };
    let given = [
        ("filter", args.filter.is_some(), [true, false, false]),
        ("blur", args.blur.is_some(), [true, false, true]),
        ("threshold", args.threshold.is_some(), [true, false, false]),
        ("colors", args.colors.is_some(), [false, true, false]),
        ("smoothness", args.smoothness.is_some(), [false, true, false]),
        ("speckle", args.speckle.is_some(), [false, true, false]),
        ("iterations", args.iterations.is_some(), [false, true, false]),
        ("style", args.style.is_some(), [false, false, true]),
        ("cell", args.cell.is_some(), [false, false, true]),
        ("columns", args.columns.is_some(), [false, false, true]),
        ("ansi", args.ansi, [false, false, true]),
        ("invert", args.invert, [false, false, true]),
    ];
    let slot = args.mode as usize;
    for (flag, present, applies) in given {
        if present && !applies[slot] {
            return Err(usage(format!("error: --{flag} does not apply to --mode {mode_name}")));
        }
    }
    let job = match args.mode {
        ModeArg::Lineart => {
            let mut o = LineArtOptions::default();
            if let Some(f) = args.filter {
                o.filter = match f {
                    FilterArg::Sobel => EdgeFilter::Sobel,
                    FilterArg::Canny => EdgeFilter::Canny,
                };
            }
            if let Some(b) = args.blur {
                o.blur = b;
            }
            if let Some(t) = &args.threshold {
                let (low, high) = parse_threshold(t).map_err(|e| usage(format!("error: {e}")))?;
                o.low = low;
                o.high = high;
            }
            o.validate().map_err(|e| usage(format!("error: {e}")))?;
            Job::LineArt(o)
        }
        ModeArg::Vector => {
            let mut o = VectorOptions::default();
            o.colors = args.colors.unwrap_or(o.colors);
            o.smoothness = args.smoothness.unwrap_or(o.smoothness);
            o.speckle = args.speckle.unwrap_or(o.speckle);
            o.max_iterations = args.iterations.unwrap_or(o.max_iterations);
            o.validate().map_err(|e| usage(format!("error: {e}")))?;
            Job::Vector(o)
        }
        ModeArg::Fx => {
            let mut o = EffectOptions::default();
            if let Some(s) = args.style {
                o.style = match s {
                    StyleArg::Sketch => Style::Sketch,
                    StyleArg::Dither => Style::Dither,
                    StyleArg::Halftone => Style::Halftone,
                    StyleArg::Hatch => Style::Hatch,
                    StyleArg::Ascii => Style::Ascii,
                };
            }
            o.blur = args.blur.unwrap_or(o.blur);
            o.cell = args.cell.unwrap_or(o.cell);
            o.columns = args.columns.unwrap_or(o.columns);
            o.ansi = args.ansi;
            o.invert = args.invert;
            o.validate().map_err(|e| usage(format!("error: {e}")))?;
            Job::Effect(o)
        }
    };
    Ok(Invocation { input: args.input, output: args.output, job })
}
