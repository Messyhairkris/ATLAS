## 6933db0 crew: packer round 3 - same contract, Qwen authors, Nemotron tests

r2 with Nemotron: every attempt judged (parser fix held), 3/9/3 failures then a
syntax error (duplicate const). Consistent defect: indents the verbatim page
template despite an exact worked example. Swapping author isolates member vs contract.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 5ecc269 fix(crew): accept a one-file answer that forgot SUBMIT; packer contract gets a worked page

splat-single-file: Nemotron's attempts 1, 3 and 4 were the file name plus a
javascript fence, or bare code, and were discarded as invalid without being judged
(contract_abandoned). A single expected file is now taken from one fenced block or
from bare code; every gate still applies. Attempt 2 was judged and failed 9 hidden
tests: it dropped 'from' when rewriting specifiers (member bug) and emitted the
contract's {S(modules)} placeholders literally (contract fault - the template had
no filled-in example). Contract now has an exact generated example.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 8e56ac2 feat(crew): install the crew-built JS gate; route .js campaign tasks to it

Round 2 (js-harness-r2): js_lex v2 (Nemotron), js_api (Qwen), js_gate (Nemotron)
all accepted first try, plus Hoss's two test files; 13 requests. Barry's lexer
tests died on provider 500s again - and were STILL logged 'unknown', because
Crew._brief never carried the job error to the campaign. Fixed and verified on a
real failed job record this time. Modules pass 172 hidden + 90 crew tests together;
crew unify took lint from 16 findings to 1. Reference implementations now live in
hidden_tests/reference (members cannot read it).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 95d2aa1 fix(crew): provider outages are not attempts; Barry ceiling 49152; JS harness round 2

Round 1 (js-harness): 6/10 accepted, 5 first-try, 16 requests. js_api never got
written: every Barry attempt died on HTTP 500 / ReadTimeout from the provider, was
logged as 'unknown', and still consumed an escalation. Now a provider error is not
counted, backs off, and stops the task after three in a row with 'provider_down'.
Barry's two empty replies came at ~36.8k tokens against a 32768 ceiling.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 8aa0bf9 feat(crew): JS harness - contracts, hidden tests, sandboxed Node runner, js task types

Five contracts (lexer, imports/forbidden globals, exports/stubs, TAP parser, gate)
for the crew to build in the js-harness campaign; each validated against a
reference implementation before submission (the check caught two contract faults).
jsrun.py runs Node with --permission so crew JS cannot read outside its temp dir,
write, or spawn. js_code_task / js_code_tests reuse the contract loop. Lexer
contract amended with regex literals after the gate misread a real module.
First customer: splat_single_file.md (Splat Studio one-file export).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 3fdba06 feat(bench): hear the device memory, not just read about it

Kris's rule for testing: "Testing that they conceivably work is your realm... but
a human will not want to guess." So profiles.py gets a panel in the sandbox he
already used: the devices it remembers, each with its own speech and alert
volumes, a lock that visibly refuses, and a "speak with its own volume" button
whose whole job is to sound different from the slider.

The reconnect hint is shown but never acted on - the bench says WOULD ASK WINDOWS,
and says "tried recently, 30s to wait" on a second press. Nothing touches the
radio, which is the same caution that came out of wedging it once.

Profiles persist in runs/crew/outbox/bench_profiles.json, readable in Notepad.

Test pass attached: 26 items across four sections - the three things his desk test
pass flagged, the profiles panel, VtoT itself speaking (with the config key to
turn it on and off), and four decisions for him, including whether software should
really reconnect a headset by itself.

Driven headlessly before shipping: remember, per-device volume, a lock refusing a
change, persistence to disk, and the reconnect cooldown.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 20a7e23 feat(crew): measure whether a test file tests anything, and grade this round

A passing suite proves nothing on its own, so `crew/runners/mutants.py` seeds one
mechanical defect at a time - flip a comparison, swap a boolean, nudge a number,
drop a `not` - and counts which the tests catch. Every survivor is printed with
its line, so a weak test is a specific thing to fix. No model is involved: it is
the same measurement every time, for free, on any accepted module.

First results on profiles.py, 40 seeded defects:

* Hoss's test file catches 26 (65%) - a third walk straight through, and its own
  comment guesses the headset cap at 99 when it is 65, with an assertion weak
  enough to hide the guess. Graded C+.
* The hidden tests catch 34 (85%), and the remainder are equivalent mutants.
  Graded A for Qwen's module: 43/43 hidden tests first try, zero mechanical lint
  findings after Unify, and it is better than my own reference in three places.

Two holes the measurement found in MY hidden tests are now closed: `last_used > 0`
became `> 1` and `last_attempt > 0` became `>= 0` with every test still green.
209 hidden-test cases now pass across six accepted modules.

The mutator also had to learn not to mutate prose: it changed "and" to "or" inside
a docstring and then called the tests weak for not noticing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 5a4e4f5 feat(desk): notice a file changing from the moment he decides, not the handoff

speech.py made this concrete: he approved it at 15:10, and by 17:20 it had grown
the whole device-profiles layer. His approval was for a file that no longer
existed and the desk said nothing, because the fingerprint was only taken when
work was sent.

It is taken at the decision now, so anything decided and then changed comes back
marked [new] whatever state it is in. `updated_since_sent` becomes
`changed_since_he_looked`, which is what it actually means.

speech.py itself is back in his queue as pending, with the origin line saying
why. His note field stays his.

Also queued for review: profiles.py (Qwen) and test_profiles.py (Hoss), accepted
in the tts-profiles campaign in 7 requests.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## d7ee747 fix(campaign): an attempt gets a token ceiling that fits the work

Three attempts in a row died as budget_tokens at the 60k default without writing
a file at all, which reads like the model failing when it is our ceiling: Qwen
spends ~78k tokens writing a 200-line module from a 6k-character contract. A
campaign can now set tokens_per_attempt, defaulting to 150k. Tokens are nearly
free; requests are the metered resource.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 7a49e60 feat(crew): a campaign can build on an earlier campaign's accepted work

profiles.py has to import devices.py, which the crew wrote and had accepted
yesterday and which is already sitting in the workspace. `depends` cannot say
that - it means "a task in this campaign that must finish first" - so a task can
now declare `uses`, which hands the module to the author and to the tester
without gating the start. A named module that is not there is a loud CrewError,
because quietly handing the author nothing would look like the model failing.

Also from the first run of tts-profiles, which failed:

* Qwen's 16384 output ceiling cannot hold a 200-line module plus its reasoning,
  so three retries in a row died as budget_tokens without producing a file at
  all. Qwen goes to 32768 and Hoss to 24576 - the same fix Barry needed.
* Attempt 1 passed 42 of 43 hidden tests. The one failure was mine: the contract
  said a name must be "a non-empty string", Qwen implemented exactly that, and
  the hidden test demanded that three spaces be refused too. The contract now
  says what the tests mean.

3 new tests for `uses` (84 in the crew suite).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 0022526 fix(unify): follow the same hidden-test naming convention as the auditor

A hardcoded map meant unify --workspace could not find tests for a module
accepted after the map was written, and broke outright when the auditor stopped
exporting it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## dd28cb7 feat(desk): a button that says the work was handed over, and what happens next

Kris used the Review Desk and answered the test pass. His one thing: "I would
add a button that confirms everything is complete and tells the user the next
steps." And: "It says they are, but there is no confirmation" that an agent was
told.

So the desk now has a moment where he says go:

* SEND TO THE AGENT, which names its own count, and a modal that lists what
  happens to each kind of decision - approved work applied, rejections revised
  with his note, questions answered and brought back, defers left alone - then
  what HE does next, which is usually nothing, with the line to paste if he
  wants it picked up now.
* The same modal appears by itself when the last item is decided, once per batch.
* handoff.json, sent.json and handoff.log record the handover, so there is a
  history of decisions and a timestamp he can see.
* Approved work leaves the list once sent; a file touched after he sent it comes
  back marked [new] in orange, which is his "color change showing when they have
  been updated for a new review".
* Ctrl+wheel, A- and A+ resize the file, the index and the note box, remembered
  between sessions - "My eyes are bad".

for_agent.json is still written on every save, so pressing nothing loses nothing.

Also: check_accepted paired modules with hidden tests from a hardcoded list, so
the three Review Desk modules were loaded but never judged. It pairs by
convention now - 226 hidden-test cases across all seven accepted modules.

Tests: 10 new in the suite (91 total), 27 checks driven against the real window.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 62264ff feat(crew): the Review Desk - a window where Kris decides and the agent finds out

Kris asked for it and then asked where it was, which was fair: only the logic
existed. This is the window.

crew/runners/review_desk.py, with the Crew's own modules doing the deciding
(vendored into crew/reviewdesk/ with provenance): review_rules by Nemotron,
review_index by Qwen, review_anchors by Hoss.

Three rules it cannot bend:
- approve needs no words; reject, question and defer are refused without them
- a decision is never overwritten, not even by a fresh pull from the crew
- for_agent.json is rewritten on every save, so Claude or Crush can see what is
  waiting and what to do without being asked

Notes attach to lines AND to a quote of them, so an anchor reports itself as
unchanged, moved, ambiguous or STALE rather than drifting onto different code.

Two defects found by driving the real window:
- review_rules.validate answered with the bare word "note" - true, and useless on
  screen. My contract only asked for a problem "mentioning note", which is too
  weak a specification; it now demands a sentence naming the decision and saying
  what to do, and Nemotron revised the module in 8 requests.
- a member labelling its fence ```python instead of ```thing.py had its
  submission rejected as a bad output path. That is our parser misreading a good
  file: every common language tag is now recognised, with tests.

71 crew tests pass. A test pass document and a .bat launcher ship with it.

## d3db228 feat(crew): read the provider quotas instead of modelling them

Synthetic returns x-synthetic-quotas on every response with the live truth, and
reading it corrected two false assumptions we had been working under:

- a cheap-model call costs 0.0333 requests, not 1, so the governor was ~30x too
  cautious and would idle a campaign that had plenty of headroom;
- requests are usually NOT the binding limit. At the time of measurement 99.99%
  of the five-hour requests were available and 6.9% of the weekly credit pool
  was ($3.32 of $48). A request-only governor runs straight into a credit wall.

v3-service/providers/quotas.py records each reading and names the binding limit;
the governor consults it first and keeps its bucket model only as a fallback for
before the provider has answered once. Six new tests cover the authoritative
path, including the credit wall that was previously invisible. 68 tests pass.

Also: verbalize revised by Qwen for the contraction rule plus spell mode, and
crew/vendor.py re-run so VtoT has the current modules with provenance.

## 8e49de2 feat(crew): vendor accepted modules into a real project, with provenance

`python -m crew vendor <accepted> <package>` moves crew output into a project the
way it should be moved: it rewrites sibling imports to relative form (the one
mismatch between a flat contract file and a package), prepends a header naming the
author and the contract, writes PROVENANCE.md listing every file and every line
changed, and re-runs the hidden tests against the rewritten files before claiming
success. A vendor step that breaks what it vendors is worse than none.

Used it for VtoT's src/tts: one import line changed across four modules, and the
hidden tests still pass.

Also: devices.py revised by Hoss in ONE request after Kris's hardware test -
per-device volume ranges (headset 0-65, speakers 1-100, never silently muted) and
the rule that the hands-free endpoint is never chosen while another headset
endpoint exists. 160 hidden tests pass. The bench gained a real STOP that purges
speech mid-word, and now finds an interpreter that has comtypes instead of dying
in a thread.

## 05539cd fix(bench): find its own interpreter, pick the endpoint that works, recover

Kris's launch failed with ModuleNotFoundError: comtypes, because `python` on his
PATH is a uv-managed 3.11 while the working interpreter is 3.14. The bench now
detects that and re-runs itself under a Python that can reach Windows speech,
saying so; "Launch TTS bench.bat" does the same for a double-click. The worker's
imports moved inside its try, so an engine failure reaches the window instead of
a console traceback nobody sees.

Endpoints, after measuring what he asked for: hands-free speaks ONCE and then
blocks forever, and wedges the headset's radio for both endpoints until it is
reconnected. The bench therefore defaults to the A2DP endpoint, labels
hands-free "(wedges after one)" in red, and has a "restart the speech engine"
button - a COM call blocked in a driver cannot be cancelled, so recovery means
abandoning that thread and starting a new one, which the log says plainly.

## 1906bc8 fix(bench): make the crew's modules testable by a human, with sound

Kris ran the first bench and reported: "No audio ever played, there was no way
to trigger audio, the buttons did things, but nothing seem to produce spoken
words." Three causes, all measured on his machine before being changed:

1. SpVoice.Speak() ran on the UI thread. One utterance took 9.17s on the stereo
   endpoint and 109s on the hands-free one, so the window froze silently.
   Speech now runs on a worker thread with its own COM apartment, and a 20s
   watchdog reports a device that never answers.
2. There was no way to just speak - audio needed type, queue, speak-the-queue.
   There is now a SPEAK THIS NOW button, a test button per device, an out-loud
   check at startup, and a one-press demo of all four modules.
3. Silence was indistinguishable from failure. Every step is logged with its
   elapsed time, and "prove audio" renders speech to a WAV and reports the peak
   amplitude (measured 6436/32767), so an OS-level silence is still visible.

The endpoint is now primed silently at startup (1.44s) so the human's first
press is not the one that waits for Bluetooth.

A real finding for the VtoT spec, not just the bench: the two endpoints of one
Bluetooth headset fight over the profile. Alternating between them wedged the
device - stereo blocked 25s and then returned a COM error. The spec currently
proposes hands-free while the mic is live and stereo when idle, which would
switch profile every time dictation starts and stops. That needs Kris's
decision; it is section 06 of the test pass.

Also: three validated contracts for the review desk Kris asked for (index,
rules, anchors - 61 hidden test cases, two of my own ambiguities found before
any credit was spent), the campaign running them, HOUSE_STYLE.md now travelling
with every contract, and a test pass document in his house style.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 3559afe feat(crew): Unify - mechanical cleanup with no LLM, and the house style

Kris asked whether the mechanical fixes could be automated so an LLM never has
to address them, on the CrossTalk principle of automating what can be automated.
They can, and this does it.

crew/unify.py runs ruff over staged crew output in three stages - safe fixes,
unsafe fixes, formatter - and keeps each stage ONLY if the file still passes its
tests afterwards, reverting otherwise. So an automatic rewrite can never quietly
change behaviour. A module is verified by its hidden tests; a test file is
verified by still passing against the module it tests, because a cleanup that
made a test stop testing would be worse than the lint it fixed. The airlock scan
runs again after every stage, so cleanup cannot widen what code may do.

Measured on the first campaign's output: 61 of 73 findings are mechanical. The
other 12 are reported with the reason a person must decide - a fabricated
docstring, a duplicated result dict, a type hint that understates the contract,
an operation ordered so a failure still consumes an id. The tool flags those and
refuses to guess.

Also: crew/contracts/HOUSE_STYLE.md, to be pasted into every future contract,
because all 64 findings in the first campaign were things nobody had asked for in
writing; a graded code review of the crew's unaided work (campaign grade B+, with
per-member grades, a 30-mutant audit at 93%, branch coverage and size ratios);
and a crew-tasking skill for both Claude and Crush, marked experimental.

Not wired into the gate pipeline: Kris tests the raw output first, then the
unified version, and only then does this move into the base Crew MCP.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 45be500 fix(crew): the campaign's own defects, found by running it

The first real campaign completed 8 of 8 tasks, and the run exposed six faults
in the harness around it. All six are fixed here.

Model handling:
- per-member output ceilings (defaults.max_tokens_by_member). Barry spent 18-20k
  tokens per reply reasoning and returned three EMPTY answers at a 16384 ceiling,
  failing a task that it then passed on retry. That is our budget, not its
  competence.
- the empty-reply nudge now says the budget went on thinking, instead of only
  that the reply was empty

Reporting:
- the report separated gate failures from stop reasons; it had called
  empty_replies a possible contract gap, which would have sent us editing a
  contract instead of a ceiling

Load lab:
- each job writes to its own log file. Every job's stdout went to a pipe nothing
  drained until the job exited, so a chatty job blocked on its own output while
  the lab waited for it - the run never finished
- a timed-out job has its whole process tree killed, not just the parent
- a heartbeat names every running job and its elapsed time, so a long job cannot
  look like a hung lab
- the memory floor can be a share of RAM: a fixed 2000MB floor stalled the first
  run for nine minutes on a box with 1876MB free, and repeated holds now collapse
  into one line with a duration

Tuned result: 5 of 5 suites in 20.1s, CPU peak 100%, 40-104MB per job.
98 tests pass.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 743b6d4 feat(crew): coding tasks, teams, campaigns and a load lab

The crew can now write code, which is the first output that gets EXECUTED, so
the design starts there: crew/codetask.py refuses any submission that imports
outside an allowlist or reaches the filesystem, network or another process, and
only then runs it in a throwaway directory with a timeout.

- contracts in crew/contracts/, each validated against a reference
  implementation first: 146 hidden test cases, all green, so a failure belongs
  to the member and not to the spec
- crew/hidden_tests/ is denied to every member, so "it works" is never the
  author's own opinion
- code_task writes a module; code_tests has a DIFFERENT member test it from the
  same contract without seeing the code, and a disagreement escalates
- crew/campaign.py runs a project unattended: author+tester teams, dependency
  order so a later module imports an earlier accepted one, three attempts with
  the test output as feedback, senior directives, then a recorded failure;
  budget and deadline both stop new work; status.json never looks idle
- crew/report.py writes the per-team scorecard and ties each recommendation to
  a number in it
- crew/runners/load_lab.py stresses the box under a psutil governor
- crew/runners/check_accepted.py re-audits the whole accepted set together

The dry run with a fake model (zero credits) caught four real defects first:
str.replace and list.remove were banned as "escapes", the airlock refused a
legitimate cross-module import, dependencies were not transitive, and code_task
had no registered playbook so every job failed before the model was called.

98 tests pass.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 1f993dd feat(harness): the provider layer, the experiment battery and the Crew MCP server

Everything this fork has added so far, committed in one baseline so a bad
decision can be undone (Kris: "any other ways we can protect our work just in
case a bad decision doesn't ruin the project completely").

- provider layer: providers.json registry, registry/telemetry modules, patched
  adapters and llm_client, so ATLAS's LLM boundary points at hosted
  OpenAI-compatible APIs with per-call cost and request accounting
- experiments: best-attempt grading, transactional parts, the verification
  ladder with a status-window Windows Sandbox runner and an injected probe
- crew/: the proto-CrossTalk work queue served over MCP - read-only tools, a
  request-budget governor, zero-token gates, playbooks, roster stages, and the
  three testers (test_triage, ui_sweep with readiness waiting, format_check)
- tests: 82 passing (fake model, no provider calls)

runs/ stays local: it holds job state, telemetry and staged output.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

