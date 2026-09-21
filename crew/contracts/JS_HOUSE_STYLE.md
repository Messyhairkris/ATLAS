# House style for crew-written JavaScript

Appended to every `js_code_task` and `js_code_tests` contract. Same reasons as the
Python house style: formatting nobody asked for in writing does not happen.

## Layout

- ES modules only: `export function`, `export const`, `import x from "./y.js"`.
  Never `module.exports` or `require`.
- 100 characters maximum per line. Two-space indentation. Semicolons at the end of
  statements. Double quotes for strings unless the string contains one.
- `const` by default, `let` only when the name is reassigned, never `var` - except
  inside a code template the contract gives you verbatim.
- No banner comments. No commented-out code.

## Structure

- Do not repeat a literal structure. One small helper beats four copies.
- Prefer one clear pass over a clever one. Other crew members read this.
- Do not reach for a global the contract did not list. Anything from the outside
  world is passed in as an argument.

## Comments

- A comment says why or which rule, never what the next line obviously does.
- **Never invent a reason.** If the contract does not say why, describe the rule and
  stop.

## Tests (node:test)

- `import test from "node:test";` and `import assert from "node:assert/strict";`.
- One rule per `test(...)`, named after the rule it checks.
- `assert.throws(() => f(), /message/)` for errors - never try/catch with
  `assert.fail`.
- Build each case so it can only pass for the right reason.

## The two things no tool can check for you

1. **Say when the contract is wrong.** Write a NOTE line at the end of your answer
   AND implement it as written.
2. **Order operations so nothing is consumed by a failure.** Validate before you
   allocate, count or record anything.
