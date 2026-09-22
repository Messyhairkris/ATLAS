---
title: Research compared - four members, one question (AHK v1 command line)
tags: [research, crew, evaluation, ahk]
last_updated: 2026-09-21
---

Kris, 2026-09-21: *"I would like to see if the more verbose teammates are good at
research as well as coding."* Runner: `crew/runners/research_compare.py`.

**The question:** how can an AutoHotkey v1 script run unattended - writing results to
a file and never showing a dialog? Three pages of the official v1 docs, given by URL.
Graded twice: by the gates (cited, grounded, structured) and by hand against the docs
on five facts - OnError is v1.1.29; its callback returns non-zero to block the dialog;
`/ErrorStdOut` covers syntax errors only; `/iLib` with `/ErrorStdOut` validates
without running (exit code 2); `A_Args` arrived in v1.1.27.

## Most of the failures were ours

Five rounds, and the harness or the question failed members in four of them:

| round | what went wrong | whose |
|---|---|---|
| 1 | two of the three URLs I gave were 404s | mine |
| 2 | `fetch_url` showed only the first screen of a page while recording the whole page as evidence | harness |
| 3 | the citations gate refused "(not stated in source)", the playbook's own wording | harness |
| 3 | relative citations resolved against the vault, not the folder being read; a second line locator was not stripped | harness |
| 3 | the grounding gate treated "lines 219-315" as a factual claim | harness |
| 4 | Nemotron copied playbook rule rd-007's one-line frontmatter example literally | playbook |

All six are fixed.

## What each member did, once the harness was fair

| member | gates | facts (of 5) | the telling detail |
|---|---|---|---|
| **Gordon** | passed (rounds 2, 4; round 3 lost to our gate) | **5/5** (round 3) | opened every page; quoted `[v1.1.29+]` verbatim; when a page was clipped he listed what he could not see instead of guessing |
| **Barry** (GLM-5.3) | passed the AHK-folder digest; command line still running at writing | right version every time he read the page | slow - 3 to 6 minutes a digest |
| **Nemotron** | never passed | 4/5 when he finished (round 4) | reads until the budget runs out; two of five runs never submitted |
| **Hoss** | **passed** (round 3) | **wrong**: said OnError is v1.1.33 | never opened the OnError page; cited the main page for every claim. "1.1.33" appears on that page for a different switch, so the grounding gate passed it |

**Every member who opened the OnError page stated its version correctly. The one who
did not, stated it wrong - and his was the only digest to pass every gate in that
round.** A passed research gate means cited and grounded, not correct.

## Answers

- **Are the wordy members good researchers?** Hoss is fast (31 seconds, 7 requests)
  and always produces a well-formed digest, but he answers from memory and decorates
  it with citations. Use him for a first map you will verify, never for a fact you
  will act on. Barry is careful but slow. Gordon, not especially wordy, is the one to
  trust.
- **What the harness needs next:** a check that each claim's citation is the page the
  claim actually came from - today the grounding gate only asks whether the words
  appear *somewhere* in something the member read.

## The second question: how Kris uses AHK v1

Same four members over Kris's AHK V1 Agentic Project (added read-only; its `.env`
files, `.git` and `node_modules` stay refused). Hoss, Gordon and Barry passed.
Gordon's digest is the useful one: of 16 libraries in `Lib/`, only Jxon and the
Belvedere comparison verbs are pure, and the recurring hand-written patterns with no
pure helper yet are regex captures (v1's `match1`/`match2` pseudo-variables), the
triple-press timing state, and case functions that return a value instead of
modifying in place. Those are the candidates for the first crew AHK module.
