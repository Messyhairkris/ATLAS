"""Reference implementation of contracts/ahk_lex.md (never given to the crew)."""


def _mask_line(line: str, in_string: bool = False) -> tuple:
    """(masked line, whether a string was still open at the end)."""
    out = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if in_string:
            if ch == "`" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    out.append("  ")
                    i += 2
                    continue
                out.append('"')
                in_string = False
                i += 1
                continue
            out.append(" ")
            i += 1
            continue
        if ch == "`" and i + 1 < n:
            out.append(line[i:i + 2])
            i += 2
            continue
        if ch == '"':
            out.append('"')
            in_string = True
            i += 1
            continue
        if ch == ";" and (i == 0 or line[:i].strip() == "" or line[i - 1] in " \t"):
            out.append(" " * (n - i))
            break
        out.append(ch)
        i += 1
    return "".join(out), in_string


def mask(source: str) -> str:
    """The source with comments blanked and string contents blanked, same shape."""
    lines = source.split("\n")
    out = []
    in_block = False
    for raw in lines:
        line = raw[:-1] if raw.endswith("\r") else raw
        tail = "\r" if raw.endswith("\r") else ""
        stripped = line.lstrip()
        if in_block:
            out.append(" " * len(line) + tail)
            if stripped.startswith("*/"):
                in_block = False
            continue
        if stripped.startswith("/*"):
            in_block = True
            out.append(" " * len(line) + tail)
            continue
        masked, _open = _mask_line(line)
        out.append(masked + tail)
    return "\n".join(out)


def unterminated(source: str) -> list:
    """1-based numbers of lines where a string was opened and never closed."""
    bad = []
    in_block = False
    for number, raw in enumerate(source.split("\n"), 1):
        stripped = raw.lstrip()
        if in_block:
            if stripped.startswith("*/"):
                in_block = False
            continue
        if stripped.startswith("/*"):
            in_block = True
            continue
        _masked, still_open = _mask_line(raw.rstrip("\r"))
        if still_open:
            bad.append(number)
    return bad


def code_lines(source: str) -> list:
    """(line number, masked text) for every line that still has code on it."""
    return [(number, text.rstrip("\r"))
            for number, text in enumerate(mask(source).split("\n"), 1)
            if text.strip()]
