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

## Task types

| Type | Member produces | Gates | Approve does |
|---|---|---|---|
| `vault_index` | INDEX.md for one vault folder | output path, frontmatter, links resolve, every note linked, numbers grounded in what it read | writes the index (old one backed up) |
| `research_digest` | cited markdown digest answering a question | output path, frontmatter, every item cited, citations were actually opened, numbers grounded in cited text, links resolve | writes the digest (default `runs/crew/outbox/`) |
| `organize_plan` | plan.json of moves/renames/tags | schema, sources exist, targets inside the folder and collision-free | saves the plan. Moves are **not** executed in v1 |
| `test_triage` | a triage report of a test run | no invented test names, the run's summary line quoted verbatim, citations, grounding, absence claims | writes the report |
| `ui_sweep` | a report on every control pressed | no invented control names, totals quoted, interference reported, citations, grounding, absence claims | writes the report |

The harness does the acting in the last two: it **runs the project's own test suite**, and it **drives the app** (each control highlighted in #FF7900 for half a second, then pressed, menus opened and their items pressed). The member only explains what happened, against evidence it cannot fake.

Any task can also carry **acceptance gates**: `must_mention`, `must_read` (the member must open the file itself), `ascii_only`. A reviewer attaches `must_read`/`ascii_only` on **revise**. This turns "read X first" from an instruction a small model may skip into a check it can't skip. On the first live job this was what made Hoss read the note it had skipped twice.

## Safety posture

- **Read-only tools.** `list_dir`, `read_file`, `search`, and `fetch_url` (off unless `fetch_allowlist` in `config.json` names domains). The member cannot write, run, move, or delete anything.
- **Path limits.** Paths are resolved and confined to the job's read roots. `deny_globs` (secrets, `.git`, `.obsidian`, crush.json, crew internals) always win.
- **Writes** happen only on approval (or at Supervised+), only inside `write_roots`, with a backup of anything overwritten.
- **Leash.**
  - Hard request budget (default 12).
  - Repeated identical tool calls aren't re-run; three repeats end the job.
  - Two invalid replies in a row end it; three empty replies end it.
  - The best submission is kept.
- **No self-promotion.** No MCP tool can change an Autonomy Stage. `python -m crew promote` is Kris-only. It refuses to skip stages and refuses to promote right after a failure.
- **Deny list available, currently empty.** `deny_models` in `config.json` is enforced by the provider layer; it was used to measure roster-only spend and is now off. Big models are not crew members by default: `defaults.assigned_to` is Hoss, and naming a large model in `assigned_to` usually means the task was mis-scoped.

## Register the server

**Claude Code:** `.mcp.json` at the repo root registers `crew` for this project. Approve it when Claude Code asks.

**Crush (Windows):** add this under `"mcp"` in `%LOCALAPPDATA%\crush\crush.json`. It runs through the same stdio wrapper the other Python servers use, because Crush's pipes break FastMCP's stdin otherwise:

```json
"crew": {
  "type": "stdio",
  "command": "C:/Users/user/AppData/Local/Programs/Python/Python314/python.exe",
  "args": ["C:/Users/user/.octofriend/mcp/mcp_stdio_wrapper.py",
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
- `autofix.py` — zero-token linter: typography and near-miss names or citations are repaired before gating, and every fix is logged (it never guesses meaning)
- `runners/` — `run_test_scripts.py` (script-style suites), `ui_sweep.py` (visible control sweep), `format_check.py` (formatting test document)
  The sweep waits for **readiness**, not a fixed delay: after each press it waits until the app answers messages again, the desktop's window list stops changing and the watched folders stop growing (`--settle` floor, `--settle-max` ceiling, `--quiet` the required calm). A control whose name says it opens something must actually open something or the press fails (`nothing_opened`); a wait past `--report-wait-after` is announced in the banner and logged as `still_waiting`; a breach of the ceiling is logged as `stalled`. The banner reports what was OBSERVED ("seen: Save -> wrote 1 file(s)"), never just what is intended.
- `fixtures/format_test_doc.txt` + `.json` — the VtoT formatting test and practice document, and its machine-checkable spec
- `playbooks/*.md` — retained knowledge per task type (append-only entries with ids)
- `runs/crew/` — state:
  - `jobs/<id>/` — job.json, transcript.jsonl, output/, backup/
  - `action_log.jsonl`, `roster.json`, `claims/`, `outbox/`
- Ledger — every model call lands in the harness telemetry file, tagged `duty=crew:<type>`, `run_id=<job>`, `role=junior`, `persona`, `requests=1`

## Known limits (v0.1)

- Prose judgment (is this verdict *right*?) is still the reviewer's job. The gates catch numbers, citations, links, reading, and structure, not meaning.
- `organize_plan` proposes only. The deterministic mover (with wikilink rewriting) comes next.
- One worker per server process, one job at a time: deliberate, given the Synthetic request quota. The **request-budget governor** (`crew/ratelimit.py`) models Kris's allowance as a bucket of 500 refilling 5% every 3 hours (~8.3 requests/hour) and holds jobs when it runs low, keeping a reserve for human and Crush interactive work.
- Web fetch is off until domains are allowlisted. Fetched pages are untrusted input, and output stays gated and reviewed either way.
