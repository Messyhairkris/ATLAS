"""Reference for compact.py: a long crew job keeps what it found (PA-written)."""

import json

NOTE_MAX_CHARS = 300
NOTES_MAX_CHARS = 3000
WARN_AT = 0.75
NOTES_HEADER = "YOUR NOTES FROM THE EARLIER RUN (you wrote these; do not redo that work):"

_LAST_TAIL = " SUBMIT your best complete file(s) now; a tool call here is wasted."


def clean_note(text: object) -> str | None:
    """One line of finding, or None when there is nothing to keep."""
    if not isinstance(text, str):
        return None
    note = " ".join(text.split())
    if not note:
        return None
    if len(note) > NOTE_MAX_CHARS:
        return note[:NOTE_MAX_CHARS - 3].rstrip() + "..."
    return note


def add_note(notes: list[str], text: object) -> bool:
    """Append a cleaned, new note to notes; True when it was added."""
    note = clean_note(text)
    if note is None or note in notes:
        return False
    notes.append(note)
    return True


def render_notes(notes: list[str], max_chars: int = NOTES_MAX_CHARS) -> str:
    """The block a re-run job is given once; newest notes kept when they do not all fit."""
    if not notes:
        return ""
    lines = [f"- {note}" for note in notes]
    kept = [lines[-1]]
    size = len(lines[-1])
    for line in reversed(lines[:-1]):
        if size + 1 + len(line) > max_chars:
            break
        kept.insert(0, line)
        size += 1 + len(line)
    dropped = len(lines) - len(kept)
    out = NOTES_HEADER
    if dropped:
        out += f"\n({dropped} older note{'s' if dropped != 1 else ''} folded away)"
    return out + "\n" + "\n".join(kept)


def stub(tool: str, args: dict, content: str, keep_chars: int = 400) -> str:
    """What an old tool result becomes when it is trimmed."""
    if len(content) <= keep_chars:
        return content
    call = f"{tool}({json.dumps(args, sort_keys=True)})"
    return (content[:keep_chars]
            + f"\n...[trimmed: {call} gave {len(content)} chars; call it again to re-read a part]")


def budget_line(tokens_used: int, max_tokens: int, last_request_tokens: int,
                requests_left: int) -> tuple[str, bool]:
    """The line that leads the next message, and whether it must be the last reply."""
    pct = 0 if max_tokens <= 0 else min(100, (100 * tokens_used) // max_tokens)
    if requests_left <= 1:
        return "LAST REPLY: this is your last reply." + _LAST_TAIL, True
    if max_tokens > 0 and tokens_used + last_request_tokens >= max_tokens:
        return (f"LAST REPLY: {pct}% of this job's token budget is spent and one more "
                f"reply this size would use the rest." + _LAST_TAIL), True
    if max_tokens > 0 and tokens_used >= WARN_AT * max_tokens:
        return (f"TOKENS: {pct}% of this job's token budget is spent. Note what you "
                f"still need and SUBMIT soon."), False
    return "", False


def lead_with(line: str, content: str) -> str:
    """Put a budget line in front of a message, where it is read."""
    return content if line == "" else f"{line}\n\n{content}"
