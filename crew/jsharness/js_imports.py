"""js_imports.py - Determine import specifiers and forbidden globals in JavaScript.

The implementation relies on the accepted `js_lex` module for accurate handling of
comments, strings, and template literals. No re-implementation of lexical rules
is performed here.
"""

from __future__ import annotations

import re

from js_lex import code_only, segments

FORBIDDEN_GLOBALS = (
    "eval",
    "Function",
    "process",
    "require",
    "fetch",
    "XMLHttpRequest",
    "WebSocket",
    "Worker",
    "globalThis",
    "window",
    "document",
)


def _is_import_specifier(code: str) -> bool:
    """Return ``True`` if *code* (trailing whitespace stripped) ends with a
    recognised import trigger.

    The trigger must be a whole word not preceded by an identifier character
    (letter, digit, ``_``, ``$`` or ``.``).  The supported forms are:

    * ``from``
    * ``import``
    * ``import`` followed by optional whitespace and ``(``
    * ``require`` followed by optional whitespace and ``(``
    """
    # ``code`` already has trailing whitespace removed by the caller.
    patterns = (
        r"(?<![A-Za-z0-9_$\.])from\b",
        r"(?<![A-Za-z0-9_$\.])import\b",
        r"(?<![A-Za-z0-9_$\.])import\s*\(",
        r"(?<![A-Za-z0-9_$\.])require\s*\(",
    )
    return any(re.search(p, code) for p in patterns)


def imports(source: str) -> list[str]:
    """Return a list of import specifiers found in *source*.

    The function walks the segments produced by :func:`js_lex.segments`,
    completely ignoring comment segments.  When a *string* segment follows code
    (ignoring comments) that ends with one of the import triggers, the string
    literal (without its surrounding quotes) is recorded as a specifier.
    Duplicates are preserved and the order matches appearance in the source.
    """
    specifiers: list[str] = []
    code_buffer = ""

    for kind, text in segments(source):
        if kind == "code":
            code_buffer += text
        elif kind == "string":
            # Determine if the preceding code makes this string a specifier.
            trimmed = code_buffer.rstrip()
            if _is_import_specifier(trimmed):
                # Strip the surrounding quote characters; escapes are left intact.
                specifiers.append(text[1:-1])
            # Reset buffer - a string (or template) breaks the code continuity.
            code_buffer = ""
        elif kind == "template":
            # Templates never act as specifiers; they also break continuity.
            code_buffer = ""
        # ``comment`` segments are ignored; they do not affect ``code_buffer``.

    return specifiers


def check_imports(source: str, allowed: set[str]) -> list[str]:
    """Return a sorted list of import specifiers from *source* that are not in
    *allowed*.

    Each offending specifier appears only once, regardless of how many times it
    occurs in the source.
    """
    offending = {imp for imp in imports(source) if imp not in allowed}
    return sorted(offending)


def forbidden_uses(source: str) -> list[str]:
    """Return a sorted list of forbidden global identifiers used in *source*.

    The analysis is performed on the output of :func:`js_lex.code_only`,
    which removes comments, strings and templates.  An identifier is reported
    only if it appears as a bare name (not as a property access).  The nearest
    non-whitespace character before the identifier must not be a dot ``.``.
    """
    code = code_only(source)
    pattern = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
    found: set[str] = set()

    for match in pattern.finditer(code):
        name = match.group(0)
        if name not in FORBIDDEN_GLOBALS:
            continue

        # Look backwards for the nearest non-whitespace character.
        idx = match.start() - 1
        while idx >= 0 and code[idx].isspace():
            idx -= 1
        if idx >= 0 and code[idx] == ".":
            continue  # property access, not a forbidden global use.

        found.add(name)

    return sorted(found)
