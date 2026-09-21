"""quirk_indent.py - restoring a contract's indentation inside string literals.

Nemotron re-indents lines of a page template that the contract asked to be
reproduced byte for byte. This module finds those lines in the member's source
and puts the contract's leading spaces back, changing nothing else.
"""

import re

VERBATIM_TAGS = ("html", "text", "verbatim")
MIN_CHARS = 6

_PLACEHOLDER = re.compile(r"\{[^{}\s][^{}]*\}")
_LITERAL = re.compile(r"([\"'])((?:\\.|(?!\1).)*)\1")


def _key_of(line: str) -> str:
    """Return the text before the first placeholder, stripped."""
    match = _PLACEHOLDER.search(line)
    head = line[: match.start()] if match else line
    return head.strip()


def _leading_spaces(text: str) -> int:
    """Count the spaces before the first non-space character."""
    return len(text) - len(text.lstrip(" "))


def _key_map(lines: list[str]) -> dict[str, int]:
    """Map each verbatim key to the indent of its first occurrence."""
    key_map: dict[str, int] = {}
    for line in lines:
        key = _key_of(line)
        if len(key) < MIN_CHARS:
            continue
        if key not in key_map:
            key_map[key] = _leading_spaces(line)
    return key_map


def _split_core(contents: str) -> tuple[str, str]:
    """Split literal contents into core text and a trailing backslash-n."""
    if contents.endswith("\\n"):
        return contents[:-2], "\\n"
    return contents, ""


def verbatim_lines(contract: str) -> list[str]:
    """Collect the lines of every verbatim fenced block, distinct and in order."""
    result: list[str] = []
    seen: set[str] = set()
    lines = contract.split("\n")
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if not line.startswith("```"):
            index += 1
            continue
        info = line[3:].strip().lower()
        index += 1
        block: list[str] = []
        while index < total and not lines[index].startswith("```"):
            block.append(lines[index])
            index += 1
        if info in VERBATIM_TAGS:
            for block_line in block:
                if len(block_line.strip()) >= MIN_CHARS and block_line not in seen:
                    seen.add(block_line)
                    result.append(block_line)
        index += 1
    return result


def indent_drift(source: str, lines: list[str]) -> list[dict]:
    """Report every string literal whose indentation differs from its key."""
    key_map = _key_map(lines)
    findings: list[dict] = []
    for number, line in enumerate(source.split("\n"), 1):
        for match in _LITERAL.finditer(line):
            core, _ = _split_core(match.group(2))
            key = core.strip()
            if key not in key_map:
                continue
            found = _leading_spaces(core)
            expected = key_map[key]
            if found != expected:
                findings.append(
                    {
                        "line": number,
                        "text": key,
                        "expected": expected,
                        "found": found,
                    }
                )
    return findings


def fix_indent_drift(source: str, lines: list[str]) -> tuple[str, int]:
    """Rewrite drifting literals with the key's indent; return source and count."""
    key_map = _key_map(lines)
    count = 0

    def replace(match: re.Match) -> str:
        nonlocal count
        core, suffix = _split_core(match.group(2))
        key = core.strip()
        if key not in key_map:
            return match.group(0)
        found = _leading_spaces(core)
        expected = key_map[key]
        if found == expected:
            return match.group(0)
        count += 1
        quote = match.group(1)
        return quote + " " * expected + core[found:] + suffix + quote

    fixed_lines = [_LITERAL.sub(replace, line) for line in source.split("\n")]
    return "\n".join(fixed_lines), count
