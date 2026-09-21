# Campaign report: js-harness

**Goal:** Build the gates that let the crew be judged on JavaScript the way the AST scan and pytest judge Python: a lexer that tells code from comments and strings, an import and forbidden-global scanner, an export and stub reader, a Node TAP parser, and the gate that combines them. Every author is also a tester of someone else's module, so the crew checks itself. First real use: Splat Studio's JS.

**Outcome: partial** - 6 of 10 tasks accepted, 1 failed, 3 never started.
16 requests, 252100 tokens, 89.0 minutes of member time.

First-attempt acceptance: 5/6 (83%). 2.7 requests per accepted task.

## Teams

| Team | Members | Tasks | Accepted | First try | Failed | Attempts | Requests | Tokens | Escalations | Minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| Tap | Nemotron, Qwen | 2 | 2 | 2 | 0 | 2 | 3 | 49880 | 0 | 3.5 |
| Lexer | Nemotron, Qwen | 2 | 2 | 2 | 0 | 2 | 4 | 37462 | 0 | 4.3 |
| Customs | Barry, Hoss | 2 | 2 | 1 | 0 | 3 | 9 | 164758 | 0 | 21.7 |
| Ledger | Barry, Hoss | 2 | 0 | 0 | 1 | 4 | 0 | 0 | 1 | 59.5 |
| Judge | Hoss, Nemotron | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 |

## Tasks

| Task | Kind | Team | Member | State | Attempts | Requests | Minutes |
|---|---|---|---|---|---|---|---|
| js_lex | module | Lexer | Nemotron | accepted | 1 | 2 | 2.4 |
| js_lex-tests | tests | Lexer | Qwen | accepted | 1 | 2 | 1.9 |
| js_imports | module | Customs | Hoss | accepted | 1 | 1 | 0.2 |
| js_imports-tests | tests | Customs | Barry | accepted | 2 | 8 | 21.5 |
| js_api | module | Ledger | Barry | failed | 4 | 0 | 59.5 |
| js_api-tests | tests | Ledger | Hoss | waiting | 0 | 0 | 0.0 |
| node_tap | module | Tap | Qwen | accepted | 1 | 1 | 1.9 |
| node_tap-tests | tests | Tap | Nemotron | accepted | 1 | 2 | 1.6 |
| js_gate | module | Judge | Nemotron | waiting | 0 | 0 | 0.0 |
| js_gate-tests | tests | Judge | Hoss | waiting | 0 | 0 | 0.0 |

## What actually went wrong

Every failed attempt, grouped by what stopped it. A GATE name (safety, api, hidden tests, tests green, no stubs) means the work was judged and found wanting. A STOP REASON (empty_replies, output_truncated, no_progress) means the member never reached judgement at all - that is a budget or task-size problem, not a quality one.

| Check | Times it stopped an attempt |
|---|---|
| unknown | 4 |
| empty_replies | 1 |

## Tasks that did not finish

### Ledger - Barry: module (4 attempts, 1 escalations)
Last failure: unknown

## What to change next time

- 'unknown' stopped 4 attempt(s). If it names a gate, check that the contract states the requirement explicitly; if it names a stop reason, the member never reached judgement and the budget or the task size is the thing to change.
- 1 attempt(s) ended in EMPTY replies: the member spent its whole output budget reasoning and never wrote an answer. That is a ceiling problem, not a contract problem. Raise `defaults.max_tokens_by_member` for that model (GLM-4.7-Flash needed 32768) rather than editing the contract.
- 1 task(s) needed three or more attempts. Those are the ones to split into two smaller tasks next time.
- 3 task(s) never started, so the budget or the deadline bound the run before the roster did. Raise the budget or reduce the task count, not the quality bar.

## Evidence

- job store: `C:\Users\user\ATLAS-api-harness\runs\crew\jobs`
- progress log: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\js-harness\progress.log`
- live status: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\js-harness\status.json`
- accepted modules: `C:\Users\user\ATLAS-api-harness\runs\crew\outbox\workspace`
