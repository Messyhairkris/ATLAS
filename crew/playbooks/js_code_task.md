# Playbook: js_code_task

You are writing one complete JavaScript ES module against a contract. The harness
runs node:test tests you never see against it, under Node with no file, network or
process access. You cannot argue with them; you can only satisfy the contract.

## Entries
- [jt-001] (seed) Write the WHOLE file every time, from the first line to the last. Not a diff, not a fragment. A partial file is a failed task.
- [jt-002] (seed) The contract's API block is exact: every name is `export`ed at module level, spelled the same way, including constants. `module.exports` and `require` are refused.
- [jt-003] (seed) Only the imports the contract allows; an accepted module is imported as "./name.js". Outside strings you may not use eval, Function, process, require, fetch, XMLHttpRequest, WebSocket, Worker, globalThis, window or document - a page or runtime object the contract needs is passed in, or appears only inside a string you are generating.
- [jt-004] (seed) No stubs. An empty body or a lone `throw new Error("...")` in a function is a failure, not progress.
- [jt-005] (seed) Read the worked examples as tests. Every table row is a case that will be checked; walk your code through each row before you submit.
- [jt-006] (seed) When the contract gives text verbatim (a template, a message), reproduce it byte for byte: same indentation, same quotes, same line endings.
- [jt-007] (seed) Rules are ordered: the first match wins. Validate before you build or allocate anything.
- [jt-008] (seed) When the feedback quotes a failing test, fix the cause it names and keep what already passes.
- [jt-009] (seed) If the contract is wrong or contradicts itself, write a NOTE line at the end AND implement it as written.
