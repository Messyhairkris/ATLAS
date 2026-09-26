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


def commit_request(message: str) -> dict:
    staged = subprocess.run(["git", "diff", "--staged"], cwd=REPO, capture_output=True,
                            text=True, encoding="utf-8", errors="replace").stdout
    if not staged.strip():
        raise SystemExit("nothing is staged: git add the files first")
    stat = subprocess.run(["git", "diff", "--staged", "--stat"], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = rd.home() / "commits" / f"{stamp}-{_slug(message)}.diff"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"PROPOSED COMMIT: {message}\n\nApprove to let the PA commit exactly this;\n"
                   f"reject or question with a note to stop it.\n\n{stat}\n{staged}",
                   encoding="utf-8")
    return add(str(out), f"APPROVE COMMIT: {message}", item_id=f"commit:{stamp}")


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
    sub.add_parser("status")
    w = sub.add_parser("withdraw")
    w.add_argument("item_id")
    args = ap.parse_args()
    if args.cmd == "add":
        print(json.dumps(add(args.path, args.title), indent=1))
    elif args.cmd == "commit":
        print(json.dumps(commit_request(args.message), indent=1))
    elif args.cmd == "withdraw":
        print("withdrawn" if withdraw(args.item_id) else "not withdrawn (decided, or not a PA item)")
    else:
        print(json.dumps(status(), indent=1))
