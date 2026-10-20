# rsharness - the Rust gate

Built 2026-10-20 for Kris's "we will be using Rust a lot moving forward": the crew had
gates for Python, JavaScript and AutoHotkey, none for Rust. Unlike the JS gate (built by
the crew), this one was written by the PA, because it is the only wall between
crew-written NATIVE code and the workstation, and the PA must be able to vouch for it.

| part | file | job |
|---|---|---|
| lexer | `rs_lex.py` | code vs comments (nested), strings (raw, byte, C), chars vs lifetimes; offsets for mutants |
| allowlist scan | `rs_scan.py` | what a file may name before it compiles (below) |
| API and stubs | `rs_api.py` | `pub` items / `Type::method` exist; empty, `todo!`, `unimplemented!` bodies; `#[test]` count |
| cargo output | `cargo_out.py` | libtest results -> counts, failures, pytest-shaped totals; rustc errors trimmed, hidden-test source never quoted |
| runner | `../rsrun.py` | profile crate, slots, job objects, verdicts |
| task types | `../task_types.py` | `rs_code_task`, `rs_code_tests` |
| mutants | `../runners/rs_mutants.py` | do the tests catch one-token defects? |
| tests | `tests/test_rs_gate.py` | 74, including 39 bypass attempts the scan must refuse |

## The safety model, and what it does not cover

Node has `--permission`; native code has nothing like it. So:

1. **Allowlist, not blocklist.** A file may name std minus `fs`, `io`, `net`, `process`,
   `env`, `path`, `os`, `ffi`, `thread`, `ptr` (and the rest of std's machine-facing
   modules - only the listed safe modules pass), the crates its profile lists minus their
   I/O, and its own crate. No `unsafe`, `extern`, `include!`/`include_str!`/
   `include_bytes!`, `env!`/`option_env!`, `asm!`, `macro_rules!`, inner attributes,
   `mod name;`, glob imports of foreign crates, or whole-crate imports (`use std as s`).
   A crate root anywhere in a path is judged (so `imageproc::image::open` is caught as
   `image::open`). Without unsafe or FFI, safe Rust cannot reach the OS except through
   those names.
2. **The crate is fixed.** The profile's `Cargo.toml` and `Cargo.lock` are copied in;
   no `build.rs`; `--offline --locked`; doc tests off (`doctest = false`, `--tests`), so a
   code block in a `///` comment never runs.
3. **Job objects** (`rsrun._Job`): the compile tree is capped at 4 GB; each test binary
   at 2 GB, one process (no children) and a timeout; crash dialogs suppressed. Verified
   2026-10-20: a 16 GB allocation loop dies with "memory allocation ... failed"; an
   endless loop is killed at the timeout; a child process is refused (error 1816).

Not covered, written down so nobody assumes otherwise: a deliberate soundness exploit in
safe Rust (the cve-rs class) could escape rule 1. The members are cheap models writing
image code from our contracts, not adversaries; the residual risk is accepted, and the
job object still bounds memory, processes and time.

## Profiles

`profiles/<name>/` = `Cargo.toml`, `Cargo.lock`, `profile.json` (crate name; per crate
`banned_paths`, `banned_methods`, `banned_idents`). Before adding a crate to a profile,
read its public API for file, network or process access (that is how
`imageproc::utils::load_image_or_panic` was found and banned) and run
`cargo fetch` once so `--offline` works.

| profile | crates | first used |
|---|---|---|
| photo_tools | image 0.25.10 (png, jpeg), imageproc 0.27.0, clap 4.6.7 | image_convert, 2026-10-20 |

## Machine facts (8 GB, 4 cores)

Cold build of a profile's dependencies: ~3.5 min (`-j 2`, `debug = 0`), once per profile
into `runs/crew/rs_target/<profile>` (0.24 GB for photo_tools). After that a module
rebuilds and tests in 5-20 s. Three slots share the target directory; cargo's own lock
serialises compiles. C: had 0 bytes free on 2026-10-20 until idea-animator's 31 GB
incremental cache was cleared - check free space before a cold build.
