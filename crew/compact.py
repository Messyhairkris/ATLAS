"""compact.py - utilities for managing notes, stubs, and budget warnings.

This module implements the public API defined in the contract (crew/contracts/compact.md).
It contains only the allowed import (`json`) and follows the exact rules and ordering
specified. Written by Hoss in campaign atlas-compact-ask (2026-10-26), 1 request.
"""

import json

NOTE_MAX_CHARS = 300
NOTES_MAX_CHARS = 3000
WARN_AT = 0.75
NOTES_HEADER = (
    "YOUR NOTES FROM THE EARLIER RUN (you wrote these; do not redo that work):"
)


def clean_note(text: object) -> str | None:
    """Return a cleaned note string or ``None`` according to the contract rules.

    1. Non-string input yields ``None``.
    2. Collapse all whitespace to a single space and strip ends.
    3. Empty result yields ``None``.
    4. If longer than :data:`NOTE_MAX_CHARS`, truncate to
       ``NOTE_MAX_CHARS - 3`` characters, right-strip, and append ``"..."``.
    5. Otherwise return the cleaned string.
    """
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    if len(cleaned) > NOTE_MAX_CHARS:
        truncated = cleaned[: NOTE_MAX_CHARS - 3].rstrip()
        return truncated + "..."
    return cleaned


def add_note(notes: list[str], text: object) -> bool:
    """Add a cleaned note to ``notes`` if it is new.

    Returns ``True`` when a note is appended, ``False`` otherwise.
    """
    n = clean_note(text)
    if n is None:
        return False
    if n in notes:
        return False
    notes.append(n)
    return True


def render_notes(notes: list[str], max_chars: int = NOTES_MAX_CHARS) -> str:
    """Render the newest notes that fit within ``max_chars``.

    The output always starts with :data:`NOTES_HEADER`. If some older notes are
    omitted, a line ``"(N older note(s) folded away)"`` is inserted.
    """
    if not notes:
        return ""

    # Convert notes to lines prefixed with "- ".
    lines = ["- " + note for note in notes]

    # Keep newest lines that fit, always keeping the newest one.
    kept_rev: list[str] = []
    total_len = 0
    for line in reversed(lines):
        if not kept_rev:
            kept_rev.append(line)
            total_len = len(line)
            continue
        # Adding a newline before the line.
        if total_len + 1 + len(line) <= max_chars:
            kept_rev.append(line)
            total_len += 1 + len(line)
        else:
            break

    kept = list(reversed(kept_rev))
    dropped = len(lines) - len(kept)

    parts = [NOTES_HEADER]
    if dropped:
        suffix = f"({dropped} older note{'s' if dropped != 1 else ''} folded away)"
        parts.append(suffix)
    parts.append("\n".join(kept))
    return "\n".join(parts)


def stub(tool: str, args: dict, content: str, keep_chars: int = 400) -> str:
    """Return a trimmed representation of a tool result.

    If ``content`` is short enough it is returned unchanged; otherwise the first
    ``keep_chars`` characters are kept followed by a trimmed-info line.
    """
    if len(content) <= keep_chars:
        return content
    call = f"{tool}({json.dumps(args, sort_keys=True)})"
    trimmed_msg = (
        f"\n...[trimmed: {call} gave {len(content)} chars; "
        "call it again to re-read a part]"
    )
    return content[:keep_chars] + trimmed_msg


def budget_line(
    tokens_used: int,
    max_tokens: int,
    last_request_tokens: int,
    requests_left: int,
) -> tuple[str, bool]:
    """Generate the budget warning line and indicate if this must be the final reply.

    Returns a tuple ``(line, last)`` where ``last`` is ``True`` when the member
    should submit and not make further tool calls.
    """
    pct = (
        0
        if max_tokens <= 0
        else min(100, (100 * tokens_used) // max_tokens)
    )

    # Rule 1
    if requests_left <= 1:
        msg = (
            "LAST REPLY: this is your last reply. SUBMIT your best complete file(s) now; "
            "a tool call here is wasted."
        )
        return msg, True

    # Rule 2
    if max_tokens > 0 and tokens_used + last_request_tokens >= max_tokens:
        msg = (
            f"LAST REPLY: {pct}% of this job's token budget is spent and one more reply "
            "this size would use the rest. SUBMIT your best complete file(s) now; "
            "a tool call here is wasted."
        )
        return msg, True

    # Rule 3
    if max_tokens > 0 and tokens_used >= WARN_AT * max_tokens:
        msg = (
            f"TOKENS: {pct}% of this job's token budget is spent. "
            "Note what you still need and SUBMIT soon."
        )
        return msg, False

    # Rule 4
    return "", False


def lead_with(line: str, content: str) -> str:
    """Prepend ``line`` to ``content`` separated by a blank line unless ``line`` is empty."""
    if line == "":
        return content
    return f"{line}\n\n{content}"
