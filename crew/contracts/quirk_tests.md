# Contract: quirk_tests.py - a forced failure hidden inside a try block

Part of the crew's **quirk linter**: zero-token checks for mistakes a model is known to
make. This one is a test-writing habit: putting `assert False` (Python) or
`assert.fail(...)` (JavaScript) inside a `try` block to prove an exception is raised.
Under `python -O` the assert disappears, and in both languages a broad `except`/`catch`
can swallow the failure itself, so the test can pass when nothing was raised. The house
style forbids it; this module finds it. Pure text in, line numbers out.

## Public API

```python
def python_fail_in_try(source: str) -> list[int]: ...
def js_fail_in_try(source: str) -> list[int]: ...
def fail_in_try(source: str, language: str) -> list[int]: ...
```

Allowed imports: `re`. Nothing else.

Lines are split on `\n` and numbered from 1. Results are line numbers in increasing
order, each once.

## python_fail_in_try(source)

A line is reported when ALL hold:

1. it contains `assert` followed by whitespace and then the word `False`
   (regex `\bassert\s+False\b`), and its stripped text does not start with `#`;
2. walking upward from it, skipping blank lines, the FIRST line with fewer leading
   spaces than it starts (after its leading spaces) with `try` followed by optional
   spaces and `:`.

So an `assert False` directly inside a `try:` body is reported; one inside `except:`,
inside `else:`, at module level, or nested one level deeper under an `if` inside the
try (its nearest less-indented line is the `if`) is not.

## js_fail_in_try(source)

A line is reported when it contains `assert`, optional spaces, `.`, optional spaces,
`fail`, optional spaces, `(` (regex `\bassert\s*\.\s*fail\s*\(`) and that call is inside
the braces of a `try {` block:

1. Walk the source character by character, tracking brace depth. `try` followed by
   optional whitespace and `{` (regex `\btry\s*\{`) opens a try block: depth goes up by
   one and that depth is remembered as an open try. Every other `{` raises the depth;
   every `}` lowers it, and if it closes a depth remembered as an open try, that try is
   no longer open.
2. A line whose `assert.fail(` appears while a try is open is reported. Because a whole
   line is processed before it is checked, also report a line where `try {` appears
   earlier on the same line than `assert.fail(` (a one-line try).

Braces inside strings or comments are not special-cased (known limitation).

## fail_in_try(source, language)

`"python"` -> `python_fail_in_try`, `"javascript"` -> `js_fail_in_try`, anything else
raises `ValueError` whose message contains the language.

## Worked examples

| Python source | result |
|---|---|
| `try:\n    f()\n    assert False\nexcept ValueError:\n    pass` | `[3]` |
| `try:\n    f()\nexcept ValueError:\n    assert False` | `[]` |
| `assert False` | `[]` |
| `try:\n    if x:\n        assert False\nexcept E:\n    pass` | `[]` |
| `try:\n    f()\n\n    assert False  # no raise\nexcept E:\n    pass` | `[4]` |
| `try:\n    # assert False\n    f()\nexcept E:\n    pass` | `[]` |
| `def t():\n    try:\n        g()\n        assert  False\n    except E:\n        pass` | `[4]` |

| JavaScript source | result |
|---|---|
| `try {\n  f();\n  assert.fail("no throw");\n} catch (e) {}` | `[3]` |
| `try {\n  f();\n} catch (e) {\n  assert.fail("x");\n}` | `[]` |
| `assert.fail("plain");` | `[]` |
| `try { f(); assert.fail("one line"); } catch (e) {}` | `[1]` |
| `try {\n  if (x) {\n    assert . fail("nested");\n  }\n} catch (e) {}` | `[3]` |
| `try {\n  f();\n} finally {}\nassert.fail("after");` | `[]` |

| call | result |
|---|---|
| `fail_in_try("x", "ruby")` | raises `ValueError` mentioning `ruby` |
