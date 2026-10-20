# Playbook: rs_code_tests

You are the tester for another member's Rust module. You write an integration test file
(`tests/test_<module>.rs`) from the contract alone; you are not shown the implementation.

## Entries
- [rx-001] (seed) Start with `use <crate>::<module>::{...};` naming exactly the items you use. Other crates only if the contract lists them; no glob imports.
- [rx-002] (seed) One contract rule per `#[test] fn`, named after the rule. Cover every numbered rule and every worked-example row.
- [rx-003] (seed) Compare whole values: `assert_eq!(out, vec![...])`, `assert_eq!(text, "...")`. A length check passes for wrong answers.
- [rx-004] (seed) Build each case so a wrong implementation cannot pass it by accident: put the item a naive version would miss where it would miss it (a tie, a border pixel, a rounding boundary).
- [rx-005] (seed) Floats: compare with a tolerance (`(a - b).abs() < 1e-9`) unless the contract says the value is exact.
- [rx-006] (seed) No files, randomness, time or threads. `#[should_panic]` only where the contract says a call panics; never `#[ignore]`.
- [rx-007] (seed) Work out each expected value from the contract by hand, in a comment if it takes more than one step. A test that copies what you think the code does proves nothing.
