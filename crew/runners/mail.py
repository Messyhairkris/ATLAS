"""Vault mail for PAs: the command line over CrossTalk Local Mail (Cross_talk/tools/mail/mail_lib.py).

Kris 2026-10-27: handoffs between PAs must be repeatable. A handoff is a mail thread in the
Obsidian vault (wiki/agents/mail): messages are immutable, hashed files in a thread folder, and
each participant gets a pointer in its own inbox, so a reply lands back in the sender's inbox.
Addresses are the participants view (wiki/agents/mail/participants.md); an unknown one fails.

    python crew/runners/mail.py inbox gordon
    python crew/runners/mail.py read <thread>
    python crew/runners/mail.py send --from claude-code --to gordon --subject "..." --body-file f.md
    python crew/runners/mail.py reply <thread> --from gordon --body "..."
    python crew/runners/mail.py archive gordon <thread>

A body passed with --body must not contain '>': the chat shell treats it as a redirection and
asks (or refuses in plan mode). Longer replies go in a file and use --body-file.
"""
import argparse
import os
import sys
from pathlib import Path

MAIL_LIB = Path(os.environ.get("MAIL_LIB", "C:/Users/user/Cross_talk/tools/mail"))
sys.path.insert(0, str(MAIL_LIB))
import mail_lib  # noqa: E402

CHANNEL = "direct_disk"


def _body(a) -> str:
    if a.body_file:
        return Path(a.body_file).read_text(encoding="utf-8")
    if a.body:
        return a.body.replace("\\n", "\n")
    sys.exit("give --body or --body-file")


def inbox(vault: Path, slug: str) -> list[dict]:
    """Newest last: thread, subject, who wrote last, when, and how many messages."""
    out = []
    for thread in mail_lib.read_inbox(vault, slug):
        msgs = mail_lib.thread_messages(vault, thread)
        if not msgs:
            continue
        last = msgs[-1][0]
        out.append({"thread": thread, "subject": msgs[0][0].get("subject"),
                    "last_from": last.get("from"), "last_ts": last.get("ts"),
                    "messages": len(msgs)})
    return sorted(out, key=lambda r: r["last_ts"] or "")


def send(vault: Path, sender: str, to: list, subject: str, body: str) -> tuple:
    thread = f"t-{mail_lib.ts_ms()}-{sender}"
    return thread, mail_lib.deliver(vault, thread, sender, to, subject, body, channel=CHANNEL)


def reply(vault: Path, thread: str, sender: str, body: str) -> str:
    """To everyone else on the thread, in reply to its newest message."""
    msgs = mail_lib.thread_messages(vault, thread)
    if not msgs:
        raise SystemExit(f"no such thread: {thread}")
    parent = msgs[-1][0]
    to = [p for p in mail_lib.participants_of(vault, thread) if p != sender]
    subject = parent.get("subject") or ""
    subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    return mail_lib.deliver(vault, thread, sender, to, subject, body,
                            parent=parent.get("id"), channel=CHANNEL)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", type=Path, default=mail_lib.DEFAULT_VAULT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inbox"); p.add_argument("slug")
    p = sub.add_parser("read"); p.add_argument("thread")
    for name in ("send", "reply"):
        p = sub.add_parser(name)
        if name == "reply":
            p.add_argument("thread")
        p.add_argument("--from", dest="sender", required=True)
        if name == "send":
            p.add_argument("--to", required=True, help="comma-separated slugs")
            p.add_argument("--subject", required=True)
        p.add_argument("--body"); p.add_argument("--body-file")
    p = sub.add_parser("archive"); p.add_argument("slug"); p.add_argument("thread")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "inbox":
            rows = inbox(a.vault, a.slug)
            for r in rows:
                print(f"{r['thread']}  [{r['messages']}] last from {r['last_from']} {r['last_ts']}\n"
                      f"    {r['subject']}")
            print(f"{len(rows)} thread(s) in {a.slug}'s inbox")
        elif a.cmd == "read":
            folder = mail_lib._thread_dir(a.vault, a.thread)
            for fm, body in mail_lib.thread_messages(a.vault, a.thread):
                ok = mail_lib.verify_message(folder / f"{fm['id']}.md")
                print(f"=== {fm['id']}  from {fm.get('from')} to {', '.join(fm.get('to') or [])}"
                      f"  {fm.get('ts')}  {'hash ok' if ok else 'HASH MISMATCH'}\n"
                      f"Subject: {fm.get('subject')}\n\n{body.strip()}\n")
        elif a.cmd == "send":
            to = [s.strip() for s in a.to.split(",") if s.strip()]
            thread, mid = send(a.vault, a.sender, to, a.subject, _body(a))
            print(f"sent {mid} in {thread}")
        elif a.cmd == "reply":
            print(f"sent {reply(a.vault, a.thread, a.sender, _body(a))} in {a.thread}")
        elif a.cmd == "archive":
            print("archived" if mail_lib.archive(a.vault, a.slug, a.thread) else "not found")
    except mail_lib.UnknownParticipant as e:
        print(f"not an active participant: {e.args[0]} (wiki/agents/mail/participants.md)",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
