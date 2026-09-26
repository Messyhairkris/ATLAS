RECON QUESTION for yetifriend, a small Octofriend patch set.

The folder you were given is small and focused, not a full app: a Rust
backend (`backend/main.rs`), auto-compaction logic (`compaction/`), a cron
persistence module (`cron/persistence.ts`), and an applied-patches log
(`patches/`) that includes an emergency-fix doc. Read the actual files -
this is small enough that you should be able to open everything relevant
within budget.

Answer, as a cited digest:

1. AUTO-COMPACTION, IN DETAIL. This is likely the most valuable part.
   `compaction/autocompact-enhanced.ts`, `compaction/index.ts`, and
   `compaction/MIGRATION.md` describe how this project manages an LLM
   context window filling up. This team's own Crew harness has hit the
   identical problem from the other direction - members running out of
   TOKEN BUDGET before finishing a task (`budget_tokens` failures). Describe
   precisely: what triggers a compaction, what gets kept vs. summarized vs.
   dropped, and whether the mechanism is reusable as an idea (even if the
   code is not portable as-is).
2. THE PATCH PROCESS ITSELF. `patches/APPLIED_PATCHES.md` and
   `patches/EMERGENCY_FIX.md` are a record of how a live system was patched
   under pressure. Is there a lesson in HOW patches were tracked/applied
   (not just what they fixed) worth adopting for how this team manages its
   own hotfixes?
3. THE RUST BACKEND. What `backend/main.rs` does, and whether the choice of
   Rust for this piece (vs. the rest of the stack, which look TypeScript)
   tells you anything about why - performance, safety, a specific library
   need. Say if you cannot tell from the file alone.
4. CRON/PERSISTENCE. What `cron/persistence.ts` persists and why, and
   whether it overlaps with anything this team's Crew harness already does
   (e.g. its own append-only event log / status.json pattern) or should.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite every claim as [src: path] for a file you actually opened.
- End with a short CANDIDATES list: the 3-8 strongest salvage candidates,
  ranked, each ending in its [src: path].
