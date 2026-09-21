"""Read the public API of an ES module and spot functions that are only stubs."""

import re

from js_lex import code_only

_DECL = re.compile(
    r"(?<![\w$.])export(?:\s+(?:"
    r"(?P<default>default)\b"
    r"|(?:async\s+)?function\s*\*?\s*(?P<fn>[A-Za-z_$][\w$]*)"
    r"|class\s+(?P<cls>[A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+(?P<var>[A-Za-z_$][\w$]*)"
    r"|\*\s*as\s+(?P<ns>[A-Za-z_$][\w$]*))"
    r"|\s*\{(?P<list>[^}]*)\})")
_FUNC = re.compile(r"(?<![\w$.])function\s*\*?\s*(?P<name>[A-Za-z_$][\w$]*)\s*\(")
_THROW = re.compile(r"throw\s+new\s+Error\s*\(\s*(?:\"\")?\s*\)\s*;?")


def exported_names(source: str) -> list[str]:
    """Exported names in order of first appearance, each once."""
    names: list[str] = []
    for m in _DECL.finditer(code_only(source)):
        if m.group("list") is not None:
            found = [part.split()[-1] for part in m.group("list").split(",")
                     if part.strip()]
        else:
            found = [next(v for v in m.groups() if v is not None)]
        names.extend(n for n in found if n not in names)
    return names


def missing_api(source: str, required: list[str]) -> list[str]:
    """Required names that are not exported, in the order given."""
    have = set(exported_names(source))
    return [n for n in required if n not in have]


def _match(code: str, i: int, open_: str, close: str) -> int:
    depth = 0
    for j in range(i, len(code)):
        depth += (code[j] == open_) - (code[j] == close)
        if depth == 0:
            return j
    return len(code)


def stub_functions(source: str) -> list[str]:
    """Named function declarations whose body is empty or only throws."""
    code = code_only(source)
    stubs: list[str] = []
    for m in _FUNC.finditer(code):
        after = _match(code, m.end() - 1, "(", ")")
        start = code.find("{", after)
        if start < 0:
            continue
        body = code[start + 1:_match(code, start, "{", "}")].strip()
        if body == "" or _THROW.fullmatch(body):
            stubs.append(m.group("name"))
    return stubs
