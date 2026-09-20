# ATLAS API Harness — Fork Notes

Derived from `itigges22/ATLAS` @ `ef616c5d2797f3e54dbe2aa33f8159049e144965` (AGPL-3.0 — derivative work stays AGPL, source must stay published).
Branch: `api-harness`. Experiment plan: `C:\Users\user\Documents\Obsidian\Knowledge_Base\wiki\experiments\atlas-api-harness\PLAN.md`

## What this fork does

Points ATLAS's LLM boundary at hosted OpenAI-compatible APIs (Synthetic first) instead of a local llama-server, so compact hosted models gain the ATLAS harness (V3 pipeline candidates, verification, repair) without local GPU. Everything is backward compatible: with `ATLAS_PROVIDER` unset, behavior is byte-for-byte upstream.

## The provider layer (new)

- `providers.json` (repo root) — the registry. **Adding a provider or model is a config entry, not code.**
- `v3-service/providers/registry.py` — resolution, auth (env var → optional fallback config), capability flags
- `v3-service/providers/telemetry.py` — JSONL token/latency log per call
- Patched: `v3-service/adapters.py` (LLMAdapter, EmbedAdapter), `v3-service/stages/llm_client.py` (chat_completion)

Environment:

| Var | Default | Meaning |
|---|---|---|
| `ATLAS_PROVIDER` | unset (upstream local-llama) | provider id from providers.json |
| `ATLAS_CHAT_MODEL` | first chat_models entry | model override |
| `ATLAS_PROVIDERS_FILE` | repo-root providers.json | registry location |
| `ATLAS_TELEMETRY_FILE` | `runs/telemetry.jsonl` | JSONL token log |
| `SYNTHETIC_API_KEY` | falls back to crush.json | provider key |

The Synthetic entry reads the key from `C:\Users\user\AppData\Local\crush\crush.json` if the env var is missing — zero secrets in this repo.

## The experiment battery (new)

- `experiments/godot_battery.py` — T1–T4 runner (raw mode = model alone, baseline)
- `experiments/prompts/t1.md … t4.md` — identical prompts across all models
- `experiments/verify.py` — verification ladder:
  1. **structural** — pure-Python .tscn check (host, always safe)
  2. **check-only** — `godot --headless --check-only` script compile, no execution (host, safe)
  3. **wsb-run** — full headless project load inside Windows Sandbox (T4 playability; agent code executes ONLY here; networking + vGPU off; sandbox killed after log capture)
- `tests/test_providers.py` + `tests/test_senior_review.py` — 19 unit tests, all passing as of 2026-09-18
- `experiments/senior_review.py` — escalation: junior failure goes to a senior model named with `--senior` (no default) with a compact evidence pack; senior returns root cause + ranked fix DIRECTIVES (never code); directives appended to `experiments/pattern_cache.jsonl` for batched human review

## Run it

```
cd C:\Users\user\ATLAS-api-harness
set PY=C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe
%PY% experiments\godot_battery.py --model Hoss --repair 2
%PY% experiments\godot_battery.py --model all --repair 2 --senior Claude
%PY% experiments\godot_battery.py --model Hoss --tiers 4 --repair 2 --budget 15000
```

Model nicknames (aliases in `providers.json`): **Hoss** = gpt-oss-120b, **Barry** (or `Flash`) = GLM-4.7-Flash, **Qwen** = Qwen3.8-27B, **Nemotron** = Nemotron-3-Super-120B, **Kimi** = Kimi-K3.
Key flags: `--repair N` (repair-feedback rounds per tier), `--budget N` (cumulative token cap per tier, default 15000; breach = `failure_class=budget_exceeded` + escalation), `--senior MODEL` (senior review on unrescued failures / any T4 failure).

Outputs: `runs\battery-<timestamp>\report.json` + per-tier summaries.
Live token log: `C:\Users\user\Documents\Obsidian\Knowledge_Base\wiki\experiments\atlas-api-harness\runs\telemetry.jsonl`

## P0 hygiene (Claude, 2026-09-19; review: vault `REVIEW-20260919-claude-senior.md`)

- **Best attempt, not last** (`experiments/attempts.py`, all three runners): a regression never replaces a better attempt; repairs start from the best attempt. Loop guards end a part on identical output (`no_change`), two non-improving repairs (`no_progress`), or budget. Summaries carry `best_attempt`, `stop_reason`, per-attempt scores.
- **Transactional parts** (`space_duty.py`): each attempt is gated in `runs/<run>/<part>/stage<N>/` (a copy of the project); the live project changes only when the whole part passes. Repairs ask only for failing files; the rest carry forward from the best attempt. The battery keeps its "emit the complete set" rule so older battery results stay comparable.
- **Ledger v2**: every telemetry row carries `run_id, duty, task_id, attempt, role (junior|senior), persona`, `requests: 1` (Synthetic subscriptions meter requests per 5h), `cost_usd` (null until `providers.json` pricing is filled; null never means free), and failed calls. Claude-CLI senior calls are logged with null tokens.
- **Senior is always explicit**: `senior_review.py --senior` is required (no default). `ATLAS_DENY_MODELS` makes the provider layer refuse a named model outright; it was used on 2026-09-19 to measure roster-only spend ($0.15 crew vs $1.00 Kimi in 24h) and is now EMPTY. Division of labor: Crush drives Kimi, Claude drives Claude, both delegate bounded work to the Crew (default member Hoss).
- **Librarian grounding gate**: numbers, ratios, $ amounts, and verdict words on an INDEX line must appear in the note the line links to.
- **Sandbox runner** (`experiments/sandbox/`, mapped read-only): the sandbox now sees only its own run folder + Godot + the tools. Inside, `runner.ps1` shows an always-on-top status window (stage checklist, elapsed time, live marker/probe/error lines, preview verdict), applies `debloat_profile.json` (edit to taste; logs process count + free MB before/after), runs Godot, and writes `godot.log` + `runner_done.txt`. Its own log is copied out **only on failure**. Failed run folders stay in `C:\ATLAS-wsb\run-*`; passing ones are deleted. `.wsb` turns off audio/video/printer/clipboard and caps memory (`ATLAS_WSB_MEMORY_MB`, default 3072; `ATLAS_WSB_LINGER_S`, default 4, how long the verdict stays visible).
- **Harness probe**: `harness_probe.gd` is injected as an autoload into the sandbox copy with a per-run nonce. A WSB pass now also requires `HARNESS_PROBE <nonce> SCENE_LOADED`, which agent code does not print. Nodes in group `harness_track` get positions logged every 5s (runtime tuning evidence).

## The Crew MCP server (Claude, 2026-09-19)

`crew/` is a proto-CrossTalk work queue served over MCP (`.mcp.json` for Claude Code, `crew_server.py` for Crush through its stdio wrapper). Architects submit atomic tasks. Hoss works them with read-only tools, under a request budget and loop guards. Zero-token gates check the output, reviewers approve/revise/reject, and playbooks keep the lessons. Details: `crew/README.md`. Tests: `tests/test_crew.py` (fake model, no provider calls).

Two findings from the first live job (vault_index on the lab notebook, 20 Synthetic requests over 4 runs, no Kimi):

- gpt-oss sometimes answers through its **native tool-call channel** (`message.tool_calls`, `content: null`, invented namespace `repo_browser.*`). Reading only `content` made valid work look like empty replies. The crew now accepts and maps these.
- Instructions don't hold a small model; gates do. "Read both notes" was skipped twice as a constraint. As a `must_read` gate it was satisfied on the next submission.

## Request-budget governor (Claude, 2026-09-19)

Kris's Synthetic allowance behaves like a **bucket of 500 refilling 5% every 3 hours (~8.3 requests/hour)**, not a rolling window, so `crew/ratelimit.py` tracks the level in `runs/crew/rate_state.json` from the telemetry ledger and holds jobs when it runs low, keeping a reserve for human and Crush interactive work the ledger cannot see. `crew_budget` / `python -m crew budget` report level, refill rate and hours-to-refill. The worker sleeps until there is room instead of failing jobs, which is what lets a long campaign run unattended. OpenCode runs are parsed back into the ledger so its spend is visible to the governor too.

## OpenCode in the loop — first real test (2026-09-19)

`opencode-ai@1.2.6` was already installed. Synthetic wired in as a custom provider (`@ai-sdk/openai-compatible`, `baseURL https://api.synthetic.new/v1`, key via `{env:SYNTHETIC_API_KEY}`), all four roster models registered. Headless `opencode run -m synthetic/<model> --format json` works.

First result: Hoss fixed a seeded 3-test bug end to end (verified independently: `3 passed`), 875s wall, 22 tool calls, ~194.5K input / 6.0K output, about $0.01, one malformed tool call absorbed by OpenCode. Prompt caching does work through Synthetic (289.7K cache reads).

Lessons: it is slow per turn (~40s) because prompts are large and gpt-oss reasons before answering, so it suits a **tight correction/verification step with a reduced tool set** (`agent.build.tools`), not open-ended exploration. Its requests bypass the harness ledger, so any wrapper must parse `--format json` usage back into telemetry or the governor goes blind.

## Three testers for Hoss (Claude, 2026-09-19)

- **`test_triage`** — the harness runs the project's own suite; the member explains it. VtoT's tests are standalone scripts, not pytest cases, so `crew/runners/run_test_scripts.py` runs each file: baseline **19 passed, 0 failed in 29.7s**.
- **`ui_sweep`** — `crew/runners/ui_sweep.py` launches an app and presses every control, **highlighting each in #FF7900 for half a second first** so a human can watch, with a status banner throughout, a hands-off countdown before it starts, and interference detection (keyboard/mouse input during a press marks that result unreliable, and a gate fails any report that hides it). Menus are opened with ExpandCollapse and their items pressed. On VtoT: 28 controls found, 23 pressed, 0 problems. Seeds text first, so Save and Copy act on real content, and watches folders for files written.
- **Formatting test document** — `crew/fixtures/format_test_doc.txt` (also a practice sheet for new users) plus a spec and `crew/runners/format_check.py`: each line states the formatting it should have, and the checker verifies the saved `.html`. Three lines are two-step to test removal (checked box; bold then plain; Heading 3 then body text). Page break and title page stay human-only via a saved `.fountain` check.

## Sweep timing: readiness, not a guess (Kris, 2026-09-19)

Kris watched a sweep and reported: "Testing did not give enough time for each
process or file to open. It caused a backlog and stalling, saying different
actions were happening then were on the screen at the time. First slowdown
noticed on opening the logs (it never did)." Three separate faults, all fixed:

- **A fixed settle time is a guess.** After every press the sweep now waits until
  the app answers a message again (`SendMessageTimeoutW` + `IsHungAppWindow`),
  the window list of the whole desktop stops changing, and the watched folders
  stop growing. `--settle` (0.6s) is the floor so a human can still see what
  happened; `--settle-max` (12s) is the ceiling; `--quiet` (0.6s) is how long
  calm must last. Launch waits for a *responsive* titled window, not just a
  titled one.
- **It watched the wrong windows.** Only the app's own process tree was checked,
  so a log opening in Notepad looked like nothing happening. It now diffs every
  visible top-level window on the desktop (minus the sweep's own overlay) and
  reports `external_window`.
- **The banner narrated intent.** It said "pressing: X" before the press
  finished, which is why it described actions that were not on screen yet. It
  now separates `next:` (about to act) from `seen:` (observed outcome, e.g.
  "opened Log Viewer", "wrote 1 file(s)", "NOTHING OPENED").

New events: `still_waiting` (any wait past `--report-wait-after`, so a slow
action is visible instead of silent), `stalled` (ceiling reached),
`nothing_opened` (a control whose name says it opens something opened nothing
anywhere and wrote nothing — **counted as a failure**), `dialog_would_not_close`,
and `seen` on every press. The `reports_stalls` gate fails any report that
leaves those out. Verified against a purpose-built dummy that opens its log
3.5s late, drops it silently, and freezes for 4s: the late window is now caught
(4.25s), the dropped one fails after 12.1s of visible waiting, and the freeze is
narrated rather than skipped.

## Cost evidence, second reading (2026-09-19)

Synthetic's own totals with Crush and the Crew both working: **$8.76 total, of
which Kimi-K3 is $8.50**. The entire crew roster together is **$0.26** (Qwen
$0.13, gpt-oss-120b $0.05, Nemotron $0.05, GLM-4.7-Flash $0.03). The two also
share one request pool, so running Crush and a crew campaign at the same time
hits the cooldown that stops both; the crew's own token use is small enough to
run all day when it has the pool to itself.

## Coding tasks, teams and campaigns (Claude, 2026-09-20)

The crew can now write code, which is the first task type whose output is
EXECUTED, so the whole design is about that:

- `crew/codetask.py` is the airlock. It reads a submission as an AST and refuses
  it unless every import is on an allowlist and nothing calls
  `eval/exec/compile/__import__/open`, reaches a dunder escape, or names a way
  out to the filesystem, network or another process. Only then is the code run,
  in a throwaway directory, as a separate process, with a timeout. Contracts are
  written so this is easy: anything needing the real machine is passed in as a
  callable. Stated plainly: an allowlist is not a sandbox - the real protections
  are cheap models working from our contracts, our tests, and a human moving the
  result into the project.
- **Hidden tests decide.** `crew/hidden_tests/` is denied to every member
  (`deny_globs`), so "it works" is never the author's opinion. Each contract in
  `crew/contracts/` was validated against a reference implementation before any
  model saw it: 146 test cases across four modules, all green, so a failure is
  the member's, not the spec's.
- **Two task types**: `code_task` (write the module: gates are safety scan, the
  contract's API exists, no stubs, hidden tests pass) and `code_tests` (a
  DIFFERENT member writes tests from the same contract without seeing the
  implementation; a disagreement between them is escalated, never guessed).
- **`crew/campaign.py` runs a whole project unattended.** Teams of author +
  tester, dependency-ordered tasks where a later module imports an earlier
  accepted one, three attempts with the test output as feedback, then escalation
  to a senior for DIRECTIVES (never code), then a recorded failure and the
  campaign moves on. A request budget and a wall-clock deadline both stop new
  work. `status.json` and `progress.log` update continuously - nothing ever looks
  idle. `python -m crew campaign run crew/campaigns/tts_foundation.json`
- **`crew/report.py`** writes the per-team scorecard Kris asked for: tasks,
  first-attempt acceptance, attempts, requests, tokens, escalations, minutes, the
  count of every check that failed, and recommendations tied to those numbers.
- **`crew/runners/load_lab.py`** runs several suites at once under a psutil
  governor (CPU ceiling, free-memory floor) that holds jobs back rather than
  letting the box thrash, and reports peak CPU, memory and per-job RSS. Stress
  without a crash. `python -m crew loadlab crew/campaigns/load_lab.json`
- **`crew/runners/check_accepted.py`** is the independent audit: it re-runs every
  hidden test against whatever is in the workspace now, so the accepted set is
  proven to work TOGETHER and not only inside the job that made it.

Found by the dry run, before any credits were spent: the attribute blocklist
banned `str.replace` and `list.remove` (ordinary code); the airlock did not allow
a task to import the module an earlier task had accepted; dependency modules were
not transitive, so a tester got `speech_queue.py` without the `verbalize.py` it
imports; and `code_task` had no playbook registered, which failed every job
before the model was called. 98 tests pass.

## Known gaps (explicit, by design)

- **V3 pipeline mode** (`--mode v3`) is Phase B: provider layer + battery baseline first, pipeline integration second.
- `geometric-lens` service still expects llama-server self-embeddings; substitute-representation retraining (free Synthetic nomic embeddings) is mapped in PLAN.md, not implemented.
- `proxy/` (Go) untouched; the bench/v3-service path is the experiment surface.
- Windows Sandbox run requires `C:\Godot\` (present) and Windows Sandbox feature on (enabled 2026-09-17).
