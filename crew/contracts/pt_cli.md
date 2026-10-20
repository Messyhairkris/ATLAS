# Contract: cli.rs - command-line parsing

Module `src/cli.rs` of the crate `photo_tools`. Parses the command line with clap's
derive API into an `Invocation` (input path, output path, and the library `Job`). It does
not read files or exit the process: `main.rs` (written separately) does that with what
`parse` returns.

## API (exact)

```rust
//! Command-line parsing into a Job.

use clap::error::ErrorKind;
use clap::{Parser, ValueEnum};

use crate::options::{
    parse_threshold, EdgeFilter, EffectOptions, Job, LineArtOptions, Style, VectorOptions,
};

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModeArg { Lineart, Vector, Fx }

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum FilterArg { Sobel, Canny }

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum StyleArg { Sketch, Dither, Halftone, Hatch, Ascii }

/// Non-AI image effects: line art, flat-colour SVG, sketch, dither, halftone,
/// hatching and ASCII art.
#[derive(Parser, Debug)]
#[command(name = "photo_tools", version)]
pub struct Args {
    #[arg(long)] pub input: String,
    #[arg(long)] pub output: String,
    #[arg(long, value_enum)] pub mode: ModeArg,
    #[arg(long, value_enum)] pub filter: Option<FilterArg>,
    #[arg(long)] pub blur: Option<f32>,
    #[arg(long)] pub threshold: Option<String>,
    #[arg(long)] pub colors: Option<u8>,
    #[arg(long)] pub smoothness: Option<f32>,
    #[arg(long)] pub speckle: Option<u32>,
    #[arg(long)] pub iterations: Option<u32>,
    #[arg(long, value_enum)] pub style: Option<StyleArg>,
    #[arg(long)] pub cell: Option<u32>,
    #[arg(long)] pub columns: Option<u32>,
    #[arg(long)] pub ansi: bool,
    #[arg(long)] pub invert: bool,
}

/// A parsed command line.
#[derive(Debug, Clone, PartialEq)]
pub struct Invocation { pub input: String, pub output: String, pub job: Job }

/// Why parsing stopped: help or version text (code 0) or an error (code 2).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Exit { pub code: i32, pub message: String }

pub fn parse(argv: &[String]) -> Result<Invocation, Exit>
```

Put each `#[arg(..)]` on its own line above its field (rustfmt style) and add a `///`
help line to `input`, `output` and `mode` at least. Field ORDER matters (rule 3).

Imports allowed: exactly the `use` lines above. The API card (reference below) covers
clap 4.6; `crate::options` (source shown below the contract) gives `parse_threshold`,
the option structs with `Default` and `validate()`, and `Error`'s Display text.

## Rules (in order)

1. `Args::try_parse_from(argv.iter())` (argv[0] is the program name). Never `parse()` or
   `parse_from()`. On a clap error `e`: return `Err(Exit { code, message: e.to_string() })`
   with `code = 0` if `e.kind()` is `ErrorKind::DisplayHelp` or `ErrorKind::DisplayVersion`,
   else `code = 2`.
2. Which flags belong to which mode:
   | flag | lineart | vector | fx |
   |---|---|---|---|
   | --filter | yes | | |
   | --blur | yes | | yes |
   | --threshold | yes | | |
   | --colors, --smoothness, --speckle, --iterations | | yes | |
   | --style, --cell, --columns, --ansi, --invert | | | yes |
   A flag counts as GIVEN when its `Option` is `Some`, or for `ansi`/`invert` when true.
3. Check the flags in the `Args` FIELD ORDER (filter, blur, threshold, colors,
   smoothness, speckle, iterations, style, cell, columns, ansi, invert). The first GIVEN
   flag that does not belong to `--mode` -> `Err(Exit { code: 2, message:
   "error: --{flag} does not apply to --mode {mode}" })` with `{mode}` = `lineart`,
   `vector` or `fx`.
4. Start from the mode's `Default` options and overwrite only what was given:
   - lineart: `filter` (Sobel -> `EdgeFilter::Sobel`, Canny -> `EdgeFilter::Canny`),
     `blur`; `threshold` through `parse_threshold(&text)` into `(low, high)`.
   - vector: `colors`, `smoothness`, `speckle`, `iterations` -> `max_iterations`.
   - fx: `style` (each `StyleArg` to the `Style` of the same name), `blur`, `cell`,
     `columns`, and `ansi`, `invert` copied as given.
5. Any `Error` from `parse_threshold` or from `validate()` (call validate after rule 4)
   -> `Err(Exit { code: 2, message: format!("error: {e}") })` (Error's Display text).
6. Otherwise `Ok(Invocation { input, output, job })` with `Job::LineArt(..)`,
   `Job::Vector(..)` or `Job::Effect(..)`.

## Worked examples

argv always starts with `"photo_tools"`; shown here without it.

| arguments | result |
|---|---|
| `--input photo.jpg --output lineart.png --mode lineart --filter canny --blur 1.2 --threshold 45` | `Ok(Invocation { input: "photo.jpg", output: "lineart.png", job: LineArt(LineArtOptions { filter: Canny, blur: 1.2, low: 45.0, high: 90.0 }) })` |
| `--input landscape.png --output vector.svg --mode vector --colors 8 --smoothness 1.5` | job `Vector(VectorOptions { colors: 8, smoothness: 1.5, speckle: 8, max_iterations: 20 })` |
| `--input a --output b --mode fx` | job `Effect(EffectOptions::default())` |
| `--input a --output b --mode lineart --filter sobel --threshold 20,60 --blur 0` | `LineArt { filter: Sobel, blur: 0.0, low: 20.0, high: 60.0 }` |
| `--input a --output b --mode vector --colors 3 --smoothness 0 --speckle 0 --iterations 5` | `Vector { colors: 3, smoothness: 0.0, speckle: 0, max_iterations: 5 }` |
| `--input a --output - --mode fx --style ascii --columns 80 --ansi --invert` | `Effect { style: Ascii, blur: 8.0, cell: 6, columns: 80, ansi: true, invert: true }` |
| `--input a --output b --mode vector --blur 2` | `Err(Exit { code: 2, message: "error: --blur does not apply to --mode vector" })` |
| `--input a --output b --mode lineart --cell 3 --colors 4` | `Err(Exit { code: 2, message: "error: --colors does not apply to --mode lineart" })` (colors comes before cell) |
| `--input a --output b --mode vector --invert` | `Err(Exit { code: 2, message: "error: --invert does not apply to --mode vector" })` |
| `--input a --output b --mode vector --colors 1` | `Err(Exit { code: 2, message: "error: invalid --colors: must be from 2 to 64" })` |
| `--input a --output b --mode lineart --threshold 20,10` | `Err(Exit { code: 2, message: "error: invalid --threshold: the high limit must not be below the low limit" })` |
| `--help` | `Err(Exit { code: 0, message: <clap's help text, which mentions --input and --mode> })` |
| `--version` | `Err(Exit { code: 0, message: <text containing "photo_tools"> })` |
| `--input a --output b` (no --mode) | `Err(Exit { code: 2, .. })`, message mentions `--mode` |
| `--mode paint`, `--colors 300`, or an unknown flag | `Err(Exit { code: 2, .. })` (clap's own errors) |
