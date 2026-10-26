# Playbook: research_digest

Collect what the workspace already knows about a question and hand it to
other agents as a cited digest. Entries are rules learned from real runs;
follow every one.

## Entries
- [rd-001] (seed) Every bullet, numbered item, or table row ends with at least one citation: [[Note Name]] for vault notes or [src: relative/path.md] for files and [src: https://...] for fetched pages.
- [rd-002] (seed) Only cite what you opened with read_file, search, list_dir, or fetch_url during THIS task; a citation of something you did not open fails the check.
- [rd-003] (seed) Numbers, ratios, dollar amounts, and verdict words must be copied from the cited source text; if unsure, quote the source's wording instead of a number.
- [rd-004] (seed) Start with search to find candidate notes, then read_file only the most relevant ones; stop reading when the question is answered. Requests are the scarce resource.
- [rd-005] (seed) Structure: frontmatter, a 2-4 line answer at the top, then ## Findings (cited bullets), ## Open questions (what the sources do not settle), ## Sources (one cited line per source used).
- [rd-006] (seed) Write for another agent: plain statements, no filler, no speculation presented as fact; mark inference explicitly with "(inferred)".
- [rd-007] (review Claude TTS-round1; example corrected 2026-09-21) Frontmatter must include title and tags, on SEPARATE lines at the very top: a line `---`, then `title: <your title>`, then `tags: [research, <topic>]`, then a line `---`. The old example here wrote it on one line with slashes, and Nemotron copied that literally - slashes and all - and failed.
- [rd-008] (review Claude TTS-round1) When the task gives a URL, fetch that exact URL first; do not guess raw.githubusercontent.com or branch names.
- [rd-009] (review Claude TTS-round1) Never state sizes, dates, versions, counts or licenses that are not in text you fetched or read this task; write (not stated in source) instead.
- [rd-010] (review Claude TTS-round1) For long inventories use one short table row per item and no repeated explanation; a reply cut off before the closing fence fails.
- [rd-011] (review Claude job-20260919-132524-3c05) Never attribute a request or requirement to testers or users unless you can quote their words from a file you read.
- [rd-012] (review Claude job-20260919-132957-7852) For a code map, first search for class and def names matching the topic words (e.g. announce|feedback|notify|speak|settings) and name the central function callers use; a map without it is incomplete.
- [rd-013] (review Claude job-20260921-044834-7bf8) When a preloaded file is unavailable, say so in the first lines and spend the remaining requests on the question it was meant to answer, not on searching code for substitutes.
- [rd-014] (review Claude job-20260921-050107-9537) Never compute totals, sums or averages in a report: quote each number as it appears in its source, or write (not stated in source). Arithmetic is done by the harness.
- [rd-015] (review Crush job-20260924-160933-4dda) Keep research_digests to ONE preloaded file, one read pass, and a capped word count; multi-file digests blow the token budget.
- [rd-016] (Qwen via Crush) Absence-claim checkers scan every line, including the top answer: keep "missing/absent/drops" wording only in cited bullets or with (inferred).
- [rd-017] (Qwen via Crush) Summarize bug locations in the answer line without restating the absence claim itself.
- [rd-018] (review Crush job-20260924-163428-6347) When exact numeric constants cannot be fetched, mark them (not stated in source) - the orchestrator fills them from richedit.h knowledge.
- [rd-019] (review Crush job-20260924-163429-4ee9) Reject-with-harvest: when a failed output is already applied, a quick reject with a note beats another paid retry.
- [rd-020] (review Crush job-20260924-163428-80fd) Hoss fabricates URLs under citation pressure (fake stackoverflow question IDs). Give him 'no URL you did not fetch' up front, not as an afterthought.
- [rd-021] (review Crush job-20260924-170519-7313) When asking for a verdict word with must_mention, accept BOTH possible verdicts or the gate fails the good answer.
- [rd-022] (review Crush job-20260924-171102-b5de) Larry as pure reporter (dir listing + orchestrator-supplied ground truth) is his sweet spot - first-try pass at 2 requests.
- [rd-023] (review PA 2026-10-26, job t4 GodCode) A digest whose source is a URL must carry that URL in the job's `must_read`, so it cannot pass unless the page was actually opened this run. An honest "the repository could not be fetched" is self-consistent and passes every other gate, which is how a correct digest about nothing reached the outbox. A source that will not load is a FAILED job - that is what puts it on the Desk.
- [rd-024] (review PA 2026-10-26, job t10 egui-grid) Write every URL in full, including its `https://` scheme. A scheme-less `raw.githubusercontent.com/...` is read as having no host and is refused as "not in the crew fetch allowlist"; the member then honestly reports "(not stated in source)" and the contract's own typo looks like a member failure.
- [rd-025] (harness 2026-10-26) `github.com/<owner>/<repo>/commits` is HTML chrome and the first thing GitHub rate-limits (HTTP 429, 2026-10-25 study). The harness now rewrites it to the commits API, so a commit date can still be read and quoted verbatim.
- [rd-026] (review PA 2026-10-26) Stay inside the ceiling: prefer the load-bearing features over an exhaustive list, name the sources you will actually open before you start (a fetch-heavy digest costs one request per source), and write the file in one pass.
- [rd-027] (review Claude job-20261026-093546-088d) When a digest reads a local tool's source, quote its constants (thresholds, caps, cooldowns) verbatim with the file as the citation - the PA builds from those numbers.
