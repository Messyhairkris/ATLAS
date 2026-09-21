"""Parse the TAP output of `node --test --test-reporter=tap`."""

import re

COUNT_KEYS = ("tests", "suites", "pass", "fail", "cancelled", "skipped", "todo")
_RESULT = re.compile(r"^( *)(not ok|ok) \d+(?: - (.*?))?(?: # (SKIP|TODO)\b.*)?$",
                     re.IGNORECASE)
_COUNT = re.compile(r"^# (\w+) ([\d.]+)$")


def parse_tap(text: str) -> dict:
    """Results in order, footer counts, and the duration in milliseconds."""
    tests: list[dict] = []
    counts: dict[str, int] = {}
    duration_ms = None
    for line in text.splitlines():
        m = _RESULT.match(line)
        if m:
            directive = (m.group(4) or "").upper()
            tests.append({"name": m.group(3) or "", "ok": m.group(2) == "ok",
                          "skip": directive == "SKIP", "todo": directive == "TODO",
                          "depth": len(m.group(1)) // 4})
            continue
        m = _COUNT.match(line)
        if m and m.group(1) in COUNT_KEYS:
            counts[m.group(1)] = int(m.group(2))
        elif m and m.group(1) == "duration_ms":
            duration_ms = float(m.group(2))
    return {"tests": tests, "counts": counts, "duration_ms": duration_ms}


def summary_line(result: dict) -> str:
    """A pytest-shaped totals line so the crew's totals gate works unchanged."""
    counts = result["counts"]
    parts = [f"{counts[key]} {word}" for key, word in
             (("fail", "failed"), ("pass", "passed"), ("skipped", "skipped"))
             if counts.get(key, 0)]
    seconds = (result["duration_ms"] or 0) / 1000
    return f"{', '.join(parts) or 'no tests ran'} in {seconds:.2f}s"
