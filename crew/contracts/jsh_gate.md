# Contract: js_gate.py - the verdict on a crew-written JavaScript module

The top of the **JS harness**: it combines the three accepted modules into one
decision, the way the Python code_task gate does. You MUST import them:

```python
from js_api import missing_api, stub_functions
from js_imports import check_imports, forbidden_uses
from node_tap import parse_tap
```

## Public API

```python
VERDICTS = ("accepted", "unsafe", "missing_api", "stubs", "tests_failed")

def judge(source: str, api: list[str], allowed_imports: set[str],
          run_tests: Callable[[str], str]) -> dict: ...
```

Allowed imports: `collections` (for `collections.abc.Callable`), `typing`, and the
three accepted modules above. `run_tests` is passed IN: the harness uses it to run
Node on the source and hand back the TAP text. This module never runs anything
itself.

## judge(...)

Returns `{"verdict": str, "problems": list[str], "counts": dict | None}`. The rules
apply **in order and the first failing one decides**:

1. **unsafe** - problems are, in this order: `"forbidden global: NAME"` for each name
   in `forbidden_uses(source)`, then `"import not allowed: SPEC"` for each in
   `check_imports(source, allowed_imports)`. If there is at least one, the verdict is
   `unsafe`.
2. **missing_api** - `"not exported: NAME"` for each name in
   `missing_api(source, api)`.
3. **stubs** - `"stub: NAME"` for each name in `stub_functions(source)`.
4. Only now call `run_tests(source)` - **exactly once**, and never when rules 1-3
   rejected the module: running untrusted code that already failed a static check is
   the one thing this gate exists to prevent. Parse the result with `parse_tap`;
   `counts` is its `"counts"`. Let `failed = fail + cancelled` (missing keys are 0).
   - `failed > 0` -> `tests_failed` with problems `["N failed"]`;
   - otherwise, if `pass` is 0 or missing -> `tests_failed` with problems
     `["no test passed"]`.
5. Otherwise `accepted` with problems `[]`.

`counts` is `None` for rules 1-3 and the parsed counts for rules 4-5.

## Worked examples

```python
ALLOWED = {"./three.js"}
API = ["go"]
GOOD = 'import * as T from "./three.js";\nexport function go() { return 1; }'
PASS_TAP = "ok 1 - a\n# pass 1\n# fail 0\n"
```

| source | run_tests returns | verdict | problems |
|---|---|---|---|
| `GOOD` | `PASS_TAP` | `accepted` | `[]` |
| `export function go(){ return fetch(1) }` | (never called) | `unsafe` | `["forbidden global: fetch"]` |
| `import "fs"; export function go(){ return 1 }` | (never called) | `unsafe` | `["import not allowed: fs"]` |
| `import "fs"; export function go(){ eval(1) }` | (never called) | `unsafe` | `["forbidden global: eval", "import not allowed: fs"]` |
| `export function other(){ return 1 }` | (never called) | `missing_api` | `["not exported: go"]` |
| `export function go(){}` | (never called) | `stubs` | `["stub: go"]` |
| `GOOD` | `"not ok 1 - a\n# pass 0\n# fail 1\n"` | `tests_failed` | `["1 failed"]` |
| `GOOD` | `"# pass 2\n# cancelled 1\n"` | `tests_failed` | `["1 failed"]` |
| `GOOD` | `""` | `tests_failed` | `["no test passed"]` |

In every row `api` is `API` and `allowed_imports` is `ALLOWED`. For `accepted`,
`counts` is `{"pass": 1, "fail": 0}`.
