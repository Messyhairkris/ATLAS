# Building a gate harness for a new language

A gate harness lets a cheap model's code be judged by checks it cannot read. Two exist:
Python (`codetask.py` + `gates.py`) and JavaScript (`jsharness/` + `jsrun.py`). The JS one
was **built by the crew** on 2026-09-21, and building it is the recipe below. Sources:
Qwen's drafts (`reports/harness-building.draft1.md`, and part A, job-20260921-045922-68e9),
the campaign reports in `reports/`, and `runners/member_stats.py`.

## 1. The parts, and where each lives

| Part | Python | JavaScript |
|---|---|---|
| Tell code from comments/strings | the `ast` module | `jsharness/js_lex.py` (v2 knows regex literals) |
| Import allowlist + banned names | `codetask.scan()` | `jsharness/js_imports.py` |
| Contract API exists | `gates.defines_api` | `jsharness/js_api.py` `missing_api` |
| No stubs | `gates.not_stubbed` | `jsharness/js_api.py` `stub_functions` |
| Sandboxed test run | `codetask.run_tests` (temp dir, subprocess, timeout) | `jsrun.run_node_tests` (temp dir, `node --permission`, timeout) |
| Test output -> counts + pytest-shaped totals line | pytest itself | `jsharness/node_tap.py` |
| One verdict, rules in order, tests never run after a static rejection | `task_types.code_task_gates` | `jsharness/js_gate.py` |
| Task types + playbooks | `code_task`, `code_tests` | `js_code_task`, `js_code_tests` |

Qwen's first draft said the Python harness has no API or stub check; it had not opened
`gates.py` and marked the claim (inferred). It does: `defines_api` and `not_stubbed`.

## 2. Build order

Lexer -> (import scanner, API/stub reader, test-output parser) -> gate -> runner and task
types. Everything above the lexer asks "is this word code?", so the lexer is accepted
first and the others must import it (a campaign `depends`). Modules accepted in an earlier
round are reused with `uses`. The runner and task-type wiring is architect work: it
touches the harness itself, so a large model writes it on a branch.

## 3. The recipe

1. **Write the parts in the harness's own language.** The JS gate is Python modules, so
   the existing Python gate judged the crew while they built the new one.
2. **Contract checklist** (the reason 5 of Qwen's 5 modules passed first try):
   exact API block first; numbered rules, first match wins; a worked-example table with
   one row per rule; the import allowlist in one line; anything touching the machine
   passed in as a callable; the house style appended (`HOUSE_STYLE.md` or
   `JS_HOUSE_STYLE.md`).
3. **Validate every contract before spending a request**: reference implementation +
   hidden tests; references go in `hidden_tests/reference/`. This caught two contract
   faults in round 1 and a wrong expectation in a lexer test.
4. **Template output needs a filled-in example, generated from the reference.** A
   `{placeholder}` template with no example was copied literally.
5. **Test the harness on real code before trusting a verdict.** The v1 lexer called a
   correct module unsafe because a quote inside `/"/g` looked like a string.
6. **Run the crew's modules together** against every hidden test and their own
   cross-tests, then `python -m crew unify` (keeps a lint fix only if tests still pass),
   then read for what tools miss. Only then move them into the harness.
7. **A second wall.** Static checks decide; the runtime sandbox (`--permission` for Node)
   catches what they miss.

## 4. What failed, and the class of each (Qwen, part A)

| campaign | what failed | class | what was changed |
|---|---|---|---|
| js-harness | two contract faults | CONTRACT | reference validation before submission |
| js-harness | gate misread a real module (regex) | CONTRACT (scoping: v1 excluded regexes) | lexer v2 |
| js-harness | every Barry attempt: HTTP 500 / timeout, logged "unknown", escalation spent | PROVIDER | not counted, backoff, `provider_down` after 3 |
| js-harness | empty replies at ~36.8k tokens vs a 32768 ceiling | HARNESS | Barry 49152 |
| js-harness-r2 | still logged "unknown": `Crew._brief` dropped the error | HARNESS | brief carries `error`; verified on a real record |
| splat-single-file | answers without SUBMIT discarded unjudged | HARNESS | one-file answers accepted; every gate still applies |
| splat-single-file | dropped `from` when rewriting | MEMBER | author swapped |
| splat-single-file | `{S(modules)}` emitted literally | CONTRACT | exact generated example |
| splat-single-file-r2 | re-indented a byte-exact template (3/9/3 fails, then a syntax error) | MEMBER | Qwen authored r3: accepted first try, 2 requests |
| splat-single-file-r3 | Nemotron's tests omitted the JSON quotes the contract shows | MEMBER | module accepted on the hidden tests; failed against the reference too |

Of 10 failures, 3 were the harness's, 3 the contract's, 1 the provider's, and only 3 the
members' own.

## 5. Members (from `runners/member_stats.py`, all code campaigns to 2026-09-21)

| member | modules accepted | first try | tests accepted | attempts | requests |
|---|---|---|---|---|---|
| Qwen | 5/5 | 5 | 2/2 | 7 | 20 |
| Hoss | 2/2 | 2 | 4/4 | 6 | 7 |
| Nemotron | 4/6 | 4 | 2/3 | 18 | 54 |
| Barry | 1/2 | 1 | 2/3 | 13 | 18 (undercounted: failed jobs record no requests) |

- **Qwen** - default author for anything exact (templates, byte formats) and the best tester.
- **Hoss** - cheapest: first-try modules at 1 request; wordy. Fine for simple modules.
- **Nemotron** - strong logic modules; "improves" text that must be copied verbatim; careless tests.
- **Barry** - unmeasured: his model failed at the provider on most runs. Keep him off critical paths.

## 6. Report tasks (digests) - what the guide itself taught

- One question per job. A digest over seven sources ran out of tokens before submitting;
  split in two, part A passed in 3 requests.
- Preloading is not free: every request re-sends the context. Preload only what the one
  question needs.
- Never ask a member for arithmetic; the grounding gate refuses numbers not in a source
  (playbook rule rd-014). Compute in a runner and let the digest quote it.
- A denied folder silently empties a digest (`crew/campaigns/**` is denied). Put evidence
  in `crew/reports/`. If a preload is missing, the member should say so first (rd-013).

## 7. Rust (2026-10-20): what was different

Rust is the first gate for NATIVE code, so the recipe changed in three places (details:
`rsharness/README.md`):

- **The PA wrote the gate, not the crew.** Node has `--permission` as a second wall;
  native code has none, so the allowlist scan is the wall and the PA must vouch for it.
  Its tests are written as 39 bypass attempts (`rsharness/tests/test_rs_gate.py`), and
  every crate added to a profile is read for I/O first (that found
  `imageproc::utils::load_image_or_panic`, and `imageproc` re-exporting `image`).
- **Profiles instead of an import allowlist per contract.** The member writes one file
  into a fixed crate (`rsharness/profiles/<name>/`, locked, offline, no build.rs, doc
  tests off); the profile lists the crates and their banned items.
- **Resource walls are a job object**, tested with a real endless loop, a 16 GB
  allocation loop and a child-process spawn before any member ran.

Also new: `runners/rs_mutants.py` (one-token mutants, the Rust twin of mutants.py),
which found a real gap in the first photo_tools hidden tests (6 CLI survivors) before
any member was judged by them. Harness faults found by the first campaigns: a freshly
linked test .exe can be locked by the virus scanner (WinError 32 - now retried), and
parallel campaigns collided on the provider's per-model concurrency (now a cross-process
slot per model in core.py, `rate_limit.concurrent_requests_per_model`).

## 8. For the next language (C#, GDScript, ...)

Copy unchanged: the campaign loop, provider-error handling, the gate step shape, the
contract checklist, reference validation, the build discipline above.
Write new: a lexer, an import/banned-name scanner, an API/stub reader, a parser for the
language's test output that emits a pytest-shaped totals line, a gate combining them, and a
runner with that language's sandbox. The C# launcher in Splat Studio is the obvious first
customer.
