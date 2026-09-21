# Campaign report: tts-foundation

**Goal:** Build the four pure-logic modules VtoT's text-to-speech needs, with four crew teams: device policy, verbatim verbalization, chattiness levels, and the speech queue. Each module is judged by tests its author never sees, and each is cross-tested by a different team member.

**Outcome: complete** - 8 of 8 tasks accepted, 0 failed, 0 never started.
26 requests, 199248 tokens, 13.4 minutes of member time.

First-attempt acceptance: 7/8 (88%). 3.2 requests per accepted task.

## Teams

| Team | Members | Tasks | Accepted | First try | Failed | Attempts | Requests | Tokens | Escalations | Minutes |
|---|---|---|---|---|---|---|---|---|---|---|
| Pipes | Hoss, Qwen | 2 | 2 | 2 | 0 | 2 | 5 | 37129 | 0 | 1.5 |
| Echo | Barry, Hoss | 2 | 2 | 2 | 0 | 2 | 6 | 51450 | 0 | 3.4 |
| Signal | Nemotron, Qwen | 2 | 2 | 2 | 0 | 2 | 7 | 35444 | 0 | 1.5 |
| Relay | Barry, Nemotron | 2 | 2 | 1 | 0 | 3 | 8 | 75225 | 0 | 6.9 |

## Tasks

| Task | Kind | Team | Member | State | Attempts | Requests | Minutes |
|---|---|---|---|---|---|---|---|
| devices | module | Pipes | Hoss | accepted | 1 | 1 | 0.3 |
| devices-tests | tests | Pipes | Qwen | accepted | 1 | 4 | 1.2 |
| verbalize | module | Signal | Qwen | accepted | 1 | 4 | 1.0 |
| verbalize-tests | tests | Signal | Nemotron | accepted | 1 | 3 | 0.5 |
| chattiness | module | Relay | Nemotron | accepted | 1 | 2 | 0.2 |
| chattiness-tests | tests | Relay | Barry | accepted | 2 | 6 | 6.7 |
| speech_queue | module | Echo | Barry | accepted | 1 | 4 | 3.0 |
| speech_queue-tests | tests | Echo | Hoss | accepted | 1 | 2 | 0.5 |

## What actually went wrong

Every failed attempt, grouped by what stopped it. A GATE name (safety, api, hidden tests, tests green, no stubs) means the work was judged and found wanting. A STOP REASON (empty_replies, output_truncated, no_progress) means the member never reached judgement at all - that is a budget or task-size problem, not a quality one.

| Check | Times it stopped an attempt |
|---|---|
| empty_replies | 1 |

## What to change next time

- The campaign finished. Cost to beat next time: 26 requests for 8 accepted tasks (3.2 each).
- 1 attempt(s) ended in EMPTY replies: the member spent its whole output budget reasoning and never wrote an answer. That is a ceiling problem, not a contract problem. Raise `defaults.max_tokens_by_member` for that model (GLM-4.7-Flash needed 32768) rather than editing the contract.

## Evidence

- job store: `C:\Users\user\ATLAS-api-harness\runs\crew\jobs`
- progress log: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\tts-foundation\progress.log`
- live status: `C:\Users\user\ATLAS-api-harness\runs\crew\campaigns\tts-foundation\status.json`
- accepted modules: `C:\Users\user\ATLAS-api-harness\runs\crew\outbox\workspace`
