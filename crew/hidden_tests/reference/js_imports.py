"""Find what a JavaScript module imports and which forbidden globals it touches."""

import re

from js_lex import code_only, segments

FORBIDDEN_GLOBALS = ("eval", "Function", "process", "require", "fetch",
                     "XMLHttpRequest", "WebSocket", "Worker", "globalThis",
                     "window", "document")
_BEFORE = re.compile(
    r"(?:(?<![\w$.])(?:from|import)|(?<![\w$.])(?:import|require)\s*\(\s*)\Z")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def imports(source: str) -> list[str]:
    """Specifiers in order of appearance, duplicates kept."""
    found: list[str] = []
    before = ""
    for kind, text in segments(source):
        if kind == "comment":
            continue
        if kind == "string" and _BEFORE.search(before.rstrip()):
            found.append(text[1:-1])
        before = before + text if kind == "code" else ""
    return found


def check_imports(source: str, allowed: set[str]) -> list[str]:
    """Specifiers not in allowed, sorted and unique."""
    return sorted({s for s in imports(source) if s not in allowed})


def forbidden_uses(source: str) -> list[str]:
    """Forbidden names used as identifiers, not as properties; sorted, unique."""
    code = code_only(source)
    hits = set()
    for m in _IDENT.finditer(code):
        if m.group() in FORBIDDEN_GLOBALS:
            if not code[:m.start()].rstrip().endswith("."):
                hits.add(m.group())
    return sorted(hits)
