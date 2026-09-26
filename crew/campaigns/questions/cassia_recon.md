RECON QUESTION for a dormant project.

CASSIA_Workspace_v3 (the folder you were given as a read root) is an earlier,
now-dormant AHK v1 agentic automation project: a chat server, an AutoHotkey
"Control Center" GUI, a registry of reusable automations, a task pool, and
provider/credential handling (OpenClaw). Kris's live project, CrossTalk, grew
out of the same ideas. The project is likely over, but you are not being asked
whether it should be revived - you are being asked what is worth salvaging
from it before it is left alone for good.

The project already wrote a lot of its own history down. Before anything
else, open its own post-mortems and maps - look for files named along the
lines of ISSUES_FIXED, WORK_SESSION_SUMMARY, DEPENDENCY_MAP,
FILE_ORGANIZATION_PLAN, PROJECT_COMPLETE, CASSIA_SUMMARY, and the top-level
quick-start / walkthrough docs - before reading source code cold. They will
save you requests.

Answer, as a cited digest:

1. TOOLS WORTH SALVAGING. Name each file/module that solves a real, working
   problem cleanly enough to be adapted elsewhere. For each: what it does,
   and what reusing it would actually take - drop-in as-is, port the logic to
   a new language/runtime, or just steal the idea and rewrite it.
2. LESSONS ALREADY WRITTEN DOWN. The project's own post-mortem docs record
   concrete mistakes and decisions. Pull out the ones worth NOT repeating -
   in CrossTalk, or in this Crew harness itself.
3. OVERLAP WITH CROSSTALK. CASSIA has its own registry of reusable
   automations, a task pool, and provider/model routing. Where you can see a
   direct parallel to something CrossTalk or the Crew is also trying to do,
   say so, so a reader can compare the two approaches - do not guess at
   CrossTalk's internals you have not read.
4. DEAD ENDS. Anything the project itself marks broken, abandoned, or
   superseded - and is therefore NOT worth carrying forward.

FORMAT
- Frontmatter with title and tags, as usual.
- Cite every claim as [src: path] for a file you actually opened (list_dir or
  search alone is not enough to cite a claim about a file's contents). Never
  say a file is missing, broken, or absent without having listed the
  directory or opened it first.
- End with a short CANDIDATES list: the 5-10 strongest extraction
  candidates, one line each, ranked, each ending in its [src: path].
