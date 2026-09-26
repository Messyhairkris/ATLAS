RECON QUESTION for Vocto's own tooling (not vendored code).

Context, so you don't waste requests re-discovering it: the folder you were
given, `vocto-tools/` (and its sibling `vocto-scripts/`), sits inside a git
clone of the open-source project https://github.com/synthetic-lab/octofriend.
The cloned octofriend source itself needs NO cataloguing - it is recoverable
from GitHub any time. `vocto-tools/` and `vocto-scripts/` are Kris's OWN
additions on top, built to keep a patched "Vocto" instance running and
self-repairing on Windows. That is what you are here to survey.

From the folder structure, `vocto-tools/` looks like a small self-built
framework: browser automation, config management, a memory/trigger-detector
layer, a repair layer (diagnostic relay, health monitor, system repair), and
a signal layer (process monitor, redundant watcher). Read the actual files -
do not infer behavior from file names alone.

Answer, as a cited digest:

1. WHAT EACH PIECE ACTUALLY DOES. For each module you open: its real
   purpose, not a guess from its name. Group related files (e.g. everything
   under `repair/`) rather than listing every file in isolation.
2. SELF-MONITORING AND SELF-REPAIR PATTERNS, ESPECIALLY. This team runs its
   own agent harness (the "Crew," in a sibling project called
   ATLAS-api-harness) which is starting to build its own resilience/retry
   logic for flaky model connections. If `health_monitor.py`,
   `system_repair.py`, `process_monitor.py`, or `redundant_watcher.py`
   contain a pattern for detecting a stuck/broken process and recovering
   it, describe the mechanism precisely (what it watches, what triggers
   recovery, what recovery does) - this is the single most valuable thing
   you could find here.
3. WHAT'S REUSABLE VS. WHAT'S TOO SPECIFIC. Some of this may be tightly
   bound to Octofriend/browser automation specifics. Say plainly which
   pieces are portable ideas vs. which are throwaway glue for this one
   tool.
4. `vocto-scripts/` - what the update/versioning scripts (`update_vocto.py`,
   `vocto.cmd`, the versioned zips) tell you about how Kris has been
   iterating this tool, if anything is worth learning from the process
   itself.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite every claim as [src: path] for a file you actually opened. Never say
  a file is missing, broken, or absent without having listed the directory
  or opened it first.
- End with a short CANDIDATES list: the 5-10 strongest salvage candidates,
  ranked, each ending in its [src: path], each noting whether it applies to
  the Crew harness, CrossTalk, or is too Octofriend-specific to reuse.
