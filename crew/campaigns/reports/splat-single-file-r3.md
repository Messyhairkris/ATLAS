# Campaign report: splat-single-file-r3

**Goal:** First JavaScript job judged by the crew-built JS harness: the Splat Studio module that packs an exported portfolio site into one .html that plays from a double-click. Kris has never been able to view an export because browsers will not run the site from file://.

**Outcome: partial** - 1 of 2 tasks accepted, 1 failed, 0 never started.
14 requests, 255699 tokens, 15.5 minutes of member time.

First-attempt acceptance: 1/1 (100%). 14.0 requests per accepted task.

## Teams

| Team | Members | Tasks | Accepted | First try | Failed | Attempts | Requests | Tokens | Escalations | Minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| Packer | Nemotron, Qwen | 2 | 1 | 1 | 1 | 5 | 14 | 255699 | 1 | 15.5 |

## Tasks

| Task | Kind | Team | Member | State | Attempts | Requests | Minutes |
|---|---|---|---|---|---|---|---|
| single_file | module | Packer | Qwen | accepted | 1 | 2 | 3.4 |
| single_file-tests | tests | Packer | Nemotron | failed | 4 | 12 | 12.1 |

## What actually went wrong

Every failed attempt, grouped by what stopped it. A GATE name (safety, api, hidden tests, tests green, no stubs) means the work was judged and found wanting. A STOP REASON (empty_replies, output_truncated, no_progress) means the member never reached judgement at all - that is a budget or task-size problem, not a quality one.

| Check | Times it stopped an attempt |
|---|---|
| tests run | 4 |

## Tasks that did not finish

### Packer - Nemotron: tests (4 attempts, 1 escalations)
Last failure: tests run: the tests fail against the real module:
not ok - scriptSafe: escapes <, U+2028, U+2029 globally
not ok - packedPage: portfolio literal is correct
not ok - packedPage: modules literal is correct
  expected: |-
  actual: |-
  error: |-
  expected: '\\u003c\\u003c'
  actual: '"\\u003c\\u003c"'
  error: |-
  expected: '"\\"{\\\\\\"hello\\\\\\": \\\\\\"world\\\\\\", \\\\\\"q\\\\\\": \\\\\\"\\\\u003c>\\\\\\"}\\""'
  actual: '"{\\"hello\\": \\"world\\"'
  error: |-
  expected: `{"mod1":"var a = 1;","mod2":"console.log('hello');"}`
  actual: '{"mod1":"var a = 1'
6 failed, 20 passed in 0.14s

## What to change next time

- 'tests run' stopped 4 attempt(s). If it names a gate, check that the contract states the requirement explicitly; if it names a stop reason, the member never reached judgement and the budget or the task size is the thing to change.
- 1 task(s) needed three or more attempts. Those are the ones to split into two smaller tasks next time.

## Evidence

- job store: `C:\Users\user\ATLAS-api-harness\runs\crew\jobs`
- progress log: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\splat-single-file-r3\progress.log`
- live status: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\splat-single-file-r3\status.json`
- accepted modules: `C:\Users\user\ATLAS-api-harness\runs\crew\outbox\workspace`
