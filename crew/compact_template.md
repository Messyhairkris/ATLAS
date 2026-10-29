# What the chat compact must keep in its summary input

Kris edits this file. The engine's own compaction (`POST /session/{id}/summarize`) writes its own
summary and takes no template, so this is the record we keep ourselves: written beside every
backup, so a person or a model can rebuild the summary if the engine's ever needs replacing. The
sections are the ones that matter across a long chat.

## Goals

What this chat is for, in one or two lines.

## Decisions, with their reasons

Every choice we made and why. A decision without its reason is worse than no decision.

## Files touched

Every file read or changed, with what happened to it.

## Open items and next steps

What is unfinished, what is waiting on someone, and what comes next.

## What Kris asked for, in his own words

The PM's own phrasing, quoted - not our paraphrase of it. When the two disagree, his words win.
