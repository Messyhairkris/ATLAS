# quirks - zero-token checks for mistakes a model is known to make

Built by the crew in the quirk-linter campaign (2026-09-21), judged by hidden tests
(`crew/hidden_tests/test_quirk_*.py`) and cross-tested.

| module | catches | author | tester |
|---|---|---|---|
| quirk_indent.py | verbatim contract text re-indented (Nemotron: 29 lines in one real attempt); finds and fixes it | Gordon (DeepSeek-V4.1-Flash), first try, 2 requests | Qwen |
| quirk_tests.py | assert False / assert.fail inside a try block | Barry (GLM-5.3-Flash), first judged attempt, 2 requests, after two provider errors not counted | Hoss |

## Wiring (crew/quirklint.py, called from Crew.run_job's grade step)

- **code_task / js_code_task:** after autofix, `fix_indent_drift` restores the contract's
  indentation on verbatim text; each repair is recorded as an autofix note.
- **code_tests / js_code_tests:** `fail_in_try` findings become a failing `quirks` gate
  step naming the lines, so the member is told exactly what to change. Never rewritten.

Verified end to end (crew/quirks/checks/test_quirklint_e2e.py, fake chat through Crew.run_job): a
correct packer with drifted template lines is repaired and accepted by the hidden tests;
a test file with assert.fail inside try is failed with the line number.

Known limit: lines shorter than MIN_CHARS (`}`, `};`) are skipped - the contract has
them at several depths, so the key is ambiguous. A v2 could place them by the matched
lines around them.
