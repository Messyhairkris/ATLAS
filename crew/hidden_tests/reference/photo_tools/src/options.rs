//! Options, validation and the library's error type. Reference for options.rs.

use std::fmt;

/// Everything the library can refuse.
#[derive(Debug, Clone, PartialEq)]
pub enum Error {
    InvalidOption { name: &'static str, reason: String },
    EmptyImage,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::InvalidOption { name, reason } => write!(f, "invalid --{name}: {reason}"),
            Error::EmptyImage => write!(f, "the image has no pixels"),
        }
    }
}

impl std::error::Error for Error {}

fn invalid(name: &'static str, reason: &str) -> Error {
    Error::InvalidOption { name, reason: reason.to_string() }
}

const THRESHOLD_SYNTAX: &str = "expected a number like 45 or two like 20,60";
const THRESHOLD_RANGE: &str = "must be a number of 0 or more";
const THRESHOLD_ORDER: &str = "the high limit must not be below the low limit";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EdgeFilter {
    Sobel,
    Canny,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LineArtOptions {
    pub filter: EdgeFilter,
    pub blur: f32,
    pub low: f32,
    pub high: f32,
}

impl Default for LineArtOptions {
    fn default() -> Self {
        LineArtOptions { filter: EdgeFilter::Canny, blur: 1.0, low: 50.0, high: 100.0 }
    }
}

impl LineArtOptions {
    pub fn validate(&self) -> Result<(), Error> {
        if !self.blur.is_finite() || !(0.0..=50.0).contains(&self.blur) {
            return Err(invalid("blur", "must be a number from 0 to 50"));
        }
        if !self.low.is_finite() || self.low < 0.0 || !self.high.is_finite() || self.high < 0.0 {
            return Err(invalid("threshold", THRESHOLD_RANGE));
        }
        if self.high < self.low {
            return Err(invalid("threshold", THRESHOLD_ORDER));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VectorOptions {
    pub colors: u8,
    pub smoothness: f32,
    pub speckle: u32,
    pub max_iterations: u32,
}

impl Default for VectorOptions {
    fn default() -> Self {
        VectorOptions { colors: 8, smoothness: 1.0, speckle: 8, max_iterations: 20 }
    }
}

impl VectorOptions {
    pub fn validate(&self) -> Result<(), Error> {
        if !(2..=64).contains(&self.colors) {
            return Err(invalid("colors", "must be from 2 to 64"));
        }
        if !self.smoothness.is_finite() || !(0.0..=10.0).contains(&self.smoothness) {
            return Err(invalid("smoothness", "must be a number from 0 to 10"));
        }
        if self.speckle > 10_000 {
            return Err(invalid("speckle", "must be from 0 to 10000"));
        }
        if !(1..=100).contains(&self.max_iterations) {
            return Err(invalid("iterations", "must be from 1 to 100"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Style {
    Sketch,
    Dither,
    Halftone,
    Hatch,
    Ascii,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct EffectOptions {
    pub style: Style,
    pub blur: f32,
    pub cell: u32,
    pub columns: u32,
    pub ansi: bool,
    pub invert: bool,
}

impl Default for EffectOptions {
    fn default() -> Self {
        EffectOptions {
            style: Style::Sketch,
            blur: 8.0,
            cell: 6,
            columns: 100,
            ansi: false,
            invert: false,
        }
    }
}

impl EffectOptions {
    pub fn validate(&self) -> Result<(), Error> {
        if !self.blur.is_finite() || !(0.5..=100.0).contains(&self.blur) {
            return Err(invalid("blur", "must be a number from 0.5 to 100"));
        }
        if !(2..=64).contains(&self.cell) {
            return Err(invalid("cell", "must be from 2 to 64"));
        }
        if !(1..=1000).contains(&self.columns) {
            return Err(invalid("columns", "must be from 1 to 1000"));
        }
        Ok(())
    }
}

/// What to make from an image.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Job {
    LineArt(LineArtOptions),
    Vector(VectorOptions),
    Effect(EffectOptions),
}

/// "45" -> (45, 90); "20,60" -> (20, 60). Spaces around numbers are ignored.
pub fn parse_threshold(text: &str) -> Result<(f32, f32), Error> {
    let parts: Vec<&str> = text.split(',').map(str::trim).collect();
    if parts.len() > 2 {
        return Err(invalid("threshold", THRESHOLD_SYNTAX));
    }
    let mut nums = Vec::new();
    for p in &parts {
        nums.push(p.parse::<f32>().map_err(|_| invalid("threshold", THRESHOLD_SYNTAX))?);
    }
    let (low, high) = if nums.len() == 1 { (nums[0], nums[0] * 2.0) } else { (nums[0], nums[1]) };
    if !low.is_finite() || low < 0.0 || !high.is_finite() || high < 0.0 {
        return Err(invalid("threshold", THRESHOLD_RANGE));
    }
    if high < low {
        return Err(invalid("threshold", THRESHOLD_ORDER));
    }
    Ok((low, high))
}
