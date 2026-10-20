# API card: image 0.25.10, imageproc 0.27.0, clap 4.6.7

Checked against the crates' own source on 2026-10-20 (the versions the photo_tools crate
is locked to). Only what photo_tools modules need. If your memory of these crates
disagrees with this card, the card is right: older versions differ.

## image 0.25.10

```rust
use image::{DynamicImage, GrayImage, RgbImage, Luma, Rgb};
// GrayImage = ImageBuffer<Luma<u8>, Vec<u8>>   (1 byte per pixel, row-major)
// RgbImage  = ImageBuffer<Rgb<u8>, Vec<u8>>    (3 bytes per pixel, row-major)

// DynamicImage (an enum: ImageLuma8(GrayImage), ImageRgb8(RgbImage), ImageRgba8(..), ...)
img.width() -> u32                 // inherent method, no trait import needed
img.height() -> u32
img.to_rgb8() -> RgbImage          // converts any variant; drops alpha
img.to_luma8() -> GrayImage        // DO NOT use for photo_tools gray: it is Rec. 709;
                                   // photo_tools uses crate::luma (Rec. 601)

// ImageBuffer (GrayImage, RgbImage)
GrayImage::new(w: u32, h: u32) -> GrayImage                       // all zero
GrayImage::from_raw(w: u32, h: u32, buf: Vec<u8>) -> Option<GrayImage>
                                   // None if buf.len() < w * h * channels
GrayImage::from_pixel(w, h, Luma([v])) -> GrayImage
GrayImage::from_fn(w, h, |x: u32, y: u32| Luma([..])) -> GrayImage
buf.as_raw() -> &Vec<u8>           // borrow the bytes (use .as_slice() or &buf.as_raw()[..])
buf.into_raw() -> Vec<u8>          // take the bytes
buf.width() -> u32, buf.height() -> u32, buf.dimensions() -> (u32, u32)
buf.get_pixel(x, y) -> &Luma<u8>   // .0[0] is the value; panics out of bounds
buf.put_pixel(x, y, Luma([v]))
```

Not allowed in crew modules (file I/O): `image::open`, `.save(..)`, `.save_with_format(..)`,
`ImageReader`, `image::io`, `image::codecs`, `image::load`.

## imageproc 0.27.0

```rust
imageproc::filter::gaussian_blur_f32(image: &GrayImage, sigma: f32) -> GrayImage
    // generic over pixel type; works on GrayImage. PANICS if sigma <= 0.0:
    // only call it when sigma > 0.
imageproc::edges::canny(image: &GrayImage, low_threshold: f32, high_threshold: f32) -> GrayImage
    // PANICS unless high_threshold >= low_threshold. Applies its own Gaussian blur
    // (sigma 1.4) first. Output: 255 on an edge, 0 elsewhere (white edges on black).
```

## clap 4.6.7 (derive)

```rust
use clap::{Parser, ValueEnum};
use clap::error::ErrorKind;

#[derive(ValueEnum, Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModeArg { Lineart, Vector, Fx }        // values on the command line: lineart, vector, fx

#[derive(Parser, Debug)]
#[command(name = "photo_tools", version)]       // version comes from Cargo.toml
pub struct Args {
    #[arg(long)] pub input: String,             // --input <INPUT>, required
    #[arg(long, value_enum)] pub mode: ModeArg, // --mode <MODE>, required
    #[arg(long)] pub blur: Option<f32>,         // optional
    #[arg(long)] pub ansi: bool,                // a flag: present -> true
}

Args::try_parse_from(argv.iter()) -> Result<Args, clap::Error>
    // argv: &[String]; argv[0] is the program name. NEVER use Args::parse() or
    // parse_from(): they read the real process arguments / exit the process.
err.kind() -> ErrorKind     // ErrorKind::DisplayHelp for --help, ErrorKind::DisplayVersion for --version
err.to_string() -> String   // the full message clap would print (help text for --help)
```

A doc comment `///` on the struct becomes the `--help` description; on a field, that
option's help line.
