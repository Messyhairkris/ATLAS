# House style for crew-written Rust

Appended to every `rs_code_task` and `rs_code_tests` contract. Formatting nobody asked
for in writing does not happen, so it is written here. `rustfmt` and `clippy` run after
acceptance; what follows is what they cannot fix for you.

## The file

- ONE file: `src/<module>.rs` for a module, `tests/<name>.rs` for tests. The harness
  writes `src/lib.rs` (one `pub mod` line per module) and `Cargo.toml`; you cannot add
  crates, features, `build.rs` or other files.
- Edition 2021, stable Rust. Write the whole file every time.
- 100 characters per line at most, four-space indentation (rustfmt's defaults).
- A `//!` line at the top saying what the module is. `///` on every `pub` item.
- No `println!`/`eprintln!`/`dbg!` in a module. Return values; the caller prints.

## What you may use

- `std`, minus everything that reaches the machine: no `std::fs`, `io`, `net`,
  `process`, `env`, `path`, `os`, `ffi`, `thread`, `ptr`. No `unsafe`, `extern`,
  `include!`/`include_str!`/`include_bytes!`, `env!`, `macro_rules!`, inner attributes
  (`#![...]`) or `mod name;`. The scan refuses the file before it compiles.
- Other modules of this crate: `use crate::<module>::<item>;` (tests: `use
  <crate>::<module>::<item>;`).
- Crates the contract lists, minus their file I/O (for `image`: no `open`, `save`,
  `ImageReader`, `io`, `codecs`). Pixels come in as arguments and go out as values.
- Import each name you use; no glob imports except `use super::*;` in a test module.

## Types and numbers

- Use exactly the signatures in the contract's API block: same names, same argument
  order, same integer widths. The hidden tests call them as written.
- Integer arithmetic that can overflow `u8` goes through `u32`/`i32` first:
  `a as u32 * 255`, not `a * 255`. Debug builds panic on overflow.
- Say which rounding you use: `f64::round` rounds half away from zero; `as` truncates
  toward zero; integer `/` truncates toward zero for negatives too.
- Ranges: `a..b` excludes `b`; `a..=b` includes it. Check the contract's wording.
- Prefer `usize` for indices, and compute `y * width + x` once per pixel.

## Structure

- Validate first, then allocate, then compute: nothing is consumed by a failure.
- Do not repeat a literal structure; one small helper beats four copies.
- Private helpers (`fn` without `pub`) are fine and encouraged.
- No `todo!()`, `unimplemented!()` or empty function bodies: the stub check refuses them.
- Do not `panic!` or `unwrap()` on input the contract says can happen; return what the
  contract says. `unwrap()` is fine where the contract guarantees success.

## Comments

- A comment says why or which rule ("rule 3: ties go to the smaller label"), never what
  the next line obviously does.
- **Never invent a reason.** If the contract does not say why, name the rule and stop.

## Tests (`rs_code_tests`)

- An integration test file: `use <crate>::<module>::{...};` then `#[test]` functions.
- One rule per test, named after it (`fn rule_2_ties_go_to_smaller_label()`).
- `assert_eq!(got, want)` on whole values (whole vectors, whole strings), not lengths.
- `#[should_panic]` only where the contract says a call panics. Never `#[ignore]`.
- No files, no randomness, no time. Build inputs inline.

## The two things no tool can check for you

1. **Say when the contract is wrong.** Write a NOTE line at the end of your answer AND
   implement it as written.
2. **Walk the worked-example table through your code before you submit.** Every row is
   a hidden test.
