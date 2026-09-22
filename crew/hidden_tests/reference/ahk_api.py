"""Reference implementation of contracts/ahk_api.md (never given to the crew)."""

import re

from ahk_lex import code_lines

KEYWORDS = frozenset({"if", "while", "for", "loop", "switch", "catch", "return",
                      "else", "until", "try", "throw", "finally", "and", "or", "not"})
_HEAD = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\(([^()]*)\)\s*(\{)?\s*$")
_CONST = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*:=\s*\S")


def _params(text: str) -> list:
    """Parameter names only: no ByRef, no default value, no trailing '*'."""
    out = []
    for part in text.split(","):
        part = re.sub(r"^\s*byref\s+", "", part, flags=re.IGNORECASE).strip()
        if part:
            out.append(re.split(r"\s*:?=|\*", part)[0].strip())
    return out


def functions(source: str) -> dict:
    """Lowercase name -> {name, params, line, end, body} for every definition."""
    lines = code_lines(source)
    found = {}
    i = 0
    while i < len(lines):
        number, text = lines[i]
        head = _HEAD.match(text)
        if not head or head.group(1).lower() in KEYWORDS:
            i += 1
            continue
        opener = i
        if not head.group(3):
            if i + 1 >= len(lines) or lines[i + 1][1].strip() != "{":
                i += 1
                continue
            opener = i + 1
        depth, k = 0, opener
        while k < len(lines):
            depth += lines[k][1].count("{") - lines[k][1].count("}")
            if depth <= 0:
                break
            k += 1
        if k >= len(lines):                 # never balanced: runs to the end
            k = len(lines) - 1
            body = [t.strip() for _n, t in lines[opener + 1:]]
        else:
            body = [t.strip() for _n, t in lines[opener + 1:k]]
        found[head.group(1).lower()] = {"name": head.group(1),
                                        "params": _params(head.group(2)),
                                        "line": number, "end": lines[k][0],
                                        "body": body}
        i = k + 1
    return found


def missing(source: str, api) -> list:
    """Contract names with no definition, compared without case, in api order."""
    defined = functions(source)
    return [name for name in api if name.lower() not in defined]


def stubs(source: str) -> list:
    """Functions that do nothing: no statement, or only a bare `return`."""
    return [info["name"] for info in functions(source).values()
            if all(s.lower() == "return" for s in info["body"] if s not in "{}")]


def top_level(source: str) -> list:
    """Code lines outside every function, other than `NAME := value` and
    directives (the scanner judges those)."""
    spans = [(f["line"], f["end"]) for f in functions(source).values()]
    return [n for n, t in code_lines(source)
            if not any(a <= n <= b for a, b in spans)
            and not _CONST.match(t) and not t.strip().startswith("#")]
