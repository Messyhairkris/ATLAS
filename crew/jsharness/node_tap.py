"""Turns `node --test --test-reporter=tap` output into data and produces a
pytest-shaped totals line, so the crew's existing "quote the totals
verbatim" gate works on JavaScript runs unchanged.
"""

import re

COUNT_KEYS = ("tests", "suites", "pass", "fail", "cancelled", "skipped", "todo")

_RESULT_RE = re.compile(
    r"^(?P<indent> *)(?P<not>not )?ok (?P<num>\d+)"
    r"(?: - (?P<name>.*?))?"
    r"(?: # (?P<directive>(?i:SKIP|TODO))\b.*)?$"
)

_COUNT_RE = re.compile(r"^# (?P<key>\w+) (?P<number>\d+(?:\.\d+)?)$")


def parse_tap(text: str) -> dict:
    """Parse TAP text into tests, counts and duration_ms.

    Each line is judged on its own, in order. A result line appends a dict
    to `tests`; a count line fills `counts` (only keys that appeared) or
    `duration_ms`. Lines matching neither rule are ignored.
    """
    tests: list[dict] = []
    counts: dict[str, int] = {}
    duration_ms: float | None = None

    for line in text.splitlines():
        result = _RESULT_RE.match(line)
        if result is not None:
            directive = (result.group("directive") or "").upper()
            tests.append(
                {
                    "name": result.group("name") or "",
                    "ok": result.group("not") is None,
                    "skip": directive == "SKIP",
                    "todo": directive == "TODO",
                    "depth": len(result.group("indent")) // 4,
                }
            )
            continue

        count = _COUNT_RE.match(line)
        if count is None:
            continue
        key = count.group("key")
        number = count.group("number")
        if key == "duration_ms":
            duration_ms = float(number)
        elif key in COUNT_KEYS:
            counts[key] = int(number)

    return {"tests": tests, "counts": counts, "duration_ms": duration_ms}


def summary_line(result: dict) -> str:
    """Build the pytest-shaped totals line from a parse_tap result.

    Non-zero fail, pass and skipped are written as `N failed`, `N passed`,
    `N skipped` in that order (all zero means `no tests ran`), then
    ` in S.SSs` where S is duration_ms / 1000 to two decimals.
    """
    counts = result["counts"]
    parts = []
    for key, label in (
        ("fail", "failed"),
        ("pass", "passed"),
        ("skipped", "skipped"),
    ):
        value = counts.get(key, 0)
        if value:
            parts.append(f"{value} {label}")
    text = ", ".join(parts) if parts else "no tests ran"
    duration = result.get("duration_ms") or 0
    return f"{text} in {duration / 1000:.2f}s"
