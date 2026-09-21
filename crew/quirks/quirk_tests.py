"""Zero-token checks for test assertions that cannot fail reliably.

Putting ``assert False`` (Python) or ``assert.fail(...)`` (JavaScript) inside a
``try`` block is a habit for proving that an exception is raised. Under
``python -O`` the assert disappears, and in both languages a broad
``except``/``catch`` can swallow the failure itself, so the test can pass
without having proven anything. House style forbids the pattern; these checks
scan source text and report the line numbers where it appears.
"""

import re

_ASSERT_FALSE = re.compile(r"\bassert\s+False\b")
_PYTHON_TRY = re.compile(r"try\s*:")
_ASSERT_FAIL = re.compile(r"\bassert\s*\.\s*fail\s*\(")
_JS_TRY = re.compile(r"\btry\s*\{")


def python_fail_in_try(source: str) -> list[int]:
    """Report lines whose ``assert False`` hangs from a ``try:`` body.

    The nearest less-indented line above the assert (walking upward, skipping
    blank lines) must be the ``try:`` itself, so an assert inside ``except`` or
    ``else``, at module level, or nested under an ``if`` inside the try is not
    reported.
    """
    lines = source.split("\n")
    results: list[int] = []
    for lineno, line in enumerate(lines, 1):
        if not _ASSERT_FALSE.search(line) or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        nearest = _nearest_less_indented(lines, lineno - 2, indent)
        if nearest is not None and _PYTHON_TRY.match(nearest.lstrip()):
            results.append(lineno)
    return results


def js_fail_in_try(source: str) -> list[int]:
    """Report lines whose ``assert.fail(`` sits inside the braces of a ``try {``.

    Brace depth persists across lines: ``try {`` records its depth as an open
    try and the ``}`` that closes that depth ends it. A line is checked after
    its own characters are processed, so a one-line
    ``try { ... assert.fail(...); }`` is also reported when the ``try {`` comes
    first on the line. Braces inside strings or comments are not special-cased.
    """
    results: list[int] = []
    depth = 0
    open_tries: set[int] = set()
    for lineno, line in enumerate(source.split("\n"), 1):
        fail = _ASSERT_FAIL.search(line)
        opener = _JS_TRY.search(line)
        index = 0
        while index < len(line):
            opened = _JS_TRY.match(line, index)
            if opened:
                depth += 1
                open_tries.add(depth)
                index = opened.end()
            elif line[index] == "{":
                depth += 1
                index += 1
            elif line[index] == "}":
                depth -= 1
                open_tries.discard(depth + 1)
                index += 1
            else:
                index += 1
        if fail and (open_tries or (opener and opener.start() < fail.start())):
            results.append(lineno)
    return results


def fail_in_try(source: str, language: str) -> list[int]:
    """Run the check for ``language``.

    ``language`` must be ``"python"`` or ``"javascript"``; anything else raises
    ``ValueError`` naming the language.
    """
    if language == "python":
        return python_fail_in_try(source)
    if language == "javascript":
        return js_fail_in_try(source)
    raise ValueError(f"unsupported language: {language}")


def _nearest_less_indented(lines: list[str], start: int, indent: int) -> str | None:
    """Walk upward from ``start`` to the first non-blank line indented less than
    ``indent``; return it, or ``None`` when no such line exists."""
    for index in range(start, -1, -1):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip(" ")) < indent:
            return line
    return None
