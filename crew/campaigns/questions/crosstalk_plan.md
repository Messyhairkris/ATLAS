PLANNING QUESTION - you are drafting a campaign backlog, not just a report.

You have been PRELOADED with independent recon digests of CrossTalk_v2.3.3,
an abandoned "90% there" implementation of CrossTalk. You also have read
access to CrossTalk_v3.0 (the live redesign that replaced it), the top-level
CrossTalk docs (ARCHITECTURE.md, ROADMAP.md, AGENTS.md, ATOMIC_TASKS.md,
HANDOFF.md, CODEBASE_ANALYSIS.md), and the Obsidian Knowledge_Base vault
(`wiki/` and related folders), where most of this team's agent-planning
notes actually live. Use the extra read access: a candidate that already
exists in v3.0, or is already planned in the vault or ROADMAP.md, is not a
backlog item, it is confirmation - say so instead of proposing it again.

Turn the digest(s) into ONE concrete extraction backlog: the list of
follow-up tasks a team would actually run next to move value from the
abandoned v2.3.3 into the live v3.0.

For EACH backlog item give:
- id: a short slug
- title: one line
- source: the file(s) it comes from (as you would cite them)
- target: "CrossTalk_v3.0", "vault/planning", or "general" if neither
- rationale: why it is worth the effort, in one or two sentences - and
  explicitly say whether v3.0 or the vault already covers this (if so, this
  item should be a verification/comparison task, not a fresh port)
- shape: one of "port as-is", "rewrite the logic", "document the lesson
  only", "already covered - verify only"
- effort: "small", "medium", or "large" - a guess, but say why

Order the list by value for effort, best first. If you were given more than
one recon digest and they disagree, or one found something the other
missed, say so explicitly in the prose before the list - do not silently
pick one. Do not invent an item the digest(s) do not support; if you think
something is missing, say that separately as a gap, not as a backlog entry.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite claims as [src: path] - the preloaded digest file(s) are legitimate
  citations; cite them by the path you were given. A claim about v3.0 or
  the vault must be cited the same way - you were given real read access to
  both, use it rather than assuming.
- After the prose, end with exactly one fenced ```json block holding:
  {"backlog": [{"id": "...", "title": "...", "source": ["..."], "target": "...",
  "rationale": "...", "shape": "...", "effort": "..."}, ...],
  "gaps": ["..."], "disagreements": ["..."]}
  so the list can be read by a program, not just a person.
