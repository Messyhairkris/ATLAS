"""Public API of an ES module: exported names, missing names, stubs."""

import re

from js_lex import code_only

_NAME = r"[A-Za-z_$][A-Za-z0-9_$]*"
_NOT_WORD = r"(?<![A-Za-z0-9_$.])"

_EXPORT_HEADS = (
    r"(?:async\s+)?function\s*\*?\s*(" + _NAME + r")",
    r"class\s+(" + _NAME + r")",
    r"(?:const|let|var)\s+(" + _NAME + r")",
    r"\*\s+as\s+(" + _NAME + r")",
)


def exported_names(source: str) -> list[str]:
    """Names the module exports, in order of first appearance, each once."""
    code = code_only(source)
    names: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(_NOT_WORD + r"export", code):
        for name in _export_names_after(code[match.end() :]):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def missing_api(source: str, required: list[str]) -> list[str]:
    """Required names the module does not export, in required order."""
    exported = set(exported_names(source))
    return [name for name in required if name not in exported]


def stub_functions(source: str) -> list[str]:
    """Named function declarations, in order of appearance, whose body is
    empty or exactly one throw new Error with an empty or string argument."""
    code = code_only(source)
    stubs: list[str] = []
    for match in re.finditer(_NOT_WORD + r"function", code):
        head = re.match(r"\s*\*?\s*(" + _NAME + r")\s*\(", code[match.end() :])
        if head is None:
            continue
        open_paren = match.end() + head.end() - 1
        close_paren = _matching(code, open_paren, "(", ")")
        if close_paren < 0:
            continue
        open_brace = code.find("{", close_paren + 1)
        if open_brace < 0:
            continue
        close_brace = _matching(code, open_brace, "{", "}")
        if close_brace < 0:
            continue
        body = re.sub(r"\s+", "", code[open_brace + 1 : close_brace])
        if body == "" or re.fullmatch(r'thrownewError\((?:"")?\);?', body):
            stubs.append(head.group(1))
    return stubs


def _export_names_after(rest: str) -> list[str]:
    if rest.startswith("{"):
        return _names_in_braces(rest)
    space = re.match(r"\s+", rest)
    if space is None:
        return []
    rest = rest[space.end() :]
    if re.match(r"default\b", rest):
        return ["default"]
    for pattern in _EXPORT_HEADS:
        match = re.match(pattern, rest)
        if match is not None:
            return [match.group(1)]
    if rest.startswith("{"):
        return _names_in_braces(rest)
    return []


def _names_in_braces(text: str) -> list[str]:
    close = _matching(text, 0, "{", "}")
    if close < 0:
        return []
    names: list[str] = []
    for part in text[1:close].split(","):
        words = part.split()
        if words:
            names.append(words[-1])
    return names


def _matching(text: str, open_index: int, open_ch: str, close_ch: str) -> int:
    # Index of the close_ch matching the open_ch at open_index, or -1.
    depth = 0
    for i in range(open_index, len(text)):
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1
