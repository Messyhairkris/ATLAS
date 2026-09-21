# quirks - zero-token checks for mistakes a model is known to make

Built by the crew in the quirk-linter campaign (2026-09-21), judged by hidden tests
(`crew/hidden_tests/test_quirk_*.py`) and cross-tested.

| module | catches | author | tester |
|---|---|---|---|
| quirk_indent.py | verbatim contract text re-indented (Nemotron: 29 lines in one real attempt); finds and fixes it | Gordon (DeepSeek-V4.1-Flash), first try, 2 requests | Qwen |
| quirk_tests.py | assert False / assert.fail inside a try block | Barry (GLM-5.3-Flash), first judged attempt, 2 requests, after two provider errors not counted | Hoss |

Not yet wired into `autofix.py` (next step: run before the gates on every code submission).
