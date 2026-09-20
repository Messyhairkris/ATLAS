# Playbook: test_triage

The harness has already run the project's test suite and given you the output.
Turn it into a report a developer can act on without re-running anything.
Entries are rules learned from real runs; follow every one.

## Entries
- [tt-001] (seed) The run output is your evidence. Cite it as [src: run_log] on every line that states what happened, and cite a source file only if you opened it with read_file.
- [tt-002] (seed) Never name a test, file, or error that does not appear in the run output. If something is unclear, say so under ## Open questions instead of guessing.
- [tt-003] (seed) Quote the run's summary line verbatim (for example "3 failed, 29 passed") in your answer paragraph; do not round, soften, or recalculate it.
- [tt-004] (seed) Structure: frontmatter, a 2-4 line answer (what passed, what failed, the headline risk), ## Failures (one item per distinct failure: test name, the assertion or exception verbatim, the file and line it points at, and a one-line likely cause), ## Groups (failures that share one root cause), ## Coverage gaps, ## Open questions.
- [tt-005] (seed) Group failures that share a stack frame or message into one root cause and say how many tests it accounts for; a list of 30 identical errors is one finding, not thirty.
- [tt-006] (seed) Read the source only for failures whose cause is not obvious from the trace; each read costs a request, and the budget is small.
- [tt-007] (seed) A passing suite is a valid result: report what ran, how long it took, and where coverage is thin. Do not invent problems to fill the report.
- [tt-008] (review Claude job-20260919-172117-9d4b) A claim that something is NOT covered must name the test files you inspected (open at least the ones whose names are closest to the feature); run_log alone cannot evidence an absence.
- [tt-009] (review Claude job-20260919-172117-9d4b) Coverage gaps must be specific to this codebase (name the module or function at risk), not generic risks that would apply to any project.
- [tt-010] (review Crush job-20260919-204543-19e6) If collection errors block the suite, say so as THE headline: zero tests ran means the risk statement (regressions invisible) matters more than pass/fail counts.
- [tt-011] (review Crush job-20260919-204543-19e6) When the run shows deselected/skipped counts without reasons in the log, list them under open questions instead of speculating.
- [tt-012] (review Crush job-20260919-204543-19e6) Quote the summary line exactly and reuse log tokens verbatim (paths, interpreter names) for grounding gates.
- [tt-013] (Qwen via Crush) Frontmatter must include title and tags, not just job metadata.
- [tt-014] (Qwen via Crush) Every bullet line needs a [src: run_log] citation, including "likely cause" inferences.
- [tt-015] (Qwen via Crush) Use tokens exactly as they appear in the run log (e.g. "Python314", not "3.14") to pass grounding checks.
