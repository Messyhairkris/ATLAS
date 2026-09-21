# Contract: node_tap.py - reading a Node test run

Part of the **JS harness**. The crew's Python work is judged by pytest; JavaScript
will be judged by `node --test --test-reporter=tap`. This module turns that TAP text
into data, and produces a pytest-shaped totals line so the crew's existing
"quote the totals verbatim" gate works on JavaScript runs unchanged.

## Public API

```python
COUNT_KEYS = ("tests", "suites", "pass", "fail", "cancelled", "skipped", "todo")

def parse_tap(text: str) -> dict: ...
def summary_line(result: dict) -> str: ...
```

Allowed imports: `re`. Nothing else.

## What real Node output looks like (Node 25, trimmed)

```
TAP version 13
# Subtest: adds
ok 1 - adds
# Subtest: fails here
not ok 2 - fails here
  ---
  duration_ms: 0.6
  ...
ok 3 - skipped one # SKIP
ok 4 - todo one # TODO
# Subtest: group
    # Subtest: inner ok
    ok 1 - inner ok
    not ok 2 - inner bad
    1..2
not ok 5 - group
1..5
# tests 7
# suites 0
# pass 2
# fail 3
# cancelled 0
# skipped 1
# todo 1
# duration_ms 239.6107
```

## parse_tap(text)

Returns `{"tests": [...], "counts": {...}, "duration_ms": float | None}`.

Look at each line on its own; lines matching neither rule are ignored.

1. **A result line**: optional leading spaces, then `ok` or `not ok`, a space, a
   number, then optionally ` - ` and a name, then optionally ` # ` and a directive
   word `SKIP` or `TODO` (any case, anything may follow the word), then the end of
   the line. It becomes

   `{"name": str, "ok": bool, "skip": bool, "todo": bool, "depth": int}`

   - `name` excludes the directive; a result with no ` - name` has name `""`;
   - `ok` is `True` for `ok`, `False` for `not ok` - a SKIP or TODO does not change it;
   - `depth` is the number of leading spaces divided by 4, rounded down.

   Results appear in the list in the order of the lines.
2. **A count line**: exactly `# KEY NUMBER`. When KEY is in `COUNT_KEYS`,
   `counts[KEY] = int(NUMBER)`. When KEY is `duration_ms`, `duration_ms` is
   `float(NUMBER)`. Other keys are ignored. `counts` contains only the keys that
   appeared.

`# Subtest: x` is neither rule. `duration_ms: 0.6` (YAML, no `#`) is neither rule.

## summary_line(result)

Take `fail`, `pass` and `skipped` from `result["counts"]` (missing means 0). Write
the non-zero ones in that order as `N failed`, `N passed`, `N skipped`, joined by
`", "`. If all three are 0, the text is `no tests ran`. Then append ` in S.SSs`,
where S is `duration_ms / 1000` with two decimals (`None` counts as 0).

## Worked examples

| text | parse_tap(text)["tests"] |
|---|---|
| `ok 1 - adds` | `[{"name": "adds", "ok": True, "skip": False, "todo": False, "depth": 0}]` |
| `not ok 2 - fails here` | name `"fails here"`, ok False, depth 0 |
| `ok 3 - skipped one # SKIP` | name `"skipped one"`, ok True, skip True, todo False |
| `ok 4 - later # todo not yet` | name `"later"`, ok True, todo True |
| `    ok 1 - inner ok` | depth 1 |
| `        not ok 7 - deep` | depth 2, ok False |
| `ok 9` | name `""` |
| `# Subtest: adds` | `[]` |
| `okay 1 - no` | `[]` |

The whole sample above parses to 7 results in line order - `adds`, `fails here`,
`skipped one`, `todo one`, `inner ok`, `inner bad`, `group` - with counts
`{"tests": 7, "suites": 0, "pass": 2, "fail": 3, "cancelled": 0, "skipped": 1,
"todo": 1}` and `duration_ms` `239.6107`.

| result counts | duration_ms | summary_line |
|---|---|---|
| `{"pass": 2, "fail": 3, "skipped": 1}` | `239.6107` | `"3 failed, 2 passed, 1 skipped in 0.24s"` |
| `{"pass": 29}` | `1200.0` | `"29 passed in 1.20s"` |
| `{"fail": 1, "pass": 0}` | `None` | `"1 failed in 0.00s"` |
| `{}` | `None` | `"no tests ran in 0.00s"` |
