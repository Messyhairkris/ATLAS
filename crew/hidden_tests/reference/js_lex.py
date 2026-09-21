"""Split JavaScript source into code, comment, string, template and regex segments."""

import re

KINDS = ("code", "comment", "string", "template", "regex")
_REGEX_AFTER_CHARS = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_AFTER_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete",
                      "void", "throw", "case", "do", "else", "yield", "await"}
_LAST_WORD = re.compile(r"[A-Za-z_$][\w$]*\Z")


def _close(source: str, start: int, quote: str) -> int:
    i = start + 1
    while i < len(source):
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == quote:
            return i + 1
        i += 1
    return len(source)


def _regex_end(source: str, start: int) -> int:
    """End of a regex literal starting at start, or -1 if a newline comes first."""
    i, in_class = start + 1, False
    while i < len(source):
        ch = source[i]
        if ch == "\n":
            return -1
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            i += 1
            while i < len(source) and (source[i].isalpha()):
                i += 1
            return i
        i += 1
    return -1


def _regex_allowed(code_before: str) -> bool:
    text = code_before.rstrip()
    if not text:
        return True
    if text[-1] in _REGEX_AFTER_CHARS:
        return True
    m = _LAST_WORD.search(text)
    return bool(m) and m.group() in _REGEX_AFTER_WORDS


def segments(source: str) -> list[tuple[str, str]]:
    """Rules 1-6 of the contract, first match wins at each position."""
    out: list[tuple[str, str]] = []
    significant = ""
    i = 0
    while i < len(source):
        two = source[i:i + 2]
        if two == "//":
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            kind = "comment"
        elif two == "/*":
            end = source.find("*/", i + 2)
            end = len(source) if end < 0 else end + 2
            kind = "comment"
        elif source[i] in "'\"":
            end, kind = _close(source, i, source[i]), "string"
        elif source[i] == "`":
            end, kind = _close(source, i, "`"), "template"
        elif source[i] == "/" and _regex_allowed(significant) \
                and _regex_end(source, i) > 0:
            end, kind = _regex_end(source, i), "regex"
        else:
            end, kind = i + 1, "code"
        if kind == "code":
            significant += source[i:end]
        elif kind != "comment":
            significant += "x"
        if kind == "code" and out and out[-1][0] == "code":
            out[-1] = ("code", out[-1][1] + source[i:end])
        else:
            out.append((kind, source[i:end]))
        i = end
    return out


def code_only(source: str) -> str:
    """Comments become one space, strings '""', templates '``', regexes '/_/'."""
    swap = {"comment": " ", "string": '""', "template": "``", "regex": "/_/"}
    return "".join(swap.get(kind, text) for kind, text in segments(source))
