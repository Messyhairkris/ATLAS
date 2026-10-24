# The Crew

A proto-CrossTalk work queue. An **architect** (Claude, Crush, or Kris) splits a
big ask into atomic tasks and submits them. A **crew member** (Hoss by default)
works each one with read-only tools. Deterministic **gates** check the result.
A **reviewer** approves, revises (with enforceable constraints), or rejects,
and adds lessons to the task type's **playbook**, so the next run starts
smarter. Every step is an ActionNode in the action log. Every run updates the
member's Performance Profile and Autonomy Stage in the roster.

```
architect ──crew_submit──► queue ──worker──► member (read-only tools, request budget)
                                               │ SUBMIT
                                               ▼
                                     gates (zero tokens) ──fail──► member retries (best kept)
                                               │ pass
                               stage Observe/Checkpoint ──► review ──approve──► written to target
                               stage Supervised/Autonomous ─────────────────► auto-applied + notice
```

## The roster (2026-09-21)

| Member | Model | Reached through | Sees images | Best at, so far |
|---|---|---|---|---|
| **Hoss** (default) | gpt-oss-120b | Synthetic | no | cheapest first-try modules (~1 request); writes long; weak tests; fast but loose research |
| **Qwen** | Qwen3.8-27B | Synthetic | yes (2/3 on a screenshot) | anything byte-exact; the best tester |
| **Nemotron** | Nemotron-3-Super-120B | Synthetic | no | clean logic modules; careless tests; loops on research |
| **Barry** | GLM-5.3-Flash (was 4.7) | Synthetic | claims yes, **wrong 4/4** - do not use | measured first time 2026-09-21: std140 accepted in 3 requests; thinks at length (ceiling 65,536) |
| **Gordon** | DeepSeek-V4.1-Flash | Synthetic | **yes (3/3)** | new 2026-09-21: first-try modules at 1 request, the most accurate researcher |
| **Haiku** | claude-haiku-4-5 | Anthropic SDK (`claude_chat.py`) | yes (not yet measured) | added 2026-09-21; needs `pip install anthropic` + `ANTHROPIC_API_KEY` |
| Kimi | Kimi-K3 | Synthetic | yes | Crush's model and the senior fallback - expensive, not a crew member |

Measured records: `python crew/runners/member_stats.py`. Vision: `VISION.md`.
Prices and limits: `SYNTHETIC_LIMITS.md`. Claude members live in `config.json`
`claude_members`, never in `providers.json`, so they stay out of Synthetic's quotas.

## Task types

| Type | Member produces | Gates | Approve does |
|---|---|---|---|
| `vault_index` | INDEX.md for one vault folder | output path, frontmatter, links resolve, every note linked, numbers grounded in what it read | writes the index (old one backed up) |
| `research_digest` | cited markdown digest answering a question | output path, frontmatter, every item cited, citations were actually opened, numbers grounded in cited text, links resolve | writes the digest (default `runs/crew/outbox/`) |
| `organize_plan` | plan.json of moves/renames/tags | schema, sources exist, targets inside the folder and collision-free | saves the plan. Moves are **not** executed in v1 |
| `test_triage` | a triage report of a test run | no invented test names, the run's summary line quoted verbatim, citations, grounding, absence claims | writes the report |
| `ui_sweep` | a report on every control pressed | no invented control names, totals quoted, interference reported, citations, grounding, absence claims | writes the report |
| `code_task` | one Python module against a contract | AST airlock (import allowlist, banned names), API present, no stubs, **hidden tests** | stages it in `outbox/workspace/` |
| `code_tests` | pytest tests for another member's accepted module, from the contract alone | airlock, enough tests, they pass against the real module | stages them in `outbox/workspace/tests/` |
| `js_code_task` / `js_code_tests` | a JavaScript ES module / `node:test` tests | the crew-built JS gate (`jsharness/`): lexer, import allowlist, forbidden globals, API, stubs, then hidden `*.test.mjs` under `node --permission` | stages them |
| `rs_code_task` / `rs_code_tests` | one Rust module (`src/<m>.rs`) of a fixed profile crate / integration tests for it | the Rust gate (`rsharness/`, 2026-10-20): allowlist scan, API, stubs, cargo build, hidden `tests/*.rs` under a job object (memory, processes, time) | stages them |
| `scout` | where information lives: path, line range and a `>` verbatim quote per finding, plus Unknowns | sections, every finding cited and quoted, quotes word for word, line numbers exist in the file, grounding, absence claims | writes the report |
| `log_clerk` | what literally happened in a log: exit codes, failures quoted exactly, earliest first. No diagnosis | sections, citations, quotes word for word from the log, failures in log order, grounding | writes the report |
| `completion_audit` | YES/NO/PARTIAL/UNKNOWN per expected artifact, and a conclusion | the harness checks existence itself: a missing path must be NO, an existing one must be opened before YES/PARTIAL; conclusion consistent with the states | writes the audit |

The three clerk types (2026-09-25) are Crush-lite's workers (`~/.crush/lite/workers`)
moved into the crew, so they run under a request budget and gates instead of as
open-ended Crush sessions. First live runs: Larry passed `log_clerk` in 2 requests
and `completion_audit` in 12 (right answer, after the gate corrected a NO to
PARTIAL); Gordon's `scout` answers were correct but need a budget above 12.

## Language-server tools (`lsp`)

A job with `"lsp": true` (a campaign: top-level `"lsp": true`; MCP: `crew_submit(lsp=True)`)
gives the member four more read-only tools - `symbols(path)`, `definition(path, name)`,
`references(path, name)`, `diagnostics(path)` - answered by real language servers
(`crew/lsp.py`, configured under `"lsp"` in `config.json`). Members name a symbol, not
a position; results outside the read roots are counted, never shown. Python uses
pylsp to navigate and ruff's built-in server (rules `E9`,`F` only) for diagnostics.
Code jobs with `lsp` also get an **`lsp` gate rung** before the hidden tests that
fails only on ERROR diagnostics (undefined names, syntax); a server that will not
start is skipped with a note, never a failure. pylsp cold-starts in ~23 s here.

Measured 2026-09-25: the same scout question with and without `lsp` cost the same
(12 requests, ~35k tokens, both correct), and 66 past Python code jobs had no
undefined-name or syntax failures for the gate to catch. Treat it as available,
not yet proven.

Every code job also passes through `quirklint.py` (verbatim templates a member
re-indented are restored; a forced failure inside `try` in a test fails). A campaign
routes a `.js` module to the JS types automatically. AutoHotkey v1 has `ahk_code_task` / `ahk_code_tests`: the crew-built static gate
(`ahk_lex`, `ahk_scan`, `ahk_api`) on the host, then the hidden tests **only inside
Windows Sandbox** (`crew/ahkrun.py`, tests use `crew/ahk/tap.ahk`). A task can be
granted `clipboard`; `Run`, `Send` and the rest stay refused. A campaign routes a
`.ahk` module automatically. Each attempt boots a sandbox - several minutes on
Kris's machine - so AHK campaigns are slow by design.

The harness does the acting in the last two: it **runs the project's own test suite**, and it **drives the app** (each control highlighted in #FF7900 for half a second, then pressed, menus opened and their items pressed). The member only explains what happened, against evidence it cannot fake.

Any task can also carry **acceptance gates**: `must_mention`, `must_read` (the member must open the file itself), `ascii_only`. A reviewer attaches `must_read`/`ascii_only` on **revise**. This turns "read X first" from an instruction a small model may skip into a check it can't skip. On the first live job this was what made Hoss read the note it had skipped twice.

## Safety posture

- **Read-only tools.** `list_dir`, `read_file`, `search`, and `fetch_url` (off unless `fetch_allowlist` in `config.json` names domains); with `lsp`, also `symbols`, `definition`, `references`, `diagnostics`. The member cannot write, run, move, or delete anything.
- **Path limits.** Paths are resolved and confined to the job's read roots. `deny_globs` (secrets, `.git`, `.obsidian`, crush.json, crew internals) always win.
- **Writes** happen only on approval (or at Supervised+), only inside `write_roots`, with a backup of anything overwritten.
- **Leash.**
  - Hard request budget (default 12).
  - Repeated identical tool calls aren't re-run; three repeats end the job.
  - Two invalid replies in a row end it; three empty replies end it.
  - The best submission is kept.
- **No self-promotion.** No MCP tool can change an Autonomy Stage. `python -m crew promote` is Kris-only. It refuses to skip stages and refuses to promote right after a failure.
- **Deny list available, currently empty.** `deny_models` in `config.json` is enforced by the provider layer; it was used to measure roster-only spend and is now off. Big models are not crew members by default: `defaults.assigned_to` is Hoss, and naming a large model in `assigned_to` usually means the task was mis-scoped.

## Cold starts (2026-10-23)

Every stdio MCP server, `crew` included, starts behind
`C:\Users\user\TheCrew\bin\mcp-keeper.exe`, which starts it again when the first
(cold) start fails or hangs; `MCP_TIMEOUT` is 90000 in the user settings. Retries are logged to
`runs/mcp-keeper/keeper.jsonl` and counted by the night report.

## Register the server

**Claude Code:** `.mcp.json` at the repo root registers `crew` for this project. Approve it when Claude Code asks.

**Crush (Windows):** add this under `"mcp"` in `%LOCALAPPDATA%\crush\crush.json`. Since
2026-10-23 it starts behind mcp-keeper, whose pipes FastMCP reads fine, so the old
`~/.octofriend/mcp/mcp_stdio_wrapper.py` (removed with Octofriend) is no longer needed:

```json
"crew": {
  "type": "stdio",
  "command": "C:\\Users\\user\\TheCrew\\bin\\mcp-keeper.exe",
  "args": ["--name", "crew", "--first-wait", "40", "--total", "85",
           "--log", "C:\\Users\\user\\ATLAS-api-harness\\runs\\mcp-keeper\\keeper.jsonl",
           "--", "C:/Users/user/AppData/Local/Programs/Python/Python314/python.exe",
           "C:/Users/user/ATLAS-api-harness/crew_server.py"],
  "env": {"CREW_CLIENT": "Crush"},
  "timeout": 120
}
```

Both clients share one queue (`runs/crew/`). Each server process runs a worker. Exclusive claims with leases decide who works which job, and a job whose worker died is reclaimed when its lease expires. `CREW_WORKER=0` starts a server without a worker.

## MCP tools

`crew_task_types` · `crew_submit` · `crew_status` (long-poll with `wait_seconds`) · `crew_result` · `crew_review` · `crew_inbox` · `crew_roster` · `crew_playbook` · `crew_budget`

## CLI (Kris)

```
python -m crew inbox
python -m crew result JOB
python -m crew review JOB approve --by Kris
python -m crew review JOB revise --by Kris --constraint "..." --must-read path.md --lesson "..."
python -m crew roster
python -m crew budget
python -m crew promote Hoss vault_index Checkpoint --by Kris
python -m crew submit spec.json --by Kris      # then: python -m crew run JOB
```

## Files

- `config.json` — roots, deny globs, fetch allowlist, deny models, test commands, rate limit, defaults
- `codetask.py` — the airlock for executable output: an AST allowlist, then a
  throwaway directory and a timeout
- `campaign.py` — runs a whole project unattended: teams, dependencies, three
  attempts, senior escalation, budget and deadline, live status
- `report.py` — the per-team scorecard and the failure breakdown
- `contracts/` + `hidden_tests/` — the specification a member works from, and the
  tests it never sees (denied in config, so it cannot read them)
- `campaigns/` — campaign and load-lab definitions
- `autofix.py` — zero-token linter: typography and near-miss names or citations are repaired before gating, and every fix is logged (it never guesses meaning)
- `runners/` — `run_test_scripts.py` (script-style suites), `ui_sweep.py` (visible control sweep), `format_check.py` (formatting test document)
  The sweep waits for **readiness**, not a fixed delay: after each press it waits until the app answers messages again, the desktop's window list stops changing and the watched folders stop growing (`--settle` floor, `--settle-max` ceiling, `--quiet` the required calm). A control whose name says it opens something must actually open something or the press fails (`nothing_opened`); a wait past `--report-wait-after` is announced in the banner and logged as `still_waiting`; a breach of the ceiling is logged as `stalled`. The banner reports what was OBSERVED ("seen: Save -> wrote 1 file(s)"), never just what is intended.
- `fixtures/format_test_doc.txt` + `.json` — the VtoT formatting test and practice document, and its machine-checkable spec
- `playbooks/*.md` — retained knowledge per task type (append-only entries with ids)
- `runs/crew/` — state:
  - `jobs/<id>/` — job.json, transcript.jsonl, output/, backup/
  - `action_log.jsonl`, `roster.json`, `claims/`, `outbox/`
- Ledger — every model call lands in the harness telemetry file, tagged `duty=crew:<type>`, `run_id=<job>`, `role=junior`, `persona`, `requests=1`

## Every tool, and when to reach for it

Building and running work:

| Command | What it is for |
|---|---|
| `python -m crew campaign run crew/campaigns/<x>.json` | a whole project: author + tester teams, dependencies (`depends` inside the campaign, `uses` for modules accepted earlier), three attempts, budget, live `status.json` and a `REPORT.md` |
| `python -m crew campaign plan <x>.json` | the task graph, before spending anything |
| `python crew/runners/research_compare.py --members A B --question q.md --name n` | the same research question to several members at once; `--read-root` sets the folder relative citations resolve against |
| `python crew/runners/load_lab.py <x>.json` | several jobs at once, measuring what it costs the machine |
| `python -m crew budget` | the live provider quota; the governor holds jobs rather than failing them |
| `python crew/runners/night_shift.py [--notify]` | zero-token night report: the day's failures by category and signature, relays, guard hits (Task Scheduler runs it at 03:00 as "The Crew night shift") |
| `python -m crew pa list` / `pa brief NAME` | who may be the PA (personnel.json `pa`) and the brief that starts their session |
| `python -m crew pa promote|demote NAME --by Kris` | Kris only, at a real console: a PA's shell is refused |
| `python crew/runners/pa_session.py --pa Gordon` | open OpenCode with an approved crew member as the PA: the brief as its agent prompt, the crew MCP, LSP and skills |

**Rework and relay (2026-10-23).** A campaign retry is handed the best submission so far and
its failed checks and reworks it; after `attempts_per_member` failures (default 2), or when a
member's model is down, the task relays to the next holder of its post who has not had it.
Campaign keys: `rework`, `relay`, `attempts_per_member`; per task `post`, `relay` (and
`test_post`, `test_relay`).

**PAs (2026-10-23).** Claude, Kimi, Qwen and Gordon are approved PAs. The brief
(`crew/pa_brief.py`) is injected once per session - a SessionStart hook for Claude Code, the
agent prompt for OpenCode - never per reply, under `pa.brief_max_chars`. The Windows command
guard (`C:\Users\user\TheCrew\bin\winguard-hook.exe`, crew-built by Gordon) is a
PreToolUse hook on Claude Code's PowerShell tool; hits go to `runs/guard/hits.jsonl`.

Checking what came back - run the evidence, do not read and nod:

| Command | What it proves |
|---|---|
| `python crew/runners/check_accepted.py [--workspace DIR]` | every accepted module, together, against every hidden test (pairs by name: `test_<stem>.py` or `test_tts_<stem>.py`) |
| `python crew/runners/mutants.py --module m.py [--hidden]` | whether a test file tests anything: seeds one defect at a time and lists the survivors by line |
| `python crew/runners/member_stats.py` | each member's record across every campaign |
| `python crew/runners/rs_mutants.py --profile P --module m.rs --tests t.rs [--deps ..]` | the Rust twin of mutants.py: one-token defects, built and tested in the profile crate |
| `python crew/runners/rs_scoping.py [--prefix pt_]` | Rust campaigns by member, role and scope (S/M/L/C): which scope suits whom |
| `python -m crew unify --workspace [--check]` | mechanical cleanup with ruff, each stage kept only if the tests still pass; lists what needs a reader |
| `python -m crew vendor <workspace> <package> --author m.py=Name` | moves accepted modules into a real project with import rewrites, provenance headers and re-verification |

For a human:

| Tool | What it is for |
|---|---|
| `runners/Launch Review Desk.bat` | the queue of work waiting on Kris: approve needs no words, reject/question/defer do; **SEND** hands decisions to the agent (`for_agent.json`, `handoff.json`) |
| `C:\Users\user\TheCrew\Launch The Crew.bat` | The Crew's control room (Rust/egui): Board (campaigns, relays), Crew (who is working), Desk (the same queue), Night (the 3 AM reports), Reader. It writes the Desk only through `runners/desk_cli.py` (`list`, `decide ID DECISION < note`, `undecide`, `draft`, `send`; one JSON answer each), so both windows keep one writer and the same rules |
| `runners/Launch TTS bench.bat` | hear the TTS modules on real devices, including remembered headsets |
| `runners/ui_sweep.py` | press every control in a Windows app, visibly, and report what was observed |
| `runners/format_check.py` | check an exported VtoT document against the formatting test spec |

Writing new work: contracts in `contracts/` (paste `HOUSE_STYLE.md` or
`JS_HOUSE_STYLE.md`), hidden tests in `hidden_tests/`, and a reference in
`hidden_tests/reference/` that must pass them **before** a request is spent. A new
language: `HARNESS_BUILDING.md`.

## Known limits (2026-09-21)

- Prose judgment (is this verdict *right*?) is still the reviewer's job. The gates catch numbers, citations, links, reading, and structure, not meaning.
- `organize_plan` proposes only. The deterministic mover (with wikilink rewriting) comes next.
- One worker per server process. Separate campaigns run in parallel when their authors are different models (Synthetic allows concurrent requests per model; Kris's two packs allow two). The governor (`ratelimit.py`) reads the provider's own `x-synthetic-quotas` header; the binding limit is usually weekly **credits**, not requests.
- A passed research gate means **cited and grounded, not correct**. Hoss's AHK digest passed with a wrong version number because that number appeared elsewhere on the cited page. Grade content against the source.
- Web fetch covers only `fetch_allowlist`; pages are read in windows (`start`, `lines`) or searched (`pattern`). Fetched pages are untrusted input.
- AutoHotkey runs only in Windows Sandbox (Kris, 2026-09-21). One sandbox at a time; runs queue behind a lock.
- Vision is probed, not wired: no task type carries an image yet (`VISION.md`).
