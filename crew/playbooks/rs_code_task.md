# Playbook: rs_code_task

You are writing one complete Rust module (`src/<module>.rs`) against a contract. The
harness compiles it in a fixed crate and runs tests you never see. You cannot argue with
them; you can only satisfy the contract.

## Entries
- [rc-001] (seed) Write the WHOLE file every time, from the `//!` line to the last brace. Not a diff, not a fragment. A partial file is a failed task.
- [rc-002] (seed) The contract's API block is exact: every `pub` name, argument order, argument type and return type as written. The hidden tests call `<crate>::<module>::<name>` with those types; a `u16` where the contract says `u8` is a compile error in the tests.
- [rc-003] (seed) Only `std` (minus fs/io/net/process/env/path/os/ffi/thread/ptr), the crates the contract lists, and `crate::<module>` for accepted modules. No `unsafe`, `extern`, `include!`, `env!`, `macro_rules!`, `#![...]` or `mod name;`.
- [rc-004] (seed) Widen before you multiply: `a as u32 * 255`. Overflow panics in the test build and fails the run.
- [rc-005] (seed) Read the worked examples as tests. Walk every table row through your code before you submit, including the rounding.
- [rc-006] (seed) Rules are ordered: the first match wins. Validate before you allocate or compute.
- [rc-007] (seed) When the feedback is a compiler error, fix exactly what it names (the line, the expected type) and change nothing else. When it quotes a failing test, fix the rule it names and keep what passes.
- [rc-008] (seed) No stubs: an empty body, `todo!()` or `unimplemented!()` is refused before anything compiles.
- [rc-009] (seed) If the contract is wrong or contradicts itself, write a NOTE line at the end AND implement it as written.
