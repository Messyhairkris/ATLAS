# Contract: svg.rs - SVG text output

Module `src/svg.rs` of the crate `photo_tools`. Writes the vector engine's shapes as an
SVG document. Byte-exact: the hidden tests compare whole strings.

## API (exact)

```rust
//! SVG text output.

/// `v` rounded to 2 decimals, without trailing zeros: 1.5 -> "1.5", 2.0 -> "2",
/// -0.001 -> "0", 3.14159 -> "3.14".
pub fn fmt_num(v: f64) -> String

/// "#rrggbb", lowercase.
pub fn hex(color: [u8; 3]) -> String

/// Path data for closed loops of cubic segments [x0, y0, c1x, c1y, c2x, c2y, x1, y1].
pub fn path_data(loops: &[Vec<[f64; 8]>]) -> String

/// A whole SVG document: a background rectangle, then one path per shape.
pub fn document(width: u32, height: u32, background: [u8; 3], shapes: &[([u8; 3], String)]) -> String
```

Imports allowed: std only (`format!`, `String`).

## Rules

1. `fmt_num`: `r = (v * 100.0).round() as i64` (`f64::round` rounds half away from
   zero). `whole = |r| / 100`, `frac = |r| % 100`. Sign `"-"` only if `r < 0`.
   - `frac == 0` -> `"{sign}{whole}"`
   - `frac % 10 == 0` -> `"{sign}{whole}.{frac / 10}"`
   - otherwise -> `"{sign}{whole}.{frac:02}"` (two digits)
   Never use `{:.2}` and trim: it rounds differently and keeps "-0".
2. `hex`: `"#"` then each channel as two lowercase hex digits (`{:02x}`).
3. `path_data`: skip empty loops. For each remaining loop: `"M x0 y0"` from its FIRST
   segment's `[0]` and `[1]`; then for every segment `" C c1x c1y c2x c2y x1 y1"`
   (elements `[2]` to `[7]`, each through `fmt_num`, separated by single spaces); then
   `" Z"`. Loops are joined with ONE space. No loops (or only empty ones) -> `""`.
4. `document`, exactly (each `\n` is one newline character, nothing else between):
   ```
   <svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n
   <rect width="{W}" height="{H}" fill="{hex(background)}"/>\n
   <path fill="{hex(color)}" fill-rule="evenodd" d="{d}"/>\n      one line per shape, in order
   </svg>\n
   ```
   A shape whose `d` is the empty string gets no line.

## Worked examples

| `fmt_num(v)` | result | | `fmt_num(v)` | result |
|---|---|---|---|---|
| 0.0 | `0` | | 0.07 | `0.07` |
| 1.5 | `1.5` | | -0.5 | `-0.5` |
| 2.0 | `2` | | 1234.5678 | `1234.57` |
| -0.001 | `0` | | 0.005 | `0.01` |
| -0.0 | `0` | | 0.004999 | `0` |
| 3.14159 | `3.14` | | 2.0 / 3.0 | `0.67` |
| -1.25 | `-1.25` | | 100.0 | `100` |
| 10.1 | `10.1` | | -7.999 | `-8` |

`hex([255, 0, 16])` = `"#ff0010"`; `hex([171, 205, 239])` = `"#abcdef"`.

`path_data(&[vec![[0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0]]])` = `"M 0 0 C 1 0 2 0 3 0 Z"`

Two segments:
`[[1, 2, 1.5, 2, 2.5, 2.5, 3, 3], [3, 3, 2, 3.333, 1, 2.666, 1, 2]]` ->
`"M 1 2 C 1.5 2 2.5 2.5 3 3 C 2 3.33 1 2.67 1 2 Z"`

Loops `a`, empty, `b` -> `"M 0 0 C 0 1 1 1 1 0 Z M 5 5 C 6 5 6 6 5 6 Z"` (for
`a = [[0,0, 0,1, 1,1, 1,0]]`, `b = [[5,5, 6,5, 6,6, 5,6]]`).

`document(3, 2, [255, 255, 255], &[([255,0,0], "M 0 0 C 1 0 1 0 1 1 Z"), ([0,0,255], ""),
([0,128,0], "M 1 1 C 2 1 2 1 2 2 Z")])` =

```
<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2" viewBox="0 0 3 2">
<rect width="3" height="2" fill="#ffffff"/>
<path fill="#ff0000" fill-rule="evenodd" d="M 0 0 C 1 0 1 0 1 1 Z"/>
<path fill="#008000" fill-rule="evenodd" d="M 1 1 C 2 1 2 1 2 2 Z"/>
</svg>
```
(with a final newline after `</svg>`; the empty blue shape has no line).

`document(1, 1, [1, 2, 3], &[])` =
`"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1\" height=\"1\" viewBox=\"0 0 1 1\">\n<rect width=\"1\" height=\"1\" fill=\"#010203\"/>\n</svg>\n"`
