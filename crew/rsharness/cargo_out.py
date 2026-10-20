"""Read what cargo and the Rust test runner print, and say it back briefly.

Two jobs: turn libtest output (one block per test binary) into counts, failing
names and their panic messages, with the same pytest-shaped totals line the other
harnesses write; and cut rustc's diagnostics down to the errors a member can act
on. Errors located in the hidden tests keep their message but lose the quoted
source lines, so the feedback says what is wrong without printing the tests.
"""

import re
from typing import Dict, List

RESULT = re.compile(r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored")
TEST_LINE = re.compile(r"^test (\S+) \.\.\. (ok|FAILED|ignored)\b")
FAIL_HEAD = re.compile(r"^---- (\S+) stdout ----$")
ERROR_HEAD = re.compile(r"^error(\[E\d{4}\])?: ")
LOCATION = re.compile(r"^\s*--> ([^:]+):(\d+):(\d+)")
SOURCE_LINE = re.compile(r"^\s*(\d+\s*)?\|")


def parse_libtest(text: str) -> Dict:
    tests, failures = [], {}
    counts = {"passed": 0, "failed": 0, "ignored": 0, "binaries": 0}
    current, buf = None, []
    for line in text.splitlines():
        m = TEST_LINE.match(line)
        if m:
            tests.append({"name": m.group(1), "outcome": m.group(2)})
            continue
        m = RESULT.match(line)
        if m:
            counts["binaries"] += 1
            counts["passed"] += int(m.group(2))
            counts["failed"] += int(m.group(3))
            counts["ignored"] += int(m.group(4))
            continue
        m = FAIL_HEAD.match(line)
        if m:
            if current:
                failures[current] = "\n".join(buf).strip()
            current, buf = m.group(1), []
            continue
        if current is not None:
            if line.strip() == "failures:":
                failures[current] = "\n".join(buf).strip()
                current, buf = None, []
            elif line.strip() and not line.startswith("note: run with"):
                buf.append(line)
    if current:
        failures[current] = "\n".join(buf).strip()
    return {"tests": tests, "counts": counts, "failures": failures}


def summary_line(result: Dict) -> str:
    c = result["counts"]
    parts = [f"{c[k]} {label}" for k, label in
             (("failed", "failed"), ("passed", "passed"), ("ignored", "skipped")) if c[k]]
    return ", ".join(parts) if parts else "no tests ran"


def summarize(result: Dict, limit: int = 12) -> str:
    """Failing tests with their panic messages, then the totals."""
    lines = []
    for name, message in list(result["failures"].items())[:limit]:
        msg = "\n    ".join(message.splitlines()[:8])
        lines.append(f"FAILED {name}\n    {msg}")
    failed = [t["name"] for t in result["tests"] if t["outcome"] == "FAILED"]
    for name in failed:
        if name not in result["failures"] and len(lines) < limit:
            lines.append(f"FAILED {name}")
    lines.append(summary_line(result))
    return "\n".join(lines)


def compile_errors(stderr: str, hidden_prefixes=("tests/", "tests\\"),
                   limit: int = 6) -> List[str]:
    """The first `limit` error blocks, each trimmed; hidden-test source not quoted."""
    blocks, cur = [], None
    for line in stderr.splitlines():
        if ERROR_HEAD.match(line) and not line.startswith(("error: could not compile",
                                                            "error: aborting due to")):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur is not None:
            if not line.strip() or line.startswith(("warning", "error: ")):
                blocks.append(cur)
                cur = None
            else:
                cur.append(line)
    if cur:
        blocks.append(cur)
    out = []
    for block in blocks[:limit]:
        loc = next((LOCATION.match(l) for l in block if LOCATION.match(l)), None)
        hidden = bool(loc) and loc.group(1).replace("\\", "/").startswith(
            tuple(p.replace("\\", "/") for p in hidden_prefixes))
        if hidden:
            kept = [block[0], f"  --> in the hidden tests (line {loc.group(2)}): they call "
                              f"your module exactly as the contract's API block shows"]
            kept += [l for l in block[1:] if l.strip().startswith(("= note", "= help"))]
        else:
            kept = [l for l in block if l.strip()][:18]
        out.append("\n".join(kept))
    return out


def warning_count(stderr: str) -> int:
    return sum(1 for l in stderr.splitlines() if l.startswith("warning:")
               and "generated" not in l)
