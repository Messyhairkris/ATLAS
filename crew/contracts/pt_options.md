# Contract: options.rs - options, validation and the error type

Module `src/options.rs` of the crate `photo_tools`. The library's public vocabulary: one
options struct per engine with defaults and validation, the `Job` an embedding program
hands to the library, a threshold parser, and the error type. Other modules and other
programs use these types, so names, derives and field order are exact.

## API (exact)

```rust
//! Options, validation and the library's error type.

use std::fmt;

/// Everything the library can refuse.
#[derive(Debug, Clone, PartialEq)]
pub enum Error {
    InvalidOption { name: &'static str, reason: String },
    EmptyImage,
}
impl fmt::Display for Error { /* rule 1 */ }
impl std::error::Error for Error {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EdgeFilter { Sobel, Canny }

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LineArtOptions { pub filter: EdgeFilter, pub blur: f32, pub low: f32, pub high: f32 }

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VectorOptions { pub colors: u8, pub smoothness: f32, pub speckle: u32, pub max_iterations: u32 }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Style { Sketch, Dither, Halftone, Hatch, Ascii }

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct EffectOptions { pub style: Style, pub blur: f32, pub cell: u32, pub columns: u32, pub ansi: bool, pub invert: bool }

/// What to make from an image.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Job { LineArt(LineArtOptions), Vector(VectorOptions), Effect(EffectOptions) }

impl Default for LineArtOptions / VectorOptions / EffectOptions   // rule 2
impl LineArtOptions { pub fn validate(&self) -> Result<(), Error> }   // rule 3
impl VectorOptions  { pub fn validate(&self) -> Result<(), Error> }   // rule 4
impl EffectOptions  { pub fn validate(&self) -> Result<(), Error> }   // rule 5

/// "45" -> (45, 90); "20,60" -> (20, 60). Spaces around numbers are ignored.
pub fn parse_threshold(text: &str) -> Result<(f32, f32), Error>   // rule 6
```

(The `/* rule 1 */` and `//` lines show where each rule goes; write real items.)

Imports allowed: `std::fmt` (and `std::error::Error` by its full path). Nothing else.

## Rules

Below, `bad(name, reason)` means `Err(Error::InvalidOption { name, reason: reason.to_string() })`.

1. Display: `InvalidOption` -> `"invalid --{name}: {reason}"`; `EmptyImage` ->
   `"the image has no pixels"`.
2. Defaults: `LineArtOptions { filter: Canny, blur: 1.0, low: 50.0, high: 100.0 }`;
   `VectorOptions { colors: 8, smoothness: 1.0, speckle: 8, max_iterations: 20 }`;
   `EffectOptions { style: Sketch, blur: 8.0, cell: 6, columns: 100, ansi: false, invert: false }`.
3. `LineArtOptions::validate`, checks in this order, first failure returned:
   a. `blur` not finite or outside `0.0..=50.0` -> `bad("blur", "must be a number from 0 to 50")`
   b. `low` or `high` not finite or below 0.0 -> `bad("threshold", "must be a number of 0 or more")`
   c. `high < low` -> `bad("threshold", "the high limit must not be below the low limit")`
4. `VectorOptions::validate`, in order:
   a. `colors` outside `2..=64` -> `bad("colors", "must be from 2 to 64")`
   b. `smoothness` not finite or outside `0.0..=10.0` -> `bad("smoothness", "must be a number from 0 to 10")`
   c. `speckle > 10000` -> `bad("speckle", "must be from 0 to 10000")`
   d. `max_iterations` outside `1..=100` -> `bad("iterations", "must be from 1 to 100")`
5. `EffectOptions::validate`, in order:
   a. `blur` not finite or outside `0.5..=100.0` -> `bad("blur", "must be a number from 0.5 to 100")`
   b. `cell` outside `2..=64` -> `bad("cell", "must be from 2 to 64")`
   c. `columns` outside `1..=1000` -> `bad("columns", "must be from 1 to 1000")`
   (`style`, `ansi`, `invert` are always valid.)
6. `parse_threshold(text)`, in order:
   a. Split `text` on `','` and trim each part. More than 2 parts, or any part that is
      not an `f32` (`part.parse::<f32>()` fails - this includes an empty part) ->
      `bad("threshold", "expected a number like 45 or two like 20,60")`.
   b. One part `t` -> `(low, high) = (t, t * 2.0)`; two parts -> `(first, second)`.
   c. `low` or `high` not finite or below 0.0 -> `bad("threshold", "must be a number of 0 or more")`.
      (`"nan"` and `"inf"` parse as `f32` and fail HERE, not in a.)
   d. `high < low` -> `bad("threshold", "the high limit must not be below the low limit")`.
   e. Otherwise `Ok((low, high))`.

## Worked examples

| expression | result |
|---|---|
| `Error::EmptyImage.to_string()` | `"the image has no pixels"` |
| `bad("colors", "must be from 2 to 64")` displayed | `"invalid --colors: must be from 2 to 64"` |
| `LineArtOptions { blur: 50.1, ..default }.validate()` | `bad("blur", "must be a number from 0 to 50")` |
| `LineArtOptions { blur: 50.0, ..default }.validate()` | `Ok(())` |
| `LineArtOptions { blur: 99.0, low: -1.0, ..default }.validate()` | the blur error (3a first) |
| `LineArtOptions { low: 60.0, high: 50.0, ..default }.validate()` | the high-limit error |
| `LineArtOptions { low: 0.0, high: 0.0, ..default }.validate()` | `Ok(())` |
| `VectorOptions { colors: 0, max_iterations: 0, ..default }.validate()` | the colors error |
| `VectorOptions { speckle: 10_001, ..default }.validate()` | `bad("speckle", "must be from 0 to 10000")` |
| `EffectOptions { blur: 0.4, ..default }.validate()` | `bad("blur", "must be a number from 0.5 to 100")` |
| `EffectOptions { columns: 0, ..default }.validate()` | `bad("columns", "must be from 1 to 1000")` |
| `parse_threshold("45")` | `Ok((45.0, 90.0))` |
| `parse_threshold(" 20 , 60 ")` | `Ok((20.0, 60.0))` |
| `parse_threshold("0")` | `Ok((0.0, 0.0))` |
| `parse_threshold("12.5")` | `Ok((12.5, 25.0))` |
| `parse_threshold("a")`, `""`, `"1,2,3"`, `"1,"`, `",2"`, `"4 5"` | the "expected a number" error |
| `parse_threshold("-5")`, `"nan"`, `"inf"`, `"1,-1"` | the "0 or more" error |
| `parse_threshold("20,10")` | the high-limit error |

`Job` is plain data: `Job::Effect(EffectOptions { style: Style::Hatch, ..EffectOptions::default() })`
must compile, compare with `==`, and copy.
