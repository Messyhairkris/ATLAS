RECON QUESTION for the .octofriend dotfolder - accumulated docs and scaffolding.

The folder you were given, `.octofriend`, is a live-ish config/state
directory for an Octofriend install, but several subfolders (`config/`,
`data/`, `backups/`, `logs/`, `bridge/`) are OUTSIDE your read access on
purpose - they hold runtime state and possible credentials, not lessons.
Do not try to read them; if a tool call refuses one, that is expected, not
an error to report. Focus entirely on what you CAN read: `docs/`, `mcp/`,
`memory/`, `research/`, `skills/`, `src/`, `ts/`, `tests/`, `bin/`, and the
top-level docs (README.md, README_v2.md, READY_TO_USE.md,
ENHANCED_MCP_SUMMARY.md, IMPLEMENTATION_SUMMARY.md, TEST_PLAN.md, and the
test_*.py / check_v3.py / verify_installation.py / demo_conversation_flow.py
scripts).

This folder looks like it accumulated real documentation and scaffolding
work, not just vendor code - multiple README variants and summary docs
usually mean the project evolved through versions (v2, v3 show up in
filenames). Read the newest-looking docs first (check what they say about
superseding older ones) rather than starting from README.md and reading
every version in order.

Answer, as a cited digest:

1. WHAT THIS ADDS ON TOP OF PLAIN OCTOFRIEND. `mcp/` suggests custom MCP
   tooling; `skills/` and `memory/` suggest an agent-skill/memory system
   layered on top. Describe what each actually implements, and whether it
   looks like a precursor to - or overlaps with - this team's OWN current
   MCP-based Crew server and its own memory/playbook system
   (ATLAS-api-harness's `crew/playbook.py` and its `crew/contracts/` house
   style, if that helps you frame the comparison - you were not given that
   code to read, just use it as context for what to look for).
2. WHAT THE VERSION HISTORY TELLS YOU. If v2/v3 docs describe why a rewrite
   happened, say what changed and why - that is exactly the kind of "why we
   moved on" lesson this whole archaeology effort exists to capture.
3. TEST/VERIFICATION SCRIPTS AS EVIDENCE, NOT JUST DOCS. `TEST_PLAN.md`
   plus the various `test_*.py`/`verify_installation.py`/`check_v3.py`
   files may show what was actually verified to work, which is more
   trustworthy than a doc's own claims (recon-hoss's mistake on the CASSIA
   project was trusting a "PROJECT COMPLETE" doc over what the code
   actually showed - do not repeat that here).
4. RESEARCH AND SKILLS CONTENT. If `research/` or `skills/` hold anything
   that reads as genuine investigation (not boilerplate), summarize its
   conclusion, not just its existence.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite every claim as [src: path] for a file you actually opened. If a path
  under config/data/backups/logs/bridge is refused, do not describe its
  contents - note only that it exists and was inaccessible.
- End with a short CANDIDATES list: the 5-10 strongest salvage candidates,
  ranked, each ending in its [src: path].
