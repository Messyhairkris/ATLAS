# jsharness - the crew-built JavaScript gate

Written by the crew in the js-harness campaigns (2026-09-21), each module judged by
hidden tests in `crew/hidden_tests/test_jsh_*.py` and cross-tested by another member
(`tests/`). Moved here by hand after review; `crew/jsrun.py` imports them.

| module | author | tester |
|---|---|---|
| js_lex.py (v2, regex literals) | Nemotron | Qwen wrote the v1 tests; Barry's v2 tests never ran (provider 500s) |
| js_imports.py | Hoss | Barry |
| js_api.py | Qwen | Hoss |
| node_tap.py | Qwen | Nemotron |
| js_gate.py | Nemotron | Hoss |

Style cleaned by `python -m crew unify` (kept only where tests still passed).
Known: js_lex re-joins earlier text at every '/', so it is quadratic in the number of
slashes; 0.04 s on a 51 KB module, not meant for megabyte bundles.
