# Contract: js_api.py - the public API of an ES module, and stub detection

Part of the **JS harness**. The Python gate checks that every contract name exists
and that no function is a stub; this is the same for JavaScript. It MUST use the
accepted `js_lex` module (`from js_lex import code_only`) so that comments and
strings can never look like exports.

## Public API

```python
def exported_names(source: str) -> list[str]: ...
def missing_api(source: str, required: list[str]) -> list[str]: ...
def stub_functions(source: str) -> list[str]: ...
```

Allowed imports: `re`, and the accepted `js_lex`. Nothing else.

## exported_names(source)

Work on `code_only(source)`. Find every `export` that is a whole word (the character
before it is not a letter, digit, `_`, `$` or `.`), followed by whitespace. What comes
next decides the names; the first matching rule wins:

1. `default` -> the name `"default"`.
2. optional `async`, then `function`, optional `*`, then a NAME -> NAME.
3. `class` NAME -> NAME.
4. `const`, `let` or `var`, then a NAME -> NAME. **Only the first declarator is
   reported**: `export const A = 1, B = 2` gives `A` only. A destructuring pattern
   (`export const { a } = o`) gives nothing.
5. `*` `as` NAME (a namespace re-export) -> NAME. A bare `export * from "m"` gives
   nothing.
6. `{` ... `}` -> split the inside on commas, ignore empty parts, and for each part
   the exported name is its LAST whitespace-separated word: `a` -> `a`,
   `b as c` -> `c`, `d as default` -> `default`. The same applies to
   `export { a } from "m"`. (`export {` directly, with no space, also counts.)

NAME is `[A-Za-z_$][A-Za-z0-9_$]*`. Return names in order of first appearance, each
only once.

## missing_api(source, required)

The names in `required` that are not in `exported_names(source)`, in the order of
`required`.

## stub_functions(source)

Work on `code_only(source)`. For every **named function declaration** - the word
`function` (whole word, as above), optional `*`, a NAME, then `(` - exported or not,
async or not:

1. find the `)` that closes that `(` by counting nested `(` `)`;
2. the body is the text between the next `{` after it and its matching `}`, counting
   nested `{` `}`;
3. the function is a **stub** when the body, stripped of whitespace, is empty, OR is
   exactly one `throw new Error(...)` whose argument is empty or a single string -
   after `code_only` a string is `""`, so `throw new Error("not done");` arrives as
   `throw new Error("");`. Whitespace between the tokens and a trailing `;` are
   allowed.

Return stub names in order of appearance. Arrow functions and methods are not
checked. A comment-only body is empty, because `code_only` turned the comment into
a space.

## Worked examples

| source | exported_names(source) |
|---|---|
| `export default 1` | `["default"]` |
| `export function go() {}` | `["go"]` |
| `export async function load() {}` | `["load"]` |
| `export function* gen() {}` | `["gen"]` |
| `export class Viewer {}` | `["Viewer"]` |
| `export const A = 1, B = 2` | `["A"]` |
| `export let x; export var y` | `["x", "y"]` |
| `export const { a } = o` | `[]` |
| `export { a, b as c, d as default }` | `["a", "c", "default"]` |
| `export { a, }` | `["a"]` |
| `export * as ns from "m"` | `["ns"]` |
| `export * from "m"` | `[]` |
| `// export const hidden = 1` | `[]` |
| `const s = "export const fake = 1"` | `[]` |
| `export function a(){} export { a }` | `["a"]` |
| `reexport const q = 1` | `[]` |

| call | result |
|---|---|
| `missing_api("export const A = 1", ["B", "A", "C"])` | `["B", "C"]` |
| `missing_api("export { A, B }", ["A", "B"])` | `[]` |

| source | stub_functions(source) |
|---|---|
| `function a() {}` | `["a"]` |
| `export async function b() { /* later */ }` | `["b"]` |
| `function c() { throw new Error("not implemented"); }` | `["c"]` |
| `function d() { throw new Error() }` | `["d"]` |
| `function e(x = {}) { return x; }` | `[]` |
| `function f(a = {}) {}` | `["f"]` |
| `function g() { if (x) { throw new Error("bad"); } }` | `[]` |
| `function h() { throw new Error("a" + b); }` | `[]` |
| `const i = () => {}` | `[]` |
| `function j() { return 1 } function k() {}` | `["k"]` |
