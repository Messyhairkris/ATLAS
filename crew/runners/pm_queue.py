"""The PA's side of the Review Desk: put things in front of Kris, read his answer.

Kris, 2026-09-26: use the overlay "to facilitate our checking of files and
approving steps, commits as needed" - actions he completes should be simple and
list-like. The Review Desk queue is the one place items wait for him; this adds
PA items to it (never disturbing a decision already made - review_index.merge)
and reads his decisions back.

    python pm_queue.py add PATH --title "Check the contract wording"
    python pm_queue.py commit "Crew: add fsm_desk"     # the staged diff, for approval
    python pm_queue.py status                           # what he has decided

A commit request writes the staged diff (with message, file list and stats) to
runs/crew/review/commits/*.diff and queues it as "APPROVE COMMIT: <message>".
The PA commits only after the item says approve; reject/question notes come back
through the Desk's for_agent.json and handoff.json as usual.
"""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from crew.reviewdesk import review_index  # noqa: E402
from crew.runners import review_desk as rd  # noqa: E402


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "item"


def add(path: str, title: str, origin: str = "PA:Claude", item_id: str = None) -> dict:
    p = Path(path).resolve()
    if not p.is_file():
        raise SystemExit(f"{p} is not a file")
    item = review_index.new_item(item_id=item_id or f"pa:{p.name}", title=title[:110],
                                 path=str(p), origin=origin)
    rd.save_queue(review_index.merge(rd.load_queue(), [item]))
    return item


# The checks every commit request passes before it reaches Kris (2026-09-26: a
# shadowed `import os` reached the Desk twice). Serious pyflakes classes only:
# syntax errors, undefined names, used-before-assignment - not style.
PYTHON = r"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe"
LINT_SELECT = "E9,F63,F7,F82"
TESTS = ["tests/test_crew.py"]


def _staged_files() -> list:
    out = subprocess.run(["git", "diff", "--staged", "--name-only", "--diff-filter=ACMR"],
                         cwd=REPO, capture_output=True, text=True).stdout
    return [f for f in out.splitlines() if f.strip()]


def run_checks(files: list) -> list:
    """-> [(name, ok, detail)] for the staged files. The tests run against the
    working tree, so a staged file that also has unstaged edits is reported."""
    results = []
    py = [f for f in files if f.endswith(".py") and (REPO / f).is_file()]
    if py:
        r = subprocess.run(["ruff", "check", "--select", LINT_SELECT, "--output-format",
                            "concise", *py], cwd=REPO, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        results.append(("lint", r.returncode == 0,
                        f"{len(py)} file(s) clean" if r.returncode == 0
                        else (r.stdout + r.stderr).strip()[-2000:]))
    if any(f.startswith(("crew/", "tests/")) for f in files):
        r = subprocess.run([PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", *TESTS],
                           cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1200)
        tail = (r.stdout + r.stderr).strip().splitlines()
        results.append(("tests", r.returncode == 0,
                        tail[-1] if r.returncode == 0 else "\n".join(tail[-25:])))
    dirty = subprocess.run(["git", "diff", "--name-only"], cwd=REPO, capture_output=True,
                           text=True).stdout.split()
    both = sorted(set(dirty) & set(files))
    if both:
        results.append(("unstaged edits", False, "these staged files also have unstaged "
                        "changes, so the checks did not see exactly the commit: "
                        + ", ".join(both)))
    return results


def commit_request(message: str, force: bool = False) -> dict:
    staged = subprocess.run(["git", "diff", "--staged"], cwd=REPO, capture_output=True,
                            text=True, encoding="utf-8", errors="replace").stdout
    if not staged.strip():
        raise SystemExit("nothing is staged: git add the files first")
    checks = run_checks(_staged_files())
    failed = [c for c in checks if not c[1]]
    report = "\n".join(f"  {'PASS' if ok else 'FAIL'} {name}: {detail}"
                        for name, ok, detail in checks) or "  (nothing to check)"
    if failed and not force:
        raise SystemExit("NOT queued - the checks failed:\n" + report)
    stat = subprocess.run(["git", "diff", "--staged", "--stat"], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = rd.home() / "commits" / f"{stamp}-{_slug(message)}.diff"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"PROPOSED COMMIT: {message}\n\nApprove to let the PA commit exactly this;\n"
                   f"reject or question with a note to stop it.\n\n"
                   f"CHECKS (run before this reached you):\n{report}\n\n{stat}\n{staged}",
                   encoding="utf-8")
    title = ("[CHECKS FAILED] " if failed else "") + f"APPROVE COMMIT: {message}"
    return add(str(out), title, item_id=f"commit:{stamp}")


def withdraw(item_id: str) -> bool:
    """Take back a PA item Kris has not decided yet (e.g. a commit request whose
    diff changed). A decided item is never removed."""
    items = rd.load_queue()
    keep = [i for i in items if not (i.get("item_id") == item_id and not i.get("decision")
                                     and str(i.get("origin", "")).startswith("PA:"))]
    if len(keep) == len(items):
        return False
    rd.save_queue(keep)
    return True


def status() -> list:
    return [{k: i.get(k) for k in ("item_id", "title", "decision", "note", "state")}
            for i in rd.load_queue() if str(i.get("origin", "")).startswith("PA:")]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("path")
    a.add_argument("--title", required=True)
    c = sub.add_parser("commit")
    c.add_argument("message")
    c.add_argument("--force", action="store_true",
                   help="queue even if checks fail (the title says so)")
    sub.add_parser("status")
    w = sub.add_parser("withdraw")
    w.add_argument("item_id")
    args = ap.parse_args()
    if args.cmd == "add":
        print(json.dumps(add(args.path, args.title), indent=1))
    elif args.cmd == "commit":
        print(json.dumps(commit_request(args.message, args.force), indent=1))
    elif args.cmd == "withdraw":
        print("withdrawn" if withdraw(args.item_id) else "not withdrawn (decided, or not a PA item)")
    else:
        print(json.dumps(status(), indent=1))
