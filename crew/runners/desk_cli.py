"""The Review Desk for programs: what The Crew's control room calls to read and decide.

The control room (TheCrew, Rust/egui) shows the same queue as the Tk Review Desk. It does
not write queue.ini itself: every write goes through the functions in review_desk.py, so
there is one writer and the Desk's rules hold for both windows - approve needs no words,
the others do (review_rules.validate); a decision is stamped with the file's fingerprint;
a typed note is a draft until it becomes a decision; SEND hands over only what is ready.

Every command prints one JSON object on stdout. A note is read from stdin (UTF-8), so
quoting never mangles it.

    python crew/runners/desk_cli.py list
    python crew/runners/desk_cli.py decide ITEM_ID approve|reject|question|defer < note.txt
    python crew/runners/desk_cli.py undecide ITEM_ID
    python crew/runners/desk_cli.py draft ITEM_ID < note.txt     # blank text drops it
    python crew/runners/desk_cli.py send
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.reviewdesk import review_index, review_rules  # noqa: E402
from crew.runners import review_desk as rd  # noqa: E402


def _note() -> str:
    return sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()


def _find(items: list, item_id: str) -> dict | None:
    return next((i for i in items if i.get("item_id") == item_id), None)


def listing() -> dict:
    items = rd.load_queue()
    stamps = rd.load_sent()
    drafts = rd.load_drafts()
    out = []
    for item in items:
        out.append({**{k: item.get(k, "") for k in review_index.FIELDS},
                    "kind": rd.item_kind(item),
                    "complete": review_rules.is_complete(item) if item.get("decision") else False,
                    "changed": rd.changed_since_he_looked(item, stamps),
                    "next_action": review_rules.next_action(item),
                    "draft": (drafts.get(item.get("item_id")) or {}).get("note", "")})
    return {"ok": True, "queue": str(rd.queue_file()), "items": out,
            "summary": review_rules.summarize(items),
            "ready": len(rd.ready_to_send(items)),
            "next_steps": [[count, what] for count, what, _ in rd.next_steps(items)],
            "message": rd.handoff_message(items),
            "min_note_chars": review_rules.MIN_NOTE_CHARS}


def decide(item_id: str, decision: str, note: str) -> dict:
    """The Tk Desk's decide(), for one item, against the queue file as it is now."""
    items = rd.load_queue()
    item = _find(items, item_id)
    if item is None:
        return {"ok": False, "problem": f"{item_id} is not in the queue any more"}
    problems = review_rules.validate(decision, note)
    if problems:
        if decision not in review_rules.DECISIONS:
            problem = f"{decision!r} is not one of {review_rules.DECISIONS}"
        else:
            problem = (f"A {decision} needs a reason of at least "
                       f"{review_rules.MIN_NOTE_CHARS} characters - say what is wrong, or "
                       f"what you are asking. Only an approval needs no explanation.")
        return {"ok": False, "problem": problem}
    item.update(decision=decision, note=note, state="decided",
                decided_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    if decision == "approve" and rd.item_kind(item) == "read":
        item["state"] = "closed"               # seen: nothing to hand the agent
    rd.save_queue(items)
    rd.clear_draft(item_id)
    rd.stamp_decision(item)
    return {"ok": True, "item_id": item_id, "decision": decision,
            "next_action": review_rules.next_action(item), "ready": len(rd.ready_to_send(items))}


def undecide(item_id: str) -> dict:
    items = rd.load_queue()
    item = _find(items, item_id)
    if item is None:
        return {"ok": False, "problem": f"{item_id} is not in the queue any more"}
    note = item.get("note", "")
    item.update(decision="", state="pending", decided_at="")
    rd.save_queue(items)
    if note:
        rd.save_draft(item_id, note)          # the reason comes back as a draft, not lost
    return {"ok": True, "item_id": item_id}


def send() -> dict:
    items = rd.load_queue()
    if not rd.ready_to_send(items):
        return {"ok": False, "problem": "nothing new to send - every decision has been handed over"}
    handoff = rd.send_to_agent(items)
    return {"ok": True, "count": handoff["count"], "sent_at": handoff["sent_at"],
            "message": handoff["message"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    d = sub.add_parser("decide")
    d.add_argument("item_id")
    d.add_argument("decision")
    u = sub.add_parser("undecide")
    u.add_argument("item_id")
    r = sub.add_parser("draft")
    r.add_argument("item_id")
    sub.add_parser("send")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "list":
            result = listing()
        elif args.cmd == "decide":
            result = decide(args.item_id, args.decision, _note())
        elif args.cmd == "undecide":
            result = undecide(args.item_id)
        elif args.cmd == "draft":
            rd.save_draft(args.item_id, _note())
            result = {"ok": True, "item_id": args.item_id}
        else:
            result = send()
    except (OSError, ValueError, SystemExit) as exc:
        result = {"ok": False, "problem": str(exc)}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
