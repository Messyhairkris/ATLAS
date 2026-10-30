"""The Problems pane's runner: turn a build's own output into JSON rows for the window.

    python crew/runners/problems.py [--build DIR | --latest]

The parsing lives in crew/problems_lib.py, which is pure (the crew's airlock keeps it that way,
and it has no `open()`). This file is the impure half: it finds the build folder, reads its output,
and prints one JSON object:

    {"source": "<the file read>", "problems": [{"kind", "severity", "file", "line", "col",
                                                "code", "message"}]}

Read-only; nothing is written anywhere, and a bad folder prints an empty list rather than failing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # the harness root
if str(REPO / "crew") not in sys.path:
    sys.path.insert(0, str(REPO / "crew"))

try:
    import problems_lib as pl
except ImportError:                             # without the module there is nothing to parse
    pl = None

BUILDS = REPO / "runs" / "crew" / "pa" / "builds"

# What a build leaves behind that carries a check's own output, most useful first.
SOURCES = ("checks.txt", "round1.stderr.txt", "opencode.stderr.txt")

# Never a build folder, though it lives beside them.
SKIP = ("briefs",)


def latest_build(root: Path = BUILDS) -> Path | None:
    """The most recently written build folder, or None when there is none."""
    if not root.is_dir():
        return None
    dirs = [d for d in root.iterdir() if d.is_dir() and d.name not in SKIP]
    if not dirs:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime)


def read_output(build: Path) -> tuple[str, str]:
    """The first of SOURCES that exists, as text, with the path it came from."""
    for name in SOURCES:
        path = build / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace"), str(path)
    return "", str(build)


def problems_for(build: Path) -> dict:
    """{"source", "problems"} for one build folder; empty and quiet when there is nothing there."""
    if build is None or not build.is_dir():
        return {"source": "", "problems": []}
    text, source = read_output(build)
    return {"source": source, "problems": pl.parse(text) if pl else []}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", default="", help="a build folder; without it, the latest one")
    ap.add_argument("--latest", action="store_true", help="the most recently written build folder")
    a = ap.parse_args(argv)
    build = Path(a.build) if a.build else latest_build()
    print(json.dumps(problems_for(build)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
