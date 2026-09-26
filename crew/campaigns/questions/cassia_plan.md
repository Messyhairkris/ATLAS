PLANNING QUESTION - you are drafting a campaign backlog, not just a report.

You have been PRELOADED with two independent recon digests of the same
dormant project (CASSIA_Workspace_v3): your own from an earlier pass, and a
teammate's, written without seeing yours. Both are cited digests of what is
worth salvaging from that project - tools, lessons, and overlap with the live
CrossTalk project.

Your job now: turn the two digests into ONE concrete extraction backlog -
the list of follow-up tasks a team would actually run next. This is the
delegated-planning experiment Kris is running: can a crew member propose the
work, not just do it.

For EACH backlog item give:
- id: a short slug
- title: one line
- source: the file(s) it comes from (as you would cite them)
- target: which project it belongs in - CrossTalk, the Crew harness itself,
  or "general" if neither
- rationale: why it is worth the effort, in one or two sentences
- shape: one of "port as-is", "rewrite the logic", "document the lesson only"
- effort: "small", "medium", or "large" - a guess, but say why

Order the list by value for effort, best first. Where the two digests
disagree, or one found something the other missed, say so explicitly in the
prose before the list - do not silently pick one. Do not invent an item
neither digest supports; if you think something is missing, say that
separately as a gap, not as a backlog entry.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite claims as [src: path] - the two digest files you were preloaded with
  are legitimate citations; cite them by the path you were given.
- After the prose, end with exactly one fenced ```json block holding:
  {"backlog": [{"id": "...", "title": "...", "source": ["..."], "target": "...",
  "rationale": "...", "shape": "...", "effort": "..."}, ...],
  "gaps": ["..."], "disagreements": ["..."]}
  so the list can be read by a program, not just a person.
