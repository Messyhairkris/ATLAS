"""Reference implementation for the problems_lib.py contract (IDE Phase 1, Problems pane).

Pure: no IO except load()'s explicit read of a settings file, no clock, no process.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

LOC_WITHIN = 3

KINDS: List[Dict[str, Any]] = [
    {"name": "cargo",
     "head": r"^(?P<level>error|warning)(?:\[(?P<code>[A-Z]+\d+)\])?: (?P<message>\S.*)$",
     "loc": r"^\s*--> (?P<file>.+?):(?P<line>\d+):(?P<col>\d+)\s*$",
     "level": None},
    {"name": "pytest",
     "head": r"^(?P<file>[^\s:]+\.py):(?P<line>\d+): (?P<message>.+)$",
     "loc": None,
     "level": "error"},
]


def load(settings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """KINDS, or KINDS merged with the `kinds` list of a settings dict (a new tool is settings)."""
    if settings is None or not isinstance(settings, dict):
        return list(KINDS)
    file_kinds = settings.get("kinds")
    if file_kinds is None:
        return list(KINDS)
    if not isinstance(file_kinds, list):
        raise ValueError("kinds must be a list")
    by_name: Dict[str, Dict[str, Any]] = {}
    for kind in file_kinds:
        if not isinstance(kind, dict) or not kind.get("name"):
            raise ValueError("each kind needs a name")
        by_name[kind["name"]] = kind
    builtin = [k["name"] for k in KINDS]
    out = [by_name.get(name, k) for name, k in zip(builtin, KINDS)]
    seen = set(builtin)
    for kind in file_kinds:
        if kind["name"] not in seen:
            out.append(kind)
            seen.add(kind["name"])
    return out


def parse(text: Optional[str], kinds: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """The problems in `text`, in the order they appear, deduplicated (rule 1-6 of the contract)."""
    if not text:
        return []
    compiled = [_compile(k) for k in (KINDS if kinds is None else kinds)]
    lines = text.splitlines()
    out: List[Dict[str, Any]] = []
    for i, line in enumerate(lines):
        for name, level, head_re, loc_re in compiled:
            m = head_re.match(line)
            if not m:
                continue
            g = m.groupdict()
            severity = (g.get("level") or level or "error").lower()
            if severity not in ("error", "warning"):
                severity = "error"
            problem = {
                "kind": name,
                "severity": severity,
                "file": g.get("file"),
                "line": _as_int(g.get("line")),
                "col": _as_int(g.get("col")),
                "code": g.get("code") or None,
                "message": (g.get("message") or "").strip(),
            }
            if loc_re is not None and problem["line"] is None:
                for j in range(i + 1, min(i + 1 + LOC_WITHIN, len(lines))):
                    lm = loc_re.match(lines[j])
                    if lm:
                        lg = lm.groupdict()
                        if problem["file"] is None and lg.get("file"):
                            problem["file"] = lg["file"]
                        if problem["line"] is None and lg.get("line"):
                            problem["line"] = _as_int(lg["line"])
                        if problem["col"] is None and lg.get("col"):
                            problem["col"] = _as_int(lg["col"])
                        break
            out.append(problem)
            break
    return _dedupe(out)


def format_problem(p: Dict[str, Any]) -> str:
    """One line for the pane: position, then severity[code], then the message."""
    parts: List[str] = []
    if p.get("file"):
        loc = str(p["file"])
        if p.get("line") is not None:
            loc += ":" + str(p["line"])
        if p.get("col") is not None:
            loc += ":" + str(p["col"])
        parts.append(loc)
    head = str(p.get("severity") or "error")
    if p.get("code"):
        head += "[%s]" % p["code"]
    parts.append(head)
    message = str(p.get("message") or "").strip()
    if message:
        parts.append(message)
    return ": ".join(parts)


def _compile(kind: Dict[str, Any]):
    """(name, fixed level, head regex, loc regex) for one kind; ValueError when it is unusable."""
    if not isinstance(kind, dict) or not kind.get("name") or not kind.get("head"):
        raise ValueError("a kind needs a name and a head")
    loc = kind.get("loc")
    return (kind["name"], kind.get("level"), re.compile(kind["head"]),
            re.compile(loc) if loc else None)


def _as_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(problems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for p in problems:
        key = (p["kind"], p["file"], p["line"], p["col"], p["code"], p["message"])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
