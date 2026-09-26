RECON QUESTION for an ACTIVE project - house style, not archaeology.

Unlike a dormant-folder dig, this project is LIVE and in current use - Kris
is not archiving it, cutting anything, or deciding what to keep. The goal is
narrower and different: extract the PATTERNS, CONVENTIONS, and DESIGN
PHILOSOPHY this project already demonstrates, so they can be written down
once as house style instead of re-derived project by project. Read the
project's own docs/notes first if any exist (a README, a design doc, a
CHANGELOG) before reading source code cold - they usually state decisions
explicitly that would otherwise have to be inferred.

Answer, as a cited digest:

1. CONVENTIONS THAT REPEAT. Naming, file organization, error handling,
   comment style, how config/state is separated from logic - anything this
   project does consistently enough that it reads as a deliberate choice,
   not an accident. Quote a concrete example, not just the abstraction.
2. DESIGN PHILOSOPHY, IF STATED OR INFERABLE. Does the project explain WHY
   it does something a certain way anywhere (a comment, a doc, a commit
   message you can see)? A stated reason is worth far more than a guessed
   one - if you cannot find the reason, say the pattern exists without
   claiming to know why.
3. LESSONS FROM ITS OWN HISTORY. Look for evidence the project changed
   direction - an old approach replaced by a new one, a note explaining
   what didn't work, a version history. What was learned getting here is as
   valuable as what exists now.
4. WHAT WOULD SURPRISE SOMEONE JOINING COLD. Anything non-obvious a new
   contributor (human or agent) would need to be told explicitly to avoid a
   mistake - a gotcha, a non-standard tool choice, a constraint from the
   environment (e.g. Windows-only, a specific hardware dependency).

Do NOT propose changes, improvements, or a backlog - that is not this
question's job. Do NOT speculate about what "should" be done differently.
Report what IS, grounded in what you actually read.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite every claim as [src: path] for a file you actually opened. Never say
  a file is missing, broken, or absent without having listed the directory
  or opened it first.
- End with a short PATTERNS list: the 5-10 most reusable conventions/
  lessons found, ranked by how broadly they'd apply beyond this one
  project, each ending in its [src: path].
