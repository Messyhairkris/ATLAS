# Contract: problems_lib.py - turn a build log into the Problems pane's rows

One self-contained Python module, `problems_lib.py`. It reads the text of a compiler's or a test
runner's output and returns **problems**: one row per error or warning, each carrying the file the
problem is in and the line, so the pane can open the source at the click. This is IDE Phase 1's
pure module (`C:\Users\user\TheCrew\design\IDE design - review first (2026-10-29).md`,
"Problems" and "Pure modules ... go to the crew under hidden tests").

It is the pure half. A thin runner reads a log file and prints the rows as JSON; the window calls
that runner. **This module never touches a file, a clock, a process or the screen.**

Allowed imports: `json`, `re`, `typing`, `__future__`. Nothing else.

## Public API

```python
LOC_WITHIN = 3          # how many lines after a problem's first line its position may sit on

KINDS = [ {...cargo...}, {...pytest...} ]   # the built-in parsers, in match order

def load(settings=None) -> list: ...        # KINDS, or KINDS merged with a settings dict
def parse(text, kinds=None) -> list: ...    # the problems in `text`, in order, deduplicated
def format_problem(p) -> str: ...           # one line for the pane
```

## The shapes

A **problem** is a plain dict:

```python
{"kind": "cargo", "severity": "error", "file": "src/main.rs", "line": 12, "col": 5,
 "code": "E0308", "message": "mismatched types"}
```

- `kind` - the name of the kind that found it.
- `severity` - `"error"` or `"warning"`, and nothing else.
- `file` - the path as the tool printed it, or `None` when the output gives no position.
- `line`, `col` - ints, or `None`. `col` is only ever set when `line` is.
- `code` - the diagnostic code without its brackets (`"E0308"`), or `None`.
- `message` - the text after the colon in the head line, stripped; `""` when there is none.

A **kind** is a dict:

```python
{"name": str, "head": str, "loc": str | None, "level": str | None}
```

- `head` - a regex. It matches **the line that starts a problem**. These named groups are read:
  `level`, `code`, `message`, `file`, `line`, `col`. A kind may capture any subset.
- `loc` - an optional regex for a **following** line that carries the source position (cargo puts
  it on the `-->` line). Read for `file`, `line`, `col`. `None` when the head line carries the
  position itself.
- `level` - the fixed severity for a kind whose head line carries none (`"error"` or `"warning"`),
  or `None`.

## The built-in kinds, exactly

```python
KINDS = [
    {"name": "cargo",
     "head": r"^(?P<level>error|warning)(?:\[(?P<code>[A-Z]+\d+)\])?: (?P<message>\S.*)$",
     "loc":  r"^\s*--> (?P<file>.+?):(?P<line>\d+):(?P<col>\d+)\s*$",
     "level": None},
    {"name": "pytest",
     "head": r"^(?P<file>[^\s:]+\.py):(?P<line>\d+): (?P<message>.+)$",
     "loc":  None,
     "level": "error"},
]
```

`[k["name"] for k in KINDS] == ["cargo", "pytest"]`.

The two real lines these were written from:

```
error[E0308]: mismatched types
  --> src/main.rs:12:5

tests/test_foo.py:42: AssertionError: assert 1 == 2
```

## parse - the rules, in order

1. Split the text with `text.splitlines()`. Walk the lines **once, in order**.
2. For each line, the **first** kind whose `head` matches wins; kinds are tried in list order. A
   line that no kind matches is skipped.
3. Build the problem from that match:
   - `kind` - the kind's `name`.
   - `severity` - the head's `level` group lowercased if it captured one, else the kind's `level`,
     else `"error"`. If the result is not `"error"` or `"warning"`, use `"error"`.
   - `code` - the head's `code` group, or `None`.
   - `message` - the head's `message` group stripped, or `""`.
   - `file` - the head's `file` group, or `None`.
   - `line`, `col` - `int()` of the head's groups, or `None`.
4. If the kind has a `loc` regex **and** the problem has no `line` yet, look at the next lines,
   **at most `LOC_WITHIN`** of them, from the head line **exclusive**. The **first** line that
   matches supplies `file`, `line` and `col`; a group the match does not have stays as it was.
   Stop at that first match. A match beyond `LOC_WITHIN` lines is not used.
5. `int()` is only ever applied to a group that matched a `\d+` (so it cannot raise on a match).
6. **Dedupe:** two problems with the same `(kind, file, line, col, code, message)` are one. Keep
   the **first** occurrence and keep the original order; the returned list is never re-sorted.
7. `parse("")` and `parse(None)` both return `[]`.
8. A kind with no `name`, or with no `head`, is a settings error: `raise ValueError`.
9. `parse(text, kinds=None)` uses `KINDS`.

## load

`load()` with no argument returns `KINDS` itself.

`load(settings)` **merges** the `"kinds"` list of an already-parsed settings dict over the
built-ins:

- a kind whose `name` matches a built-in **replaces** it, in the built-in's own place (so cargo
  stays before pytest);
- a kind with a new `name` is **appended**, in the settings' order;
- a settings dict with no `"kinds"` key, or an empty list, gives the built-ins unchanged;
- a `"kinds"` that is not a list raises `ValueError`.

**The module opens no file.** It has no `open()` - the crew's airlock bans it (crew/codetask.py),
and it is banned for a reason: a module that reads the disk is not a pure module. The **runner**
(`crew/runners/problems.py`) reads the settings file with `json.load`, and passes the parsed dict
in. This is what makes a new compiler or test runner a settings change, not a code change. The
built-ins are never mutated: `load(settings)` returns a new list.

## format_problem

Build the line from these parts, each present only when it has content, joined with `": "`:

1. the position: `file`, then `:line` when `line` is set, then `:col` when `col` is set;
2. the severity, with `[code]` after it when `code` is set;
3. the message, when it is not empty.

```python
format_problem({"kind": "cargo", "severity": "error", "file": "src/main.rs", "line": 12,
                "col": 5, "code": "E0308", "message": "mismatched types"})
# "src/main.rs:12:5: error[E0308]: mismatched types"

format_problem({"kind": "cargo", "severity": "warning", "file": "src/main.rs", "line": 5,
                "col": 9, "code": None, "message": "unused variable: `x`"})
# "src/main.rs:5:9: warning: unused variable: `x`"

format_problem({"kind": "cargo", "severity": "error", "file": None, "line": None, "col": None,
                "code": None, "message": "could not compile `crew_control` (bin)"})
# "error: could not compile `crew_control` (bin)"

format_problem({"kind": "pytest", "severity": "error", "file": "tests/test_foo.py",
                "line": 42, "col": None, "code": None,
                "message": "AssertionError: assert 1 == 2"})
# "tests/test_foo.py:42: error: AssertionError: assert 1 == 2"
```

## Worked examples - parse

The text below is `CARGO` (the `|` and `= note` gutter lines are part of it and must **not**
become problems):

```
error[E0308]: mismatched types
  --> src/main.rs:12:5
   |
12 |     let x: i32 = "s";
   |            ^^^ expected `i32`, found `&str`
   |
   = note: expected type `i32`
warning: unused variable: `x`
  --> src/main.rs:5:9
```

| what is parsed | result |
|---|---|
| `CARGO` | two problems: `(cargo, error, src/main.rs, 12, 5, E0308, "mismatched types")` then `(cargo, warning, src/main.rs, 5, 9, None, "unused variable: `x`")` |
| `"error: could not compile \`crew_control\` (bin)"` | one problem, `file`, `line`, `col`, `code` all `None`, `severity` `error` |
| `"  --> src/main.rs:12:5"` alone | `[]` - a position line is not a problem on its own |
| `"   = note: expected type \`i32\`"` | `[]` |
| `"tests/test_foo.py:42: AssertionError: assert 1 == 2"` | one problem: `(pytest, error, tests/test_foo.py, 42, None, None, "AssertionError: assert 1 == 2")` |
| `""` | `[]` |
| `None` | `[]` |

The `loc` window, exactly: with

```
error: oops
line 1
line 2
line 3
  --> a.py:9:1
```

the position on the **fourth** line after the head is **not** found (`LOC_WITHIN` is 3), so `file`
is `None`. With two filler lines instead of three, `file` is `"a.py"`, `line` is `9`.

Two identical `FAILED` heads in a row give **one** problem, not two.

## Style

Type hints. A one-line docstring per public function naming the rule it implements. No `print()`.
No module-level code that runs at import beyond building `KINDS`. Follow HOUSE_STYLE.md, pasted
below this contract when the task is submitted.
