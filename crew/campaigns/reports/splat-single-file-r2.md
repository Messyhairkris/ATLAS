# Campaign report: splat-single-file-r2

**Goal:** First JavaScript job judged by the crew-built JS harness: the Splat Studio module that packs an exported portfolio site into one .html that plays from a double-click. Kris has never been able to view an export because browsers will not run the site from file://.

**Outcome: failed** - 0 of 2 tasks accepted, 1 failed, 1 never started.
12 requests, 205728 tokens, 15.1 minutes of member time.

## Teams

| Team | Members | Tasks | Accepted | First try | Failed | Attempts | Requests | Tokens | Escalations | Minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| Packer | Nemotron, Qwen | 2 | 0 | 0 | 1 | 4 | 12 | 205728 | 1 | 15.1 |

## Tasks

| Task | Kind | Team | Member | State | Attempts | Requests | Minutes |
|---|---|---|---|---|---|---|---|
| single_file | module | Packer | Nemotron | failed | 4 | 12 | 15.1 |
| single_file-tests | tests | Packer | Qwen | waiting | 0 | 0 | 0.0 |

## What actually went wrong

Every failed attempt, grouped by what stopped it. A GATE name (safety, api, hidden tests, tests green, no stubs) means the work was judged and found wanting. A STOP REASON (empty_replies, output_truncated, no_progress) means the member never reached judgement at all - that is a budget or task-size problem, not a quality one.

| Check | Times it stopped an attempt |
|---|---|
| js gate | 4 |

## Tasks that did not finish

### Packer - Nemotron: module (4 attempts, 1 escalations)
Last failure: js gate: tests_failed: 1 failed
The hidden tests fail. This is the evidence; fix the module, do not argue with it.

## What to change next time

- 'js gate' stopped 4 attempt(s). If it names a gate, check that the contract states the requirement explicitly; if it names a stop reason, the member never reached judgement and the budget or the task size is the thing to change.
- 1 task(s) needed three or more attempts. Those are the ones to split into two smaller tasks next time.
- 1 task(s) never started, so the budget or the deadline bound the run before the roster did. Raise the budget or reduce the task count, not the quality bar.

## Evidence

- job store: `C:\Users\user\ATLAS-api-harness\runs\crew\jobs`
- progress log: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\splat-single-file-r2\progress.log`
- live status: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\splat-single-file-r2\status.json`
- accepted modules: `C:\Users\user\ATLAS-api-harness\runs\crew\outbox\workspace`
