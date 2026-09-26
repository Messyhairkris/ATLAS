# The building

Kris, 2026-09-25: *think of the crew as a building full of personnel, each able to be
called to a specific role that we have found they are good at, and given enough
resources to get their work done efficiently.*

- `crew/personnel.json` - one file per member: window, public reputation (with
  sources), what we measured, the **posts** they hold, and their **quirk profile**.
- `crew/personnel.py` - turns that into a job's resources, resolves `@post`.
- `crew/inspector.py` - the recursive quality pass after every job.
- `python crew/runners/building.py` - the directory; `--budgets TASK`, `--proposals`,
  `--trial MEMBER TASK key=value`.

Switched on by `defaults.budget_from_personnel` in `config.json`. An explicit
`budget` in a spec (campaigns set one) still wins.

## Who is good at what

Public reputation first, then ours (190 finished jobs as of 2026-09-25). Where
they disagree, ours wins: it is measured on our tasks, under our gates.

| Member | Public | Measured here | Posts |
|---|---|---|---|
| Hoss - gpt-oss-120b, 128k | strong tool use; hallucinates, calls tools that do not exist | code 5/5, tests 6/6 at ~1.4 requests; research 15/30, fabricated URLs; 19 empty replies | module_author_py, tester, clerk |
| Qwen - Qwen3.8-27B, 262k | excellent, but overthinks; very verbose; slow | best researcher 22/32; 141k tokens/job; **11 jobs lost to our token ceiling, 23 jobs re-reading what trimming took away** | researcher, byte_exact, tester |
| Nemotron - 120B-A12B, 262k | fast, built for agents, verbose | Python modules 7/8; **JS 0/13, research 0/8** (loops) | module_author_py only |
| Gordon - DeepSeek-V4.1-Flash, 1M | very strong for a Flash; fast; verbose; trained at 64K, extended to 1M | vision 3/3; research 12/32 with loop stops; scouts correct but budget-bound | scout, researcher, vision, module_author_js |
| Barry - GLM-5.3-Flash, 1M | strong coding benchmarks; slow; long thinking | code 3/9; research 11/21 at 15 requests; says it sees images and is wrong 4/4 | none (held back) |
| Larry - GLM-4.7-Flash, 128k | wobbles on long reasoning, fine on short strict work | clerk jobs pass first try; research 3/12 | clerk, auditor |
| Haiku - Claude Haiku 4.5, 200k | made for sub-agent work; ~90% of Sonnet 4.5 on agentic coding | **never run** (needs `anthropic` + `ANTHROPIC_API_KEY`) | none yet |
| Kimi - Kimi-K3, 1M | best open model for long tool-using work; 51% hallucination rate; "excessive proactiveness" | **0/5 on our plain-text tool protocol** (protocol misfit every time) | special_teams |

Sources are in each member's `public.sources` in `personnel.json`.

## Resources: budgets fitted to the member and the job

- **Requests**: p75 of what this member's *passing* jobs of this type needed, + 2,
  once there are 3 or more; the task type's baseline before that. Hoss gets 3 for a
  Python module (he needs 1.4), Qwen 19 for research, a log clerk 5.
- **Working context**: `context_ceiling` x the member's window (default 1/2, max 3/4,
  capped at 200k). Old tool results are trimmed only once the prompt passes it;
  until 2026-09-25 every member kept 3 results of 6,000 characters whatever its window.
- **Tokens**: twice the member's 90th-percentile passing job (x `token_factor` for
  verbose thinkers - Qwen 2.0); a runaway stop, not a diet.

**On "half to three-quarters full"**: the evidence is that every model gets worse
as input grows, at every length, well before the window is full
([Chroma, *Context Rot*](https://www.trychroma.com/research/context-rot), 18 models).
So the fraction is a **ceiling on relevant material**, never a target to pad to. The
Inspector raises it (to 3/4 at most) only where a member keeps re-reading what was trimmed.

## Quirk harnesses

Each member's `quirks` has **addenda** (house notes appended to its system prompt,
aimed at its known weaknesses) and a **leash** (overrides of the loop's stop rules).
They sit on top of the tools that already neutralise quirks for everyone:

| Weakness | Tool that removes it |
|---|---|
| hallucinated citations, URLs, numbers | citation, grounding, verbatim, absence gates |
| calls tools that do not exist (Hoss) | native-call mapping in `agent.py`; house note |
| re-indents templates (Nemotron) | `quirklint.py` restores them |
| overthinking past the reply limit (Qwen, Barry) | per-member reply ceiling; token_factor; "decide early" note |
| loops (Gordon, Nemotron) | repeat detection; tighter leash for Nemotron |
| reads whole big files (Larry) | "search first" note; `lsp` symbols (trial) |
| wants native tool calls (Kimi) | **not built yet**: special teams need a native tool-calling harness |

## The Inspector (recursive quality pass)

After every job, without asking a model:

1. **Signatures** from the transcript: budget ran out, passed on the last request,
   token ceiling, reply ceiling, empty/invalid replies, repeated calls, re-reading,
   the same gate failing every submission, gates that taught (fixed after feedback).
2. **Refinement**: resource signatures start a bounded **trial** (more requests,
   more tokens, a larger context share) automatically - one at a time per member and
   task type. Wording and rule signatures become **proposals** for the PA: house
   notes, posts, reply ceilings, and `gate_suspect` when a gate failed every
   submission.
3. **Measurement**: after 3 jobs under a trial, it is **kept** if the pass rate did
   not drop and got better or cheaper, else **reverted**. Kept trials stay applied.

It may never edit gates, hidden tests, contracts, deny globs or autonomy stages -
an improver that can edit its own judge is the reward-hacking failure
[Continual Harness](https://arxiv.org/html/2605.09998v1) and AIDE warn about.

Dry run over the history (2026-09-25): Qwen re-read files in 23 jobs; `gate_stuck`
clusters on `research_digest` citations (11) and grounding (7) - the first place to
look for gates that are stricter than the contract; Kimi was a protocol misfit 5/5.

## Special teams (Kimi): real tools through native tool calls

Kimi abandoned the crew's plain-text tool protocol in 5 of 5 jobs; it wants native
tool calls. Special teams are its own harness:
`C:\Users\user\ATLAS-api-harness\crew\special_teams.py`, run with a mission file:

```
C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe C:\Users\user\ATLAS-api-harness\crew\special_teams.py C:\Users\user\ATLAS-api-harness\crew\campaigns\timed\mission_test_pass.json
```

- **The harness is the MCP client** (`crew\mcp_client.py`), never the member. Playwright MCP
  (`C:\Users\user\playwright-mcp-setup`) runs headless and isolated; the member is
  shown only the mission's `allowed_tools`, and never `browser_run_code_unsafe`,
  `browser_evaluate`, file upload, tabs, dialogs or network tools.
- **Every call is checked before it runs** by two crew-built modules (special-teams campaign,
  2026-09-25, 4/4 first try): `st_schema.py` (Hoss) parses and schema-checks the native call;
  `st_mission.py` (Nemotron) enforces allowed tools, the URL allowlist, step and action
  budgets and repeats. Refusals go back to the member as the tool result, with the reason.
- **Visible progress**: every click or typing is outlined orange #FF7900 for half a second
  and screenshotted first (`runs\crew\special_teams\<mission>\screenshots\`).
- **Credit cap**: the provider's own balance is read between steps; over `credit_cap_usd`,
  the mission stops.
- **Grading** (Kimi's 51% hallucination rate): every `quoted` span in the final answer must
  appear in something a tool returned; `expect_observed` strings must have been seen;
  `must_mention` terms must be in the answer.
- `file:` URLs are refused by Playwright MCP, so a mission's `serve_dir` is served on
  127.0.0.1 only for the mission's length. Playwright MCP 0.0.78 on Windows turns some
  punctuation into U+FFFD in its text output; the member is told it is not a page defect.

Output per mission: `C:\Users\user\ATLAS-api-harness\runs\crew\special_teams\<mission>\`
(`REPORT.md`, `result.json`, `transcript.jsonl`, `status.json`, `screenshots\`).

## LSP: still looking for its use case

Kris 2026-09-25: LSPs are useful, keep testing. Tests run as Inspector trials
(`--trial Gordon scout lsp=true`), measured the same way as any other change.
Candidates, most promising first: "who calls X" questions (references), outlining
large files before reading (symbols), dependency modules in multi-module campaigns
(definition). Measured so far: one navigation scout with and without - no difference.

## Next

- Special-teams harness for Kimi (native tool calling), Playwright first.
- Enable Haiku and measure it (sub-agent work is its public strength).
- Campaigns: take budgets from personnel instead of one `requests_per_attempt`.
- Let a clerk draft the text of Inspector proposals (the lesson wording), PA approves.
