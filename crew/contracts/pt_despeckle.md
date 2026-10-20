# Contract: despeckle.rs - merge small regions into a neighbour

Module `src/despeckle.rs` of the crate `photo_tools`. After colour quantization every
pixel has a label (its palette index). Tiny islands of one label make noisy vectors;
this merges each island smaller than `min_area` into the label around it.

## API (exact)

```rust
//! Merge small regions of a label map into a neighbour.

/// Components are found once, on the input; small ones are merged in raster
/// order of their first pixel, each into the most common neighbouring label.
pub fn despeckle(labels: &[u8], width: usize, height: usize, min_area: usize) -> Vec<u8>
```

Imports allowed: std only (`std::collections` if you want it).

`labels` is row-major (`labels[y * width + x]`), `labels.len() == width * height`. The
result has the same layout.

## Rules

1. If `min_area <= 1`, return a copy of `labels` unchanged.
2. COMPONENTS are found once, on the INPUT: maximal sets of equal-label pixels joined
   through their left/right/up/down neighbours (4-connected; diagonal pixels do not
   join). A component's AREA is its pixel count. Number the components in raster order of
   their first pixel (smallest y, then smallest x).
3. Walk the components in that order, ONE pass. Skip a component whose area is
   `>= min_area`.
4. For a component with area `< min_area`: for each of its pixels, look at its 4
   neighbours that are inside the image and NOT in this component, and add 1 to a count
   for that neighbour's CURRENT label - current meaning after the merges already done
   earlier in this pass. A neighbour pixel touched by two of the component's pixels
   counts twice.
5. If nothing was counted (the component touches no other pixel), leave it unchanged.
   Otherwise relabel every pixel of the component with the label that has the largest
   count; on a tie, the SMALLER label value wins.
6. Areas are never recomputed: a component that grew by absorbing a speck is still judged
   by its rule-2 area.

## Worked examples

| labels (rows separated by /) | w x h | min_area | result | why |
|---|---|---|---|---|
| `0 1 0 / 1 0 1` | 3x2 | 0 or 1 | unchanged | rule 1 |
| `0 0 0 / 0 1 0 / 0 0 0` | 3x3 | 2 | all 0 | the 1 sees 0 four times |
| `1 1 1 / 2 0 1 / 2 2 2` | 3x3 | 2 | `1 1 1 / 2 1 1 / 2 2 2` | centre sees 1 twice, 2 twice: tie -> 1 |
| `0 5 2` | 3x1 | 2 | `5 2 2` | see walk below |
| `1 1 1 / 2 0 1 / 2 2 2` | 3x3 | 5 | all 0 | see walk below |
| `7 3 / 3 7` | 2x2 | 2 | `3 3 / 3 3` | four 1-pixel components |
| `7` | 1x1 | 5 | `7` | rule 5 |
| `3 3 / 3 3` | 2x2 | 10 | unchanged | rule 5 |

Walk for `0 5 2`, min_area 2 - three 1-pixel components:
`[0]` sees 5 -> becomes 5 (now `5 5 2`). `[5]` sees 5 (the pixel just merged, rule 4
"current") once and 2 once: tie -> 2 (now `5 2 2`). `[2]` sees 2 -> stays 2.

Walk for `1 1 1 / 2 0 1 / 2 2 2`, min_area 5 - components in raster order: A = the four
1s (area 4), B = the four 2s (area 4), C = the centre 0 (area 1).
A: its outside neighbours are (0,1)=2, (1,1)=0, (1,1)=0 again (from (2,1)), (2,2)=2 ->
2: 2, 0: 2, tie -> 0. Now `0 0 0 / 2 0 0 / 2 2 2`.
B: neighbours (0,0)=0, (1,1)=0, (1,1)=0, (2,1)=0 -> 0. Now all 0. C: all 0 -> 0.
