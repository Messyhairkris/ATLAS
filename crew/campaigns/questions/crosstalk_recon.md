RECON QUESTION for CrossTalk's own dormant version.

The folder you were given as a read root, CrossTalk_v2.3.3, is a large,
feature-complete-LOOKING implementation of CrossTalk - Kris calls it "a
failed experimental version, about 90% there." It has real modules: an
agent, an editor, style handling, networking, memory, identity, MCP client,
annotations, scheduling. It was set aside, not because it does nothing, but
because something about the direction was wrong. Your job is to find out
what is worth carrying forward into CrossTalk_v3.0, the redesign that
replaced it, and what specifically made this version worth abandoning - both
are equally valuable answers.

Read the project's own record first if one exists - a README, CHANGELOG,
or any doc in `docs/` explaining decisions - before reading source code
cold; it will save you requests and tell you what the author already knew
was wrong.

Answer, as a cited digest:

1. MODULES WORTH SALVAGING. Name each file/module that solves a real
   problem cleanly enough to be adapted into v3.0. For each: what it does,
   and what reusing it would take - drop-in as-is, port the logic, or just
   steal the idea and rewrite it for v3.0's architecture (which you have not
   read - do not guess at it, only describe what v2.3.3 offers).
2. WHY THIS VERSION WAS SET ASIDE. Look for the seam - the module, the
   design choice, or the comment that explains the wrong direction. A 90%-
   complete abandoned project almost always has a specific reason, not a
   vague one; find it if it is written down, and say clearly if it is not.
3. PATTERNS, NOT JUST CODE. Architecture choices (how agent/editor/network/
   memory relate to each other) that might be sound even if the
   implementation itself is not worth keeping.
4. DEAD ENDS. Anything the code or its docs mark broken, experimental, or
   abandoned mid-way - not worth carrying forward even as an idea.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite every claim as [src: path] for a file you actually opened. Never say
  a file is missing, broken, or absent without having listed the directory
  or opened it first.
- End with a short CANDIDATES list: the 5-10 strongest salvage candidates
  (code or lesson), ranked, each ending in its [src: path].
