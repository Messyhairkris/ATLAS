# Contract: dodge.rs - Color Dodge blending

Module `src/dodge.rs` of the crate `photo_tools`. The blend mode behind the pencil-sketch
effect: a light blend layer brightens the base.

## API (exact)

```rust
//! Color Dodge blending.

/// Color Dodge of one channel (rules 1-3 of the contract).
pub fn color_dodge(base: u8, blend: u8) -> u8

/// color_dodge pairwise; the result is as long as the shorter input.
pub fn dodge_layers(base: &[u8], blend: &[u8]) -> Vec<u8>
```

Imports allowed: none needed (std prelude only).

## Rules for `color_dodge` (in order; the first that matches decides)

1. If `base == 0`, the result is `0`.
2. If `blend == 255`, the result is `255`.
3. Otherwise let `d = 255 - blend` (as `u32`, so 1..=255). The result is
   `min(255, (base * 255 + d / 2) / d)`, all in `u32` with integer division (`d / 2`
   is also integer division).

## Rule for `dodge_layers`

4. Pair `base[i]` with `blend[i]` for every `i` both slices have (zip), apply
   `color_dodge`, and collect. Extra items in the longer slice are ignored.

## Worked examples

| base | blend | d | (base*255 + d/2) / d | result | rule |
|---|---|---|---|---|---|
| 0 | 255 | - | - | 0 | 1 (before rule 2) |
| 0 | 0 | - | - | 0 | 1 |
| 10 | 255 | - | - | 255 | 2 |
| 128 | 128 | 127 | (32640 + 63) / 127 = 257 | 255 | 3, capped |
| 100 | 100 | 155 | (25500 + 77) / 155 = 165 | 165 | 3 |
| 200 | 0 | 255 | (51000 + 127) / 255 = 200 | 200 | 3 |
| 1 | 254 | 1 | (255 + 0) / 1 = 255 | 255 | 3 |
| 50 | 200 | 55 | (12750 + 27) / 55 = 232 | 232 | 3 |
| 77 | 3 | 252 | (19635 + 126) / 252 = 78 | 78 | 3 |
| 1 | 253 | 2 | (255 + 1) / 2 = 128 | 128 | 3 (the d/2 matters) |

| call | result |
|---|---|
| `dodge_layers(&[0, 100, 200], &[255, 100])` | `vec![0, 165]` |
| `dodge_layers(&[10], &[255, 1, 2])` | `vec![255]` |
| `dodge_layers(&[], &[1])` | `vec![]` |
