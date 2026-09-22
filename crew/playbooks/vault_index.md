# Playbook: vault_index

Build or refresh a Map-of-Content note (e.g. INDEX.md) for one vault folder.
Entries are rules learned from real runs; follow every one. New entries are
appended by reviewers, never rewritten wholesale.

## Entries
- [vi-001] (seed) Link every .md note in the folder with an Obsidian wikilink relative to the folder, e.g. [[PLAN]] or [[runs/RUN-20260918-signal-lost]]; never link the index file itself or non-markdown files such as telemetry.jsonl.
- [vi-002] (seed) One short line per note saying what it decides or records, written from the note's own words; do not invent outcomes, numbers, or verdicts.
- [vi-003] (seed) Any number, ratio, dollar amount, or verdict word (PASS, FAIL, MET, CONFIRMED, PARTIAL) on a line must appear in the note that line links to; if you have not read the note, leave numbers out.
- [vi-004] (seed) Group notes by theme under ## headings; put a two-line thesis and current verdict at the top, taken from the plan or the newest run note.
- [vi-005] (seed) Vault pages start with YAML frontmatter containing title, tags, aliases, last_updated (vault CLAUDE.md schema).
- [vi-006] (librarian-duty-1) A one-shot index from the inventory excerpts usually passes; read a full note only when its excerpt does not say what the note decides.
- [vi-007] (review Claude job-20260919-102403-9a88) Never copy the thesis or verdict from the existing index; derive them from the newest run note and review, read in full.
- [vi-008] (review Claude job-20260919-102403-9a88) The folder inventory is already in the task text; do not spend a request on list_dir of the same folder.
- [vi-010] (Hoss via Claude) read the run note before quoting its score
