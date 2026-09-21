# Campaign report: js-harness-r2

**Goal:** Finish the JS harness. Round 1 accepted the lexer, import scanner and TAP parser; the export reader never got a word written (Barry's model returned HTTP 500s and timeouts), which blocked the gate. The lexer also has to learn regex literals: the gate misread a real module because a quote inside /"/g looked like a string.

**Outcome: partial** - 5 of 6 tasks accepted, 1 failed, 0 never started.
11 requests, 135204 tokens, 54.3 minutes of member time.

First-attempt acceptance: 5/5 (100%). 2.2 requests per accepted task.

## Teams

| Team | Members | Tasks | Accepted | First try | Failed | Attempts | Requests | Tokens | Escalations | Minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| Ledger | Hoss, Qwen | 2 | 2 | 2 | 0 | 2 | 2 | 39720 | 0 | 2.5 |
| Judge | Hoss, Nemotron | 2 | 2 | 2 | 0 | 2 | 4 | 33233 | 0 | 1.3 |
| Lexer | Barry, Nemotron | 2 | 1 | 1 | 1 | 5 | 5 | 62251 | 1 | 50.5 |

## Tasks

| Task | Kind | Team | Member | State | Attempts | Requests | Minutes |
|---|---|---|---|---|---|---|---|
| js_lex | module | Lexer | Nemotron | accepted | 1 | 5 | 3.4 |
| js_lex-tests | tests | Lexer | Barry | failed | 4 | 0 | 47.1 |
| js_api | module | Ledger | Qwen | accepted | 1 | 1 | 2.2 |
| js_api-tests | tests | Ledger | Hoss | accepted | 1 | 1 | 0.3 |
| js_gate | module | Judge | Nemotron | accepted | 1 | 3 | 1.0 |
| js_gate-tests | tests | Judge | Hoss | accepted | 1 | 1 | 0.3 |

## What actually went wrong

Every failed attempt, grouped by what stopped it. A GATE name (safety, api, hidden tests, tests green, no stubs) means the work was judged and found wanting. A STOP REASON (empty_replies, output_truncated, no_progress) means the member never reached judgement at all - that is a budget or task-size problem, not a quality one.

| Check | Times it stopped an attempt |
|---|---|
| unknown | 4 |

## Tasks that did not finish

### Lexer - Barry: tests (4 attempts, 1 escalations)
Last failure: unknown

## What to change next time

- 'unknown' stopped 4 attempt(s). If it names a gate, check that the contract states the requirement explicitly; if it names a stop reason, the member never reached judgement and the budget or the task size is the thing to change.
- 1 task(s) needed three or more attempts. Those are the ones to split into two smaller tasks next time.

## Evidence

- job store: `C:\Users\user\ATLAS-api-harness\runs\crew\jobs`
- progress log: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\js-harness-r2\progress.log`
- live status: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\js-harness-r2\status.json`
- accepted modules: `C:\Users\user\ATLAS-api-harness\runs\crew\outbox\workspace`
