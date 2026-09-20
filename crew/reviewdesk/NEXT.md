# Review Desk — what it still needs

Kris's test pass, 2026-09-20: 13 ok, 3 need work. He asked to move on to other
tasks, so this is the written record rather than a queue of half-done work.

> "I have used the Review Desk. I can see a few things I will want to improve
> later, but lets focus on other tasks for now."

## What the desk is for

His words, and the thing to test every future change against:

> "Not meant to replace back and forth chat, but a method I can use to track the
> myriad of different projects we have going at once. I lose the item we need to
> review in the replies due to my ADHD... this tool is to show what needs review,
> what the determination is, why we determined that, and sends the reviewed work
> back for further refinement or use. Its a tool to track and assist the human
> users, not to replace the work of our AI teammates."

It belongs to **file hygiene**, one of CrossTalk's first principles: *the folders
may be messy behind the scenes, but the user should never have to search for the
file that was just made.*

## Done, 2026-09-20 (commit dd28cb7)

- **SEND TO THE AGENT**, and a modal that confirms the handover and says what
  happens next — his "if you could only fix one thing".
- The modal also appears by itself when the last item is decided.
- `handoff.json` / `handoff.log` — a timestamp and a history.
- Approved work leaves the list once sent; a file touched afterwards returns
  marked `[new]` in orange.
- `Ctrl` + wheel, `A-` / `A+` resize the file, the index and the note box.

## Still to do, in his order of interest

### 1. Projects and teams in the sidebar
> "It should contain a project section, with areas for all Agents that are able to
> send items for review... collapsible sections in the side bar that state which
> team is requesting approval, as well as the project name based on the folders
> connected to the project."

The queue is flat today. Needs: a `project` and a `requested_by` field (the INI's
`FIELDS` is Qwen's module, so this is a contract revision and a crew task, not a
hand edit), a tree instead of a listbox, and the project name derived from the
path's own folder. **This is the next real piece of work on the desk.**

### 2. "Right now" versus "later"
> "I do want one tool that Agents send all items that need review, but a way to
> keep track of the ones that need approvals right now."

A priority or a due marker, set by the agent asking. Sorting by it is cheap once
the field exists — same contract revision as (1).

### 3. Notes visible beside the document
> "it would be nice to take advantage of the extra space on the right of the
> screen next to the document and mark where the notes are located, perhaps
> displaying them next to the item in question while highlighting it."

A margin beside the viewer: one marker per anchored note, at the right line,
clickable to jump. Today an anchor is only visible when its item is selected, and
only as a label. Needs several notes per item first — right now a note is one
field on the record, which is (4).

### 4. More than one note per item
Implied by (3): a margin full of markers means a list of notes, each with its own
anchor. `note` and `anchor` are single fields in the INI today.

### 5. Living on the taskbar
> "The program ideally can live on the taskbar when not in use."

It minimises to the taskbar already, being a normal window. A genuine tray icon
with a badge count needs `pystray` or `win32gui` — a dependency decision, and a
question of whether the desk should start with Windows.

### 6. Read-only, side by side, and history
Known gaps, not yet asked for: no diff view, no search, no two files at once, and
the decision history is only `handoff.log`.

## What not to build

He was clear the desk is not an IDE:

> "Look at other ides like Antigravity or Codex for inspiration. I do not want a
> VS environment, but a way to review work without the search everytime is the
> desired outcome."

So: no editing files in the desk, no terminal, no project tree for its own sake.
The middle panel shows the file because a note has to point at something.
