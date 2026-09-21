"""Reference for quirk_tests.py: a forced failure placed inside a try block."""

import re

PY_FAIL = re.compile(r"\bassert\s+False\b")
JS_FAIL = re.compile(r"\bassert\s*\.\s*fail\s*\(")
_PY_TRY = re.compile(r"^(\s*)try\s*:")
_JS_TRY = re.compile(r"\btry\s*\{")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def python_fail_in_try(source: str) -> list[int]:
    """Lines with `assert False` whose nearest less-indented line is `try:`."""
    lines = source.split("\n")
    hits: list[int] = []
    for i, line in enumerate(lines):
        if not PY_FAIL.search(line) or line.lstrip().startswith("#"):
            continue
        depth = _indent(line)
        for above in reversed(lines[:i]):
            if not above.strip():
                continue
            if _indent(above) < depth:
                if _PY_TRY.match(above):
                    hits.append(i + 1)
                break
    return hits


def js_fail_in_try(source: str) -> list[int]:
    """Lines with `assert.fail(` inside the braces of a `try {` block."""
    hits: list[int] = []
    open_tries: list[int] = []      # brace depth at which each open try block began
    depth = 0
    for number, line in enumerate(source.split("\n"), start=1):
        i = 0
        while i < len(line):
            m = _JS_TRY.match(line, i)
            if m:
                depth += 1
                open_tries.append(depth)
                i = m.end()
                continue
            ch = line[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                if open_tries and open_tries[-1] == depth:
                    open_tries.pop()
                depth -= 1
            i += 1
        if JS_FAIL.search(line) and (open_tries or _inside_same_line_try(line)):
            hits.append(number)
    return hits


def _inside_same_line_try(line: str) -> bool:
    m = _JS_TRY.search(line)
    f = JS_FAIL.search(line)
    return bool(m and f and m.start() < f.start())


def fail_in_try(source: str, language: str) -> list[int]:
    """Dispatch on language: "python" or "javascript"; anything else is an error."""
    if language == "python":
        return python_fail_in_try(source)
    if language == "javascript":
        return js_fail_in_try(source)
    raise ValueError(f"unknown language: {language}")
