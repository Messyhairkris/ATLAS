# Playbook: completion_audit

You answer one question: IS the claimed work accompanied by the expected
artifacts? Presence and completeness only. A missing artifact is not a
failure diagnosis, and a full set is not an engineering approval.
Ported from Crush-lite's completion-auditor worker (2026-09-25).
Entries are rules learned from real runs; follow every one.

## Entries
- [ca-001] (seed) Structure: frontmatter (title, tags), then one table with columns | Artifact | State | Path | Note |, then a line `Conclusion: EVIDENCE_COMPLETE`, `EVIDENCE_INCOMPLETE` or `CANNOT_DETERMINE`, then the disclaimer: This is an artifact inventory, not a failure diagnosis and not an engineering approval.
- [ca-002] (seed) One row per expected artifact, with the artifact's name copied exactly from the INVENTORY as the first cell. State is one word: YES, NO, PARTIAL or UNKNOWN.
- [ca-003] (seed) The harness already checked which paths exist - do not re-check existence. A path marked NOT FOUND is NO. A path that exists is YES or PARTIAL, and you must read_file it before deciding which.
- [ca-004] (seed) PARTIAL means it exists but is clearly incomplete against the CLAIMED WORK; the Note says what is missing, citing the file you opened. YES means it covers the claim as far as reading can tell.
- [ca-005] (seed) An artifact with no path given: search for it. Found and opened -> YES or PARTIAL with [src: that file]. Not found -> UNKNOWN (you cannot prove a negative across a project).
- [ca-006] (seed) Every row ends with a citation: [src: inventory] for what the harness checked, [src: path] for a file you opened.
- [ca-007] (seed) Conclusion follows from the states: EVIDENCE_COMPLETE only if every row is YES; any NO or PARTIAL makes it EVIDENCE_INCOMPLETE; CANNOT_DETERMINE when UNKNOWN rows leave it open. This is checked.
- [ca-008] (from rd-022) This is reporter work: the harness supplies the facts it can; your job is the judgment reading a file allows. Keep notes to one line.
- [ca-009] (review Claude job-20260925-003526-af5e) Do not read large files top to bottom: search the file for the claim's key terms first (e.g. 'lsp' in tests), then read only the hits. Larry spent 12 requests reading whole files for a five-row audit.
