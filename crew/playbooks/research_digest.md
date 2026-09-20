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
- [rd-007] (review Claude TTS-round1) Frontmatter must include tags, e.g. ---/title: X/tags: [research, vtot]/---; a note without tags fails the check.
- [rd-008] (review Claude TTS-round1) When the task gives a URL, fetch that exact URL first; do not guess raw.githubusercontent.com or branch names.
- [rd-009] (review Claude TTS-round1) Never state sizes, dates, versions, counts or licenses that are not in text you fetched or read this task; write (not stated in source) instead.
- [rd-010] (review Claude TTS-round1) For long inventories use one short table row per item and no repeated explanation; a reply cut off before the closing fence fails.
- [rd-011] (review Claude job-20260919-132524-3c05) Never attribute a request or requirement to testers or users unless you can quote their words from a file you read.
- [rd-012] (review Claude job-20260919-132957-7852) For a code map, first search for class and def names matching the topic words (e.g. announce|feedback|notify|speak|settings) and name the central function callers use; a map without it is incomplete.
