"""Parsers for The Crew's Changes pane (Kris, 2026-10-24).

`git status --porcelain=v2 --branch` and `git diff --numstat HEAD` output,
turned into plain dicts. Pure parsing - no subprocess, no I/O - so every
porcelain rule lives here with its tests (tests/test_changes.py) and
crew/runners/changes.py only runs git and shapes JSON. Paths come C-quoted by
git when they need it; unquote() reverses that.
"""

import re

# Git's C-style quoting, the escapes the Changes pane honours: \\ \" \t \n
# plus three-digit octal byte escapes (decoded as UTF-8).
_ESCAPES = {"\\": b"\\", '"': b'"', "t": b"\t", "n": b"\n"}

_KINDS = {"A": "added", "D": "deleted", "M": "modified", "T": "typechange"}


def unquote(path: str) -> str:
    """Reverse git's C-quoting: strip surrounding quotes and turn \\, \", \\t,
    \\n and three-digit octal escapes (bytes, decoded as UTF-8) back. A path
    without surrounding quotes is returned unchanged."""
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    body = path[1:-1]
    out = bytearray()
    pos = 0
    for match in re.finditer(r"\\([0-7]{3}|.)", body, re.DOTALL):
        out += body[pos : match.start()].encode("utf-8")
        token = match.group(1)
        if len(token) == 3:  # octal: one byte value
            out.append(int(token, 8))
        elif token in _ESCAPES:
            out += _ESCAPES[token]
        else:  # unknown escape: keep literal
            out += ("\\" + token).encode("utf-8")
        pos = match.end()
    out += body[pos:].encode("utf-8")
    return out.decode("utf-8", errors="replace")


def _kind(xy: str, line_type: str) -> str:
    """The file's kind, first rule that applies: untracked and conflict are
    decided by their line type in parse_status; a rename-or-copy line is
    "renamed" when X or Y is R, "copied" when C; otherwise the first of X, Y
    that is not "." decides, anything else is "modified"."""
    if line_type == "2":
        if "R" in xy[:2]:
            return "renamed"
        if "C" in xy[:2]:
            return "copied"
    for c in xy[:2]:
        if c != ".":
            return _KINDS.get(c, "modified")
    return "modified"


def _entry(xy: str, line_type: str, path: str, orig: str = "") -> dict:
    return {
        "path": path,
        "orig": orig,
        "staged": xy[0],
        "unstaged": xy[1],
        "kind": _kind(xy, line_type),
    }


def parse_status(text: str) -> dict:
    """`git status --porcelain=v2 --branch` ->
    {"branch", "oid", "upstream", "ahead", "behind", "files": [...]}.
    Missing headers give "" and 0; "!"/ignored and unknown lines are skipped."""
    status = {
        "branch": "",
        "oid": "",
        "upstream": "",
        "ahead": 0,
        "behind": 0,
        "files": [],
    }
    for line in text.splitlines():
        if line.startswith("# branch.oid "):
            status["oid"] = line[len("# branch.oid ") :]
        elif line.startswith("# branch.head "):
            status["branch"] = line[len("# branch.head ") :]
        elif line.startswith("# branch.upstream "):
            status["upstream"] = line[len("# branch.upstream ") :]
        elif line.startswith("# branch.ab "):
            match = re.match(r"# branch\.ab \+(\d+) -(\d+)", line)
            if match:
                status["ahead"] = int(match.group(1))
                status["behind"] = int(match.group(2))
        elif line.startswith("1 "):  # ordinary change
            fields = line.split(" ")
            status["files"].append(
                _entry(fields[1], "1", unquote(" ".join(fields[8:])))
            )
        elif line.startswith("2 "):  # renamed or copied
            fields = line.split(" ")
            path, sep, orig = " ".join(fields[9:]).partition("\t")
            status["files"].append(
                _entry(fields[1], "2", unquote(path), unquote(orig) if sep else "")
            )
        elif line.startswith("u "):  # unmerged
            fields = line.split(" ")
            status["files"].append(
                {
                    "path": unquote(" ".join(fields[10:])),
                    "orig": "",
                    "staged": fields[1][0],
                    "unstaged": fields[1][1],
                    "kind": "conflict",
                }
            )
        elif line.startswith("? "):  # untracked
            status["files"].append(
                {
                    "path": unquote(line[2:]),
                    "orig": "",
                    "staged": "?",
                    "unstaged": "?",
                    "kind": "untracked",
                }
            )
        # "!" (ignored) and anything else: skip.
    return status


def parse_numstat(text: str) -> dict:
    """`git diff --numstat HEAD` -> {path: [added, deleted]}; a binary file
    (-\\t-) maps to None. Rename forms (a => b, dir/{a => b}/f) are kept as
    git prints them. Blank lines are skipped."""
    stats = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], "\t".join(parts[2:])
        stats[path] = None if added == "-" else [int(added), int(deleted)]
    return stats


def summary(status: dict) -> str:
    """One line for the pane: "clean" when nothing to say, otherwise the parts
    that apply, joined with ", ". Conflicts count separately AND inside
    changed."""
    files = status["files"]
    changed = sum(1 for f in files if f["kind"] != "untracked")
    untracked = sum(1 for f in files if f["kind"] == "untracked")
    conflicts = sum(1 for f in files if f["kind"] == "conflict")
    parts = []
    if changed:
        parts.append(f"{changed} changed")
    if untracked:
        parts.append(f"{untracked} untracked")
    if conflicts:
        parts.append(f"{conflicts} conflict" + ("s" if conflicts != 1 else ""))
    if status["ahead"]:
        parts.append(f"ahead {status['ahead']}")
    if status["behind"]:
        parts.append(f"behind {status['behind']}")
    return ", ".join(parts) if parts else "clean"
