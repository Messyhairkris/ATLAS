"""review_anchors: as accepted from the Crew.

Written by Hoss of the Crew, from the contract `contracts/tts_review_anchors.md`, and accepted
only after passing tests it was never allowed to read (campaign review-desk + revision).

Vendored into this project on 2026-09-20. The ONLY change made on the way in was the
import rewrite listed in PROVENANCE.md; the logic is exactly what was accepted.
"""

# The module's own docstring, unchanged:
# """review_anchors.py - utilities for anchoring notes to source lines.
# 
# Implements the contract described in the task specification. All functions are
# pure and operate on supplied text strings; no I/O is performed.
# """

from __future__ import annotations

import hashlib
import re
from typing import Dict

CONTEXT_LINES = 2


def _split_lines(text: str) -> list[str]:
    """Return a list of lines without trailing newlines."""
    return text.splitlines()


def _validate_range(text: str, first_line: int, last_line: int) -> None:
    """Raise ValueError if the line range is invalid for the given text."""
    if not text:
        raise ValueError("text is empty")
    if first_line < 1:
        raise ValueError("first_line must be >= 1")
    if last_line < first_line:
        raise ValueError("last_line must be >= first_line")
    lines = _split_lines(text)
    if last_line > len(lines):
        raise ValueError("last_line beyond end of text")


def make_anchor(text: str, first_line: int, last_line: int) -> Dict[str, object]:
    """Create an anchor dict containing line numbers, quote and digest."""
    _validate_range(text, first_line, last_line)
    lines = _split_lines(text)
    quote = "\n".join(lines[first_line - 1 : last_line])
    digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()[:12]
    return {
        "first_line": first_line,
        "last_line": last_line,
        "quote": quote,
        "digest": digest,
    }


def format_anchor(anchor: Dict[str, object]) -> str:
    """Return a compact string label for *anchor* (e.g. ``L12-L18#a1b2c3d4e5f6``)."""
    return f"L{anchor['first_line']}-L{anchor['last_line']}#{anchor['digest']}"


_anchor_re = re.compile(r"^L(\d+)-L(\d+)#([0-9a-f]{12})$", re.IGNORECASE)


def parse_anchor(label: str) -> Dict[str, object]:
    """Parse *label* produced by :func:`format_anchor` back into an anchor dict."""
    m = _anchor_re.fullmatch(label.strip())
    if not m:
        raise ValueError("label does not match anchor format")
    first_line, last_line, digest = m.groups()
    return {
        "first_line": int(first_line),
        "last_line": int(last_line),
        "digest": digest,
    }


def excerpt(text: str, anchor: Dict[str, object]) -> str:
    """Return a formatted excerpt around *anchor* with context lines."""
    lines = _split_lines(text)
    total = len(lines)
    first = anchor["first_line"]
    last = anchor["last_line"]
    if first < 1 or last > total or first > last:
        raise ValueError("anchor lines out of range")
    start = max(1, first - CONTEXT_LINES)
    end = min(total, last + CONTEXT_LINES)
    width = len(str(end))
    out: list[str] = []
    for i in range(start, end + 1):
        mark = ">" if first <= i <= last else " "
        out.append(f"{mark} {i:>{width}}: {lines[i - 1]}")
    return "\n".join(out)


def relocate(
    anchor: Dict[str, object], new_text: str
) -> Dict[str, object]:
    """Find *anchor*'s quote in *new_text* and report its new location."""
    quote = anchor["quote"]
    quote_lines = quote.split("\n")
    n = len(quote_lines)
    new_lines = _split_lines(new_text)

    matches: list[int] = []
    for i in range(len(new_lines) - n + 1):
        if new_lines[i : i + n] == quote_lines:
            matches.append(i)  # store 0-based start index

    original_start = anchor["first_line"] - 1
    status = "stale"
    moved_by = 0
    new_first = anchor["first_line"]
    new_last = anchor["last_line"]

    if original_start in matches:
        status = "unchanged"
        # keep original numbers
    elif len(matches) == 1:
        status = "moved"
        new_first = matches[0] + 1
        new_last = new_first + n - 1
        moved_by = new_first - anchor["first_line"]
    elif len(matches) > 1:
        status = "ambiguous"
        # keep original numbers

    result = {
        "first_line": new_first,
        "last_line": new_last,
        "quote": quote,
        "digest": anchor["digest"],
        "status": status,
        "moved_by": moved_by,
    }
    return result
