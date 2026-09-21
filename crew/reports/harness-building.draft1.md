---
title: How to build a gate harness for a new language
tags: [research, harness, js-harness, code-task]
---

A gate harness is an airlock: a static safety scan runs first, and only if it passes does the code execute, "in a throwaway directory, as a separate process, with a timeout" [src: codetask.py]. The Python harness is codetask.py plus zero-token gates in gates.py; the JavaScript harness is a runner (jsrun.py) over the five crew-written modules in jsharness/ [src: jsrun.py] [src: jsharness/README.md]. The JS modules were built in the order the README lists them - lexer, imports, API, TAP, then the gate that imports all of them - and each was judged by hidden tests before the next module depended on it (inferred) [src: jsharness/README.md] [src: jsharness/js_gate.py].

## Findings

### 1. Parts of a harness, and which file implements each

Python:
- Static safety scan: `scan()` in codetask.py reads the submitted source as an AST and refuses anything that could reach outside a pure function - no eval/exec/compile/__import__, no open(), no dunder escapes (`__globals__`, `__subclasses__`) [src: codetask.py].
- Import allowlist: the same `scan()`; `ALLOWED_IMPORTS` is a fixed set, `extra_imports` names the crew's own already-accepted modules and pytest, and "Nothing else is ever importable, so a member cannot widen this itself" [src: codetask.py].
- API check / stub check: (not stated in source) - no separate API or stub check appears in the portion of codetask.py I opened (inferred) [src: codetask.py].
- Sandboxed test run: `run_tests()` executes the code "in a throwaway directory, as a separate process, with a timeout" [src: codetask.py].
- Totals line: (not stated in source) - no totals line appears in the portion I opened (inferred); gates.py says each gate returns a step `{"rung", "file", "ok", "detail"}`, "the same shape the experiment runners use, so experiments/attempts.py can grade submissions" [src: gates.py].

JavaScript:
- Static safety scan: jsrun.py says "The static checks (lexer, import allowlist, forbidden globals, API, stubs) and the TAP parsing live in crew/jsharness/" [src: jsrun.py].
- Lexer: js_lex.py (v2, regex literals), authored by Nemotron [src: jsharness/README.md].
- Import allowlist + forbidden globals: js_imports.py - js_gate.py imports `check_imports, forbidden_uses` from it [src: jsharness/js_gate.py].
- API check + stub check: js_api.py - js_gate.py imports `missing_api, stub_functions` from it [src: jsharness/js_gate.py].
- Sandboxed test run: node_tap.py parses TAP output, and jsrun.py runs "crew-written JavaScript under Node" [src: jsharness/README.md] [src: jsrun.py].
- Verdicts/totals: js_gate.py defines `VERDICTS = ("accepted", "unsafe", "missing_api", "stubs", "tests_...")`; the tuple is clipped in my read, so the full list is (not stated in source) (inferred) [src: jsharness/js_gate.py].

### 2. Order the JavaScript parts were built, and why

- The README table lists the modules in the order js_lex.py, js_imports.py, js_api.py, node_tap.py, js_gate.py, each "judged by hidden tests in `crew/hidden_tests/test_jsh_*.py` and cross-tested by another member" [src: jsharness/README.md].
- js_gate.py imports from js_api, js_imports, and node_tap, so it could only be written after those three existed; the gate is the last module [src: jsharness/js_gate.py].
- js_lex is the base: js_imports and js_api need a lexer to find import statements and API uses (inferred) [src: jsharness/README.md].
- Why the order mattered: each module was judged by hidden tests and cross-tested before the next module depended on it, so a broken lexer would not silently corrupt the import and API checks (inferred) [src: jsharness/README.md].

### 3. What went wrong in the three campaigns

js-harness:
- Provider, not member: "js-harness 2026-09-21: four of Barry's attempts died" from provider failures; campaign.py decrements the attempt counter because the death "is not an attempt and a senior has nothing to review", and the README records "Barry's v2 tests never ran (provider 500s)" [src: campaign.py] [src: jsharness/README.md].
- Harness mistake: js_lex "re-joins earlier text at every '/', so it is quadratic in the number of slashes; 0.04 s on a 51 KB module, not meant for megabyte bundles" [src: jsharness/README.md].
- js-harness-r2: (not stated in source) - the README refers to "js-harness campaigns" in the plural, but none of the files I opened describes what went wrong in the second campaign (inferred) [src: jsharness/README.md].

splat-single-file:
- Member mistake: "splat-single-file 2026-09-21: Nemotron answered three attempts with the file..." - the rest of the line is clipped in my search result, so what the file contained and what was changed is (not stated in source) (inferred) [src: agent.py].
- Budget context: campaign.py notes a member who "spent ~78k tokens on a 200-line module and three attempts in a row died"; the surrounding context is clipped, so I cannot attribute this to a specific campaign (not stated in source) (inferred) [src: campaign.py].

### 4. Contract rules that made first-try acceptance likely (checklist)

- [ ] 88 characters maximum per line; two blank lines between top-level functions/classes, one between methods; imports standard library first then task modules, each group alphabetical, no unused imports [src: contracts/HOUSE_STYLE.md].
- [ ] Built-in generics (`list[dict[str, int]]`), `str | None`; annotate every public function's arguments and return type; a type hint must be true [src: contracts/HOUSE_STYLE.md].
- [ ] Docstring on every module, public function and class; it says why or what rule; never invent a reason [src: contracts/HOUSE_STYLE.md].
- [ ] pytest style: plain `test_*` functions, bare `assert`, `pytest.raises` never `try/except` with `assert False` (under `python -O` an assert is removed); one rule per test; construct the case so it can only pass for the right reason [src: contracts/HOUSE_STYLE.md].
- [ ] Say when the contract is wrong: write a NOTE line at the end of the answer AND implement it as written [src: contracts/HOUSE_STYLE.md].
- [ ] Order operations so nothing is consumed by a failure - do not allocate an id, take a slot, or record a count before the check that might reject the work [src: contracts/HOUSE_STYLE.md].
- [ ] Do not repeat a literal structure (write one small helper); do not wrap a one-line expression in a helper used twice [src: contracts/HOUSE_STYLE.md].
- [ ] Contract design: anything that needs the real machine is passed IN as a callable, so the module stays pure and the scan is easy to satisfy [src: codetask.py].

### 5. A third-language harness (C#, GDScript, ...): copy unchanged vs write new

Copy unchanged:
- The airlock pattern: scan first, run only if clean, in a throwaway directory, as a separate process, with a timeout [src: codetask.py].
- The gate step shape `{"rung", "file", "ok", "detail"}` so attempts.py can grade submissions [src: gates.py].
- The campaign loop: attempts, provider-death detection (markers like "500 Internal Server Error", "502 Bad Gateway", "503 Service"), escalation to a senior for DIRECTIVES after `max_attempts` [src: campaign.py].
- The build discipline: each module judged by hidden tests and cross-tested by another member before the next module depends on it [src: jsharness/README.md].
- The house-style contract section, pasted into every code_task and code_tests contract [src: contracts/HOUSE_STYLE.md].

Write new:
- A lexer for the language (js_lex.py equivalent; the quadratic-slash bug is the warning to design around) [src: jsharness/README.md].
- An import allowlist + forbidden-globals check (js_imports.py equivalent) [src: jsharness/js_gate.py].
- An API check and a stub check (js_api.py equivalent) [src: jsharness/js_gate.py].
- A test-output parser for the language's runner (node_tap.py equivalent) [src: jsharness/js_gate.py].
- A gate module combining them with a verdict list (js_gate.py equivalent) [src: jsharness/js_gate.py].
- A runner that wires the static checks to the language runtime (jsrun.py equivalent) [src: jsrun.py].

## Open questions

- What exactly went wrong in js-harness-r2 and what changed: the campaign reports are outside my read roots and the preloaded js-harness-commits.md was unavailable; the README only says "js-harness campaigns" in the plural (not stated in source) (inferred) [src: jsharness/README.md].
- The full VERDICTS tuple in js_gate.py and whether a totals line is printed: my read was clipped (not stated in source) (inferred) [src: jsharness/js_gate.py].
- What Nemotron's three splat-single-file attempts contained and what was changed: the agent.py line is clipped (not stated in source) (inferred) [src: agent.py].
- Whether the Python harness has a separate API/stub check: the portion of codetask.py I opened shows scan() and run_tests() but no such check (not stated in source) (inferred) [src: codetask.py].

## Sources

- codetask.py: Python airlock - scan(), run_tests(), import allowlists [src: codetask.py]
- gates.py: gate step shape [src: gates.py]
- jsrun.py: JS runner docstring [src: jsrun.py]
- jsharness/README.md: module table, authors/testers, known quadratic lexer bug [src: jsharness/README.md]
- jsharness/js_gate.py: imports and VERDICTS [src: jsharness/js_gate.py]
- contracts/HOUSE_STYLE.md: contract checklist [src: contracts/HOUSE_STYLE.md]
- campaign.py: attempt loop, provider-death handling (via search) [src: campaign.py]
- agent.py: splat-single-file note (via search) [src: agent.py]
