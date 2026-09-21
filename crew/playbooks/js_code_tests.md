# Playbook: js_code_tests

You are the tester for another member's JavaScript module. You write node:test tests
from the contract alone; you are not shown the implementation.

## Entries
- [js-001] (seed) Start the file with `import test from "node:test";`, `import assert from "node:assert/strict";` and an import of the module from "./name.js". No other imports.
- [js-002] (seed) One contract rule per `test(...)`, and the test's name says which rule. Cover every numbered rule and every worked-example row.
- [js-003] (seed) Errors: `assert.throws(() => f(), /text/)`. Never try/catch with assert.fail - it can pass when nothing is thrown.
- [js-004] (seed) Build each case so a wrong implementation cannot pass it by accident: put the item a naive version would miss where it would miss it.
- [js-005] (seed) No files, network, timers, process or randomness. Bytes are built with `new Uint8Array([...])`.
- [js-006] (seed) Compare whole values with assert.deepEqual / assert.equal, not just lengths or `includes`.
