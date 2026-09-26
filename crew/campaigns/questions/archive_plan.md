PLANNING QUESTION - you are drafting BOTH an extraction backlog AND a cut list.

You have been PRELOADED with recon digest(s) of this folder. This is one of
several dormant Octofriend-based experiments Kris ran before Crush became
the team's main workflow driver; Claude (the senior reviewing this) left
these unused since. The goal now is a proper archive: keep what has future
value, cut the rest, and leave behind a clean, well-organized, documented
record - not the whole messy folder as it sits today.

Do TWO things, from the digest(s) alone (do not invent claims neither
digest supports):

## Part 1: Extraction backlog
The list of follow-up tasks worth doing with what was found - same shape as
prior archaeology rounds. For each: id, title, source (files/digests it
comes from), target ("Crew harness", "CrossTalk", or "general"), rationale,
shape ("port as-is" / "rewrite the logic" / "document the lesson only"),
effort ("small"/"medium"/"large" with why).

## Part 2: Cut list
For every top-level file and folder the digest(s) actually looked at or
listed, give a verdict: "keep" (worth carrying into the archive - source
code, docs, or config with real informational value) or "cut" (vendor code
recoverable from its own upstream, generated/build output, caches,
duplicate/versioned zips of things already captured elsewhere, or anything
with no standalone value once its lesson is written down). A "cut" verdict
needs a one-line reason. When in doubt between keep/cut, prefer "keep" -
this list only decides what MIGHT be archived; nothing is deleted from it
being marked "cut" here.

If you were given more than one recon digest and they disagree on a keep/cut
call, say so explicitly - do not silently pick one.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite claims as [src: path] - the preloaded digest file(s) are legitimate
  citations; cite them by the path you were given.
- After the prose, end with exactly one fenced ```json block holding:
  {"backlog": [{"id","title","source","target","rationale","shape","effort"}...],
   "cut_list": [{"path","verdict","why"}...],
   "gaps": ["..."], "disagreements": ["..."]}
  so both lists can be read by a program, not just a person.
