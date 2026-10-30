"""problems_lib.py - turning build output into the Problems pane's rows.

Pure: the log text arrives as an argument, and nothing here reads a file, a
clock, a process or the screen.
"""

from __future__ import annotations

import re

LOC_WITHIN = 3

KINDS: list[dict[str, object]] = [
    {
        "name": "cargo",
        "head": (
            r"^(?P<level>error|warning)(?:\[(?P<code>[A-Z]+\d+)\])?: "
            r"(?P<message>\S.*)$"
        ),
        "loc": r"^\s*--> (?P<file>.+?):(?P<line>\d+):(?P<col>\d+)\s*$",
        "level": None,
    },
    {
        "name": "pytest",
        "head": r"^(?P<file>[^\s:]+\.py):(?P<line>\d+): (?P<message>.+)$",
        "loc": None,
        "level": "error",
    },
]


def _checked_kind(kind: object) -> dict[str, object]:
    """Rule 8: a kind with no name, or with no head, is a settings error."""
    if not isinstance(kind, dict):
        raise ValueError("a kind must be a dict")
    if not kind.get("name") or not kind.get("head"):
        raise ValueError("a kind needs a name and a head")
    return kind


def _group_int(match: re.Match[str], name: str) -> int | None:
    """Rule 5: int() is only applied to a group that matched a \\d+."""
    value = match.groupdict().get(name)
    if value is None or not value.isdigit():
        return None
    return int(value)


def _build_problem(kind: dict[str, object], match: re.Match[str]) -> dict[str, object]:
    """Rule 3: build one problem from the head match of one kind."""
    groups = match.groupdict()
    level = groups.get("level")
    if level is not None:
        severity = level.lower()
    elif kind.get("level"):
        severity = str(kind["level"])
    else:
        severity = "error"
    if severity not in ("error", "warning"):
        severity = "error"
    line = _group_int(match, "line")
    col = _group_int(match, "col")
    if line is None:
        col = None
    message = groups.get("message")
    return {
        "kind": kind["name"],
        "severity": severity,
        "file": groups.get("file"),
        "line": line,
        "col": col,
        "code": groups.get("code"),
        "message": message.strip() if message is not None else "",
    }


def _apply_loc(
    problem: dict[str, object],
    kind: dict[str, object],
    lines: list[str],
    start: int,
) -> None:
    """Rule 4: the first loc match within LOC_WITHIN following lines wins."""
    loc = kind.get("loc")
    if not loc or problem["line"] is not None:
        return
    pattern = re.compile(str(loc))
    stop = min(start + LOC_WITHIN, len(lines))
    for index in range(start, stop):
        match = pattern.match(lines[index])
        if match is None:
            continue
        groups = match.groupdict()
        if groups.get("file") is not None:
            problem["file"] = groups["file"]
        line = _group_int(match, "line")
        if line is not None:
            problem["line"] = line
        col = _group_int(match, "col")
        if col is not None:
            problem["col"] = col
        if problem["line"] is None:
            problem["col"] = None
        return


def load(settings: dict[str, object] | None = None) -> list[dict[str, object]]:
    """load: the built-ins in a new list, merged with settings when given."""
    merged = [dict(kind) for kind in KINDS]
    if settings is None:
        return merged
    if not isinstance(settings, dict):
        raise ValueError("settings must be a dict")
    extra = settings.get("kinds")
    if extra is None:
        return merged
    if not isinstance(extra, list):
        raise ValueError("settings['kinds'] must be a list")
    places = {kind["name"]: index for index, kind in enumerate(merged)}
    for kind in extra:
        checked = _checked_kind(kind)
        name = checked["name"]
        if name in places:
            merged[places[name]] = dict(checked)
        else:
            places[name] = len(merged)
            merged.append(dict(checked))
    return merged


def parse(
    text: str | None,
    kinds: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """parse: one pass over the lines, first kind wins, deduplicated in order."""
    if not text:
        return []
    if kinds is None:
        kinds = KINDS
    heads = [(_checked_kind(kind), re.compile(str(kind["head"]))) for kind in kinds]
    lines = text.splitlines()
    problems: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for index, line in enumerate(lines):
        for kind, head in heads:
            match = head.match(line)
            if match is None:
                continue
            problem = _build_problem(kind, match)
            _apply_loc(problem, kind, lines, index + 1)
            key = (
                problem["kind"],
                problem["file"],
                problem["line"],
                problem["col"],
                problem["code"],
                problem["message"],
            )
            if key not in seen:
                seen.add(key)
                problems.append(problem)
            break
    return problems


def format_problem(p: dict[str, object]) -> str:
    """format_problem: position, then severity with [code], then message."""
    parts: list[str] = []
    file = p.get("file")
    if file:
        position = str(file)
        if p.get("line") is not None:
            position += f":{p['line']}"
            if p.get("col") is not None:
                position += f":{p['col']}"
        parts.append(position)
    severity = p.get("severity")
    if severity:
        text = str(severity)
        code = p.get("code")
        if code:
            text += f"[{code}]"
        parts.append(text)
    message = p.get("message")
    if message:
        parts.append(str(message))
    return ": ".join(parts)
