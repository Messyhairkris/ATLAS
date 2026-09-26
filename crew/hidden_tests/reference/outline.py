"""outline.py - see a file's structure before reading it."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """One structural line of a file: where it is and what it opens."""
    line: int
    depth: int
    kind: str
    name: str


_PY_RE = re.compile(
    r"^([ \t]*)(async[ \t]+def|def|class)[ \t]+([A-Za-z_][A-Za-z0-9_]*)"
)
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_CLOSING_RE = re.compile(r"[ \t]+#+$")


def outline(text: str, kind: str) -> list[Entry]:
    """List the structural entries of `text`, in file order."""
    if kind == "python":
        return _python(text)
    if kind == "markdown":
        return _markdown(text)
    raise ValueError(
        f"unknown kind {kind!r}: expected 'python' or 'markdown'"
    )


def render(entries: list[Entry]) -> str:
    """One text line per entry, indented two spaces per depth."""
    return "\n".join(
        "  " * e.depth + f"L{e.line}  {e.kind} {e.name}" for e in entries
    )


def _python(text: str) -> list[Entry]:
    entries: list[Entry] = []
    stack: list[int] = []
    in_string = False
    delimiter = ""
    for line_no, line in enumerate(text.splitlines(), 1):
        was_in_string = in_string
        in_string, delimiter = _scan_string_state(line, in_string, delimiter)
        if was_in_string:
            continue
        match = _PY_RE.match(line)
        if match is None:
            continue
        indent, keyword, name = match.groups()
        width = _indent_width(indent)
        while stack and stack[-1] >= width:
            stack.pop()
        kind = "async def" if keyword.startswith("async") else keyword
        entries.append(Entry(line_no, len(stack), kind, name))
        stack.append(width)
    return entries


def _scan_string_state(
    line: str, in_string: bool, delimiter: str
) -> tuple[bool, str]:
    """Advance the triple-quote state over one line; `#` ends scanning."""
    i = 0
    while i < len(line):
        if in_string:
            if line.startswith(delimiter, i):
                in_string = False
                delimiter = ""
                i += 3
            else:
                i += 1
        elif line[i] == "#":
            break
        elif line.startswith('"""', i) or line.startswith("'''", i):
            in_string = True
            delimiter = line[i:i + 3]
            i += 3
        else:
            i += 1
    return in_string, delimiter


def _indent_width(indent: str) -> int:
    """A space is one column; a tab advances to the next multiple of 8."""
    width = 0
    for ch in indent:
        width += 8 - width % 8 if ch == "\t" else 1
    return width


def _markdown(text: str) -> list[Entry]:
    entries: list[Entry] = []
    fenced = False
    for line_no, line in enumerate(text.splitlines(), 1):
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        hashes, raw = match.groups()
        name = _heading_name(raw)
        entries.append(Entry(line_no, len(hashes) - 1, "heading", name))
    return entries


def _heading_name(raw: str | None) -> str:
    """Strip the heading text, then a closing run of hashes if there is one."""
    text = (raw or "").strip(" \t")
    if text and not text.strip("#"):
        return ""
    return _CLOSING_RE.sub("", text).strip(" \t")
