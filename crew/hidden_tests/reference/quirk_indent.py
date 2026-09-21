"""Reference for quirk_indent.py: text copied from a contract, re-indented by a member."""

import re

VERBATIM_TAGS = ("html", "text", "verbatim")
MIN_CHARS = 6
_FENCE = re.compile(r"^```([^\n`]*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_LITERAL = re.compile(r"""(["'])((?:\\.|(?!\1).)*)\1""")
_NL = "\\n"


def verbatim_lines(contract: str) -> list[str]:
    """Lines of the contract's verbatim blocks, in order, each once."""
    out: list[str] = []
    for info, body in _FENCE.findall(contract):
        if info.strip().lower() not in VERBATIM_TAGS:
            continue
        for line in body.split("\n"):
            if len(line.strip()) >= MIN_CHARS and line not in out:
                out.append(line)
    return out


_PLACEHOLDER = re.compile(r"\{[^{}\s][^{}]*\}")


def _lead(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _core(content: str) -> str:
    return content[:-2] if content.endswith(_NL) else content


def _wanted(lines: list[str]) -> dict[str, int]:
    """Stripped text -> leading spaces, for whole lines and for the text before a
    line's first {placeholder} (when that text is long enough to be unambiguous)."""
    wanted: dict[str, int] = {}
    for line in lines:
        m = _PLACEHOLDER.search(line)
        key = (line[:m.start()] if m else line).strip()
        if len(key) >= MIN_CHARS:
            wanted.setdefault(key, _lead(line))
    return wanted


def indent_drift(source: str, lines: list[str]) -> list[dict]:
    """String literals that equal a verbatim line except for leading spaces."""
    wanted = _wanted(lines)
    found: list[dict] = []
    for number, text in enumerate(source.split("\n"), start=1):
        for m in _LITERAL.finditer(text):
            core = _core(m.group(2))
            key = core.strip()
            if key in wanted and _lead(core) != wanted[key]:
                found.append({"line": number, "text": key, "expected": wanted[key],
                              "found": _lead(core)})
    return found


def fix_indent_drift(source: str, lines: list[str]) -> tuple[str, int]:
    """Re-indent every drifted literal to the contract's indentation."""
    wanted = _wanted(lines)
    count = 0

    def repair(m: re.Match) -> str:
        nonlocal count
        quote, content = m.group(1), m.group(2)
        core = _core(content)
        key = core.strip()
        if key not in wanted or _lead(core) == wanted[key]:
            return m.group(0)
        count += 1
        return quote + " " * wanted[key] + content.lstrip(" ") + quote

    fixed = "\n".join(_LITERAL.sub(repair, text) for text in source.split("\n"))
    return fixed, count
