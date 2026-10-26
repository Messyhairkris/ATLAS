"""Git status for The Crew's Changes pane (Kris, 2026-10-24) - read-only.

The Crew window is Rust; it runs this and reads the JSON. Every repository
gets `git status --porcelain=v2 --branch` and `git diff --numstat HEAD`;
the parsing lives in crew/gitstatus.py so this file only runs git and shapes
JSON. Nothing here may write to a repository, ever: status, diff and
rev-parse are the only git commands it calls, every call with capture_output
and a 20 s timeout.

    python crew/runners/changes.py                          # every project, as JSON
    python crew/runners/changes.py --repo PATH ...          # only these
    python crew/runners/changes.py --diff FILE --repo PATH  # one file's diff as text
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew import gitstatus  # noqa: E402
from crew.config import load_config  # noqa: E402

DEFAULT_PROJECTS = [
    Path("C:/Users/user/ATLAS-api-harness"),
    Path("C:/Users/user/TheCrew"),
]

GIT_TIMEOUT = 20


def _norm(path) -> str:
    """For comparison and dedupe: case-insensitive, '/' separators."""
    return str(path).replace("\\", "/").rstrip("/").lower()


def _git(repo: Path, *args: str) -> str:
    """One read-only git call; raises RuntimeError on a non-zero exit,
    subprocess.TimeoutExpired after GIT_TIMEOUT seconds."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        timeout=GIT_TIMEOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or f"git {args[0]} exited {result.returncode}"
        )
    return result.stdout


def is_repo_top(path: Path) -> bool:
    """True when `path` is the top of a git repository, never deeper."""
    try:
        top = _git(path, "rev-parse", "--show-toplevel").strip()
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return False
    return _norm(top) == _norm(path)


def projects(repos) -> list:
    """The project list: the explicit --repo paths if given, else the default
    projects plus every read_roots entry of crew/config.json that is the top
    of a git repository. No duplicates."""
    if repos:
        candidates = [Path(r) for r in repos]
    else:
        candidates = list(DEFAULT_PROJECTS)
        try:
            roots = load_config().read_roots
        except (OSError, ValueError):
            roots = []
        candidates += [p for p in roots if is_repo_top(p)]
    out, seen = [], set()
    for p in candidates:
        key = _norm(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def repo_report(path: Path) -> dict:
    """One repository's entry: branch, upstream, ahead/behind, summary and the
    files (each with "added"/"deleted" from numstat, or null). A repo that
    fails - not a repo, a git error, a timeout - gets {"name", "path",
    "error"} and the others still print."""
    report = {"name": path.name, "path": str(path)}
    try:
        status = gitstatus.parse_status(
            _git(path, "status", "--porcelain=v2", "--branch")
        )
        numstat = {}
        if status["oid"] != "(initial)":  # no commits yet: no HEAD to diff
            numstat = gitstatus.parse_numstat(_git(path, "diff", "--numstat", "HEAD"))
        files = []
        for f in status["files"]:
            counts = numstat.get(f["path"]) or numstat.get(f["orig"])
            files.append(
                {
                    **f,
                    "added": counts[0] if counts else None,
                    "deleted": counts[1] if counts else None,
                }
            )
        report.update(
            {
                "branch": status["branch"],
                "upstream": status["upstream"],
                "ahead": status["ahead"],
                "behind": status["behind"],
                "summary": gitstatus.summary(status),
                "files": files,
            }
        )
    except subprocess.TimeoutExpired:
        report["error"] = f"git timed out after {GIT_TIMEOUT} s"
    except (RuntimeError, OSError) as exc:
        report["error"] = str(exc)
    return report


def collect(paths) -> dict:
    """{"repos": [...]} for the given project paths."""
    return {"repos": [repo_report(Path(p)) for p in paths]}


def file_diff(repo: Path, filename: str) -> str:
    """`git diff HEAD -- FILE`, or a note when the file is not in git yet."""
    status = gitstatus.parse_status(_git(repo, "status", "--porcelain=v2", "--branch"))
    wanted = filename.replace("\\", "/")
    for f in status["files"]:
        if f["kind"] == "untracked" and f["path"] == wanted:
            return "(untracked: not in git yet)"
    return _git(repo, "diff", "HEAD", "--", filename)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Git status for The Crew's Changes pane (read-only)."
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        metavar="PATH",
        help="only these repositories (repeatable)",
    )
    parser.add_argument(
        "--diff",
        metavar="FILE",
        help="print one file's diff as plain text (needs --repo)",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.diff:
        if not args.repo:
            parser.error("--diff needs --repo PATH")
        try:
            sys.stdout.write(file_diff(Path(args.repo[0]), args.diff))
        except subprocess.TimeoutExpired:
            print(f"git timed out after {GIT_TIMEOUT} s", file=sys.stderr)
            return 1
        except (RuntimeError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    print(json.dumps(collect(projects(args.repo)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
