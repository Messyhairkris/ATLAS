# Contract: js_imports.py - what a JavaScript module imports, and what it must not touch

Part of the **JS harness**. The Python gate allowlists imports and bans names like
`eval` and `open`; this module is the same check for JavaScript. It MUST use the
accepted `js_lex` module (`from js_lex import code_only, segments`) rather than
re-implementing comment and string handling.

## Public API

```python
FORBIDDEN_GLOBALS = ("eval", "Function", "process", "require", "fetch",
                     "XMLHttpRequest", "WebSocket", "Worker", "globalThis",
                     "window", "document")

def imports(source: str) -> list[str]: ...
def check_imports(source: str, allowed: set[str]) -> list[str]: ...
def forbidden_uses(source: str) -> list[str]: ...
```

Allowed imports: `re`, and the accepted `js_lex`. Nothing else.

## imports(source)

Go through `segments(source)`, **skipping comment segments entirely**. A **string**
segment is an import specifier when the CODE text since the previous string or
template - all code segments in between joined together, comments left out - with
trailing whitespace removed, ends with one of:

1. the word `from`
2. the word `import`
3. `import`, optional whitespace, `(`, optional whitespace
4. `require`, optional whitespace, `(`, optional whitespace

"The word" means the character before it is not a letter, digit, `_`, `$` or `.`
(or there is no character before it). So `x.from "a"` and `reimport "a"` are not
imports. A string right after another string or template is never a specifier (there is
no code in between). So `import a from /* c */ "b"` still finds `b`.

The specifier is the string with its two quote characters removed; escapes are not
processed. Templates are never specifiers. Return specifiers in order of
appearance, duplicates kept.

## check_imports(source, allowed)

The specifiers from `imports(source)` that are not in `allowed` (exact match), each
once, sorted.

## forbidden_uses(source)

Look only at `code_only(source)`. Find every identifier (`[A-Za-z_$][A-Za-z0-9_$]*`)
that is exactly one of `FORBIDDEN_GLOBALS` and is NOT a property access - that is,
the nearest non-whitespace character before it is not `.`. Return each name once,
sorted. `processed`, `obj.fetch`, `a?.window`, `obj . process` and `"eval"` are all
fine.

## Worked examples

| source | imports(source) |
|---|---|
| `import a from "./a.js";` | `["./a.js"]` |
| `import "./side.js";` | `["./side.js"]` |
| `export { x } from './x.js'` | `["./x.js"]` |
| `export * as ns from "n"` | `["n"]` |
| `const m = await import( "dyn" )` | `["dyn"]` |
| `const fs = require('fs')` | `["fs"]` |
| `// import a from "no"` | `[]` |
| `x.from "no"` | `[]` |
| `reimport "no"` | `[]` |
| `const s = "from"; f("a")` | `[]` |
| `` import(`tpl`) `` | `[]` |
| `import a from /* c */ "b"` | `["b"]` |
| `import a from "b"; import c from "b"` | `["b", "b"]` |

| call | result |
|---|---|
| `check_imports('import a from "b"; import "c"', {"b"})` | `["c"]` |
| `check_imports('import "z"; import "a"; import "z"', set())` | `["a", "z"]` |

| source | forbidden_uses(source) |
|---|---|
| `fetch(url)` | `["fetch"]` |
| `obj.fetch(url)` | `[]` |
| `a?.window` | `[]` |
| `obj . process` | `[]` |
| `const processed = 1` | `[]` |
| `eval("x"); window.alert(1); eval(y)` | `["eval", "window"]` |
| `new Function("return 1")` | `["Function"]` |
| `// fetch(x)` | `[]` |
| `"document"` | `[]` |
