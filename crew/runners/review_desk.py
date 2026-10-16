"""The Review Desk: a window where Kris decides, and the agent finds out.

Kris asked for it: *"a small Program that ques items for review... a desktop
windows program that is small and has a link to open the file. I would love to be
able to review it directly through the interface as well, so that notes are direct
with the document or script I am looking at... Approval needs no explanation, but
rejections and questions do... indexed somehow maybe an ini? and would let the
Agent I am working with know reviews are available."*

All of the logic behind it was written by the Crew (see `crew/reviewdesk/`):

| module | what it decides | author |
|---|---|---|
| `review_rules.py` | whether a verdict is complete, and what the agent must do next | Nemotron |
| `review_index.py` | the INI a human can read in Notepad, and a merge that never overwrites a decision | Qwen |
| `review_anchors.py` | a note pinned to lines AND to a quote of them, so it survives the file changing | Hoss |

This window is Claude's, and it holds three rules it cannot bend:

* **Approve needs no words. Reject, question and defer need them** - the buttons
  refuse, with the reason from `review_rules.validate`.
* **A decision is never overwritten.** New items merge in; anything you decided
  stays decided, even if the file it points at changed.
* **The agent is told.** Every save rewrites `for_agent.json` with
  `review_rules.agent_digest`, so Claude or Crush can see what is waiting and what
  it has to do, without being asked.

    python crew/runners/review_desk.py            # everything awaiting review
    python crew/runners/review_desk.py --seed      # also pull fresh crew jobs in
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.reviewdesk import review_anchors, review_index, review_rules  # noqa: E402

ACCENT = "#FF9E3D"          # the desk's own colour; orange belongs to tests
BG = "#161A20"
PANEL = "#0E1116"
FG = "#E8EAED"
DIM = "#9AA4B2"
OK = "#5BD675"
BAD = "#FF6B6B"
WARN = "#FFC857"
DECISION_COLOUR = {"approve": OK, "reject": BAD, "question": WARN, "defer": DIM}

# Kris 2026-10-15: "the review desk is getting too loose with what needs approvals from me...
# The PA should know what I want and be able to approve all but the most important decisions
# without me. The PM is supposed to steer the overall direction, not be bogged down with every
# detail." Every item is one of three kinds, listed in this order under its own heading:
# DECIDE (his call), TRY (test it when he can), READ (nothing to decide; SEEN takes it off).
KINDS = ("decide", "try", "read")
KIND_HEAD = {"decide": "DECIDE - your call", "try": "TRY - when you can",
             "read": "READ - nothing to decide"}


def item_kind(item: dict) -> str:
    """The item's `kind`, else read from its title's first word (a "[project] " prefix is
    skipped). Anything unrecognised counts as a decision, so nothing important hides in READ."""
    if item.get("kind") in KINDS:
        return item["kind"]
    if item.get("item_id") == GUIDE_ID:
        return "read"
    title = re.sub(r"^\[[^\]]*\]\s*", "", item.get("title", "")).lower()
    if title.startswith(("try", "test", "task")):
        return "try"
    if title.startswith(("read", "fyi", "where everything")):
        return "read"
    return "decide"


_HOME_CACHE = {}


def home() -> Path:
    """Parsing the crew config on every call made each decision cost ~60 ms of
    path resolving (75 calls per 5 decisions, 2026-09-26). Cached per CREW_HOME."""
    key = os.environ.get("CREW_HOME", "")
    if key not in _HOME_CACHE:
        from crew.config import load_config
        _HOME_CACHE[key] = Path(load_config().state_home) / "review"
    return _HOME_CACHE[key]


def queue_file() -> Path:
    return home() / "queue.ini"


def digest_file() -> Path:
    return home() / "for_agent.json"


# The guide is an ordinary review item. Kris 2026-09-26: the Desk opened on a file he
# had already approved ("a bit confusing"), and feedback about the Desk should use
# the Desk's own notation - so reviewing the guide IS the practice, and its notes,
# anchors and decisions are the feedback. When the PA revises the guide in answer,
# it comes back marked [new], which shows the whole loop working.
GUIDE_ID = "desk:guide"
GUIDE_FILE = Path(__file__).resolve().parents[1] / "reviewdesk" / "DESK_GUIDE.txt"


# Kris 2026-10-12: items name files "you know the location, but I do not". Any file
# path or web link in the reading pane opens with a click. A path in backticks may
# hold spaces; a bare one ends at the first space. A path is a link only if it exists.
LINK = re.compile(r"`([A-Za-z]:\\[^`\n]+|https?://[^`\s]+)`"
                  r"|(https?://[^\s<>\"'`)\]]+|[A-Za-z]:\\[^\s`'\"<>|*?]+)")


def links_in(line: str) -> list:
    """-> [(start, end, target)] for each openable path or web link in `line`."""
    out = []
    for m in LINK.finditer(line):
        g = 1 if m.group(1) else 2
        target = m.group(g).rstrip(".,;:")
        if target.startswith(("http://", "https://")) or Path(target).exists():
            out.append((m.start(g), m.start(g) + len(target), target))
    return out


def ensure_guide(items: list) -> list:
    if GUIDE_FILE.is_file() and not any(i["item_id"] == GUIDE_ID for i in items):
        items = review_index.merge(items, [review_index.new_item(
            item_id=GUIDE_ID, title="HOW TO USE THE REVIEW DESK - practise here, tell us "
            "what to improve", path=str(GUIDE_FILE), origin="Review Desk")])
    return items


# -- the queue -------------------------------------------------------------------

def load_queue() -> list:
    path = queue_file()
    if not path.is_file():
        return []
    try:
        return review_index.parse(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{path} is not readable: {exc}\n"
                         f"Fix it in Notepad or delete it; nothing else touches it.")


def save_queue(items: list) -> None:
    path = queue_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(review_index.render(items), encoding="utf-8")
    os.replace(tmp, path)
    write_digest(items)


def write_digest(items: list) -> dict:
    """What the agent reads. Written on every save, so nobody has to ask."""
    digest = review_rules.agent_digest(items)
    digest["summary"] = review_rules.summarize(items)
    digest["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    digest["queue"] = str(queue_file())
    digest["notes"] = {item["item_id"]: item.get("note", "")
                       for item in items if item.get("note")}
    digest["decisions"] = {item["item_id"]: item.get("decision", "")
                           for item in items if item.get("decision")}
    digest["anchors"] = {item["item_id"]: item.get("anchor", "")
                         for item in items if item.get("anchor")}
    path = digest_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(digest, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return digest


def sent_file() -> Path:
    return home() / "sent.json"


def handoff_file() -> Path:
    return home() / "handoff.json"


def load_sent() -> dict:
    path = sent_file()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fingerprint(path) -> str:
    """A short hash of the file as it stands, so a later change is noticeable."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()[:16]


def ready_to_send(items: list) -> list:
    """Decisions the agent has not been handed yet.

    A defer is deliberately not here: Kris said defer means not now, and the
    rules module says "leave it queued", so it never wakes anybody.
    """
    return [item for item in items
            if item.get("decision") in ("approve", "reject", "question")
            and review_rules.is_complete(item)
            and item.get("state") != "closed"
            and item_kind(item) != "read"]               # seen is not a decision


def stamp_decision(item: dict) -> dict:
    """Remember what the file looked like when he decided about it.

    Taken at the decision, not at the handoff, so a file that changes while it
    waits to be sent is noticed too - and so his approval is always attached to a
    version that can be identified.
    """
    stamps = load_sent()
    record = dict(stamps.get(item.get("item_id")) or {})
    record.update(decided=item.get("decision", ""),
                  decided_at=item.get("decided_at", ""),
                  fingerprint=fingerprint(item.get("path", "")))
    stamps[item["item_id"]] = record
    write_sent(stamps)
    return record


def write_sent(stamps: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    tmp = sent_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(stamps, indent=2), encoding="utf-8")
    os.replace(tmp, sent_file())


def changed_since_he_looked(item: dict, stamps: dict | None = None) -> bool:
    """True when the file has changed since he decided about it, or sent it.

    Either way the item is worth another look, and the desk colours it. His
    decision itself is never touched - that is his to change.
    """
    record = (stamps if stamps is not None else load_sent()).get(item.get("item_id"))
    if not record or not record.get("fingerprint"):
        return False
    return fingerprint(item.get("path", "")) != record["fingerprint"]


def next_steps(items: list) -> list:
    """What happens next, in words, for a batch about to be sent.

    Kris: "I would like a Complete modal pop up when everything has been completed
    and instructions on next steps the user should take to keep the project moving
    forward."  So this says what the agent will do AND what he has to do, which is
    usually nothing.
    """
    batch = ready_to_send(items)
    by = {"approve": [], "reject": [], "question": []}
    for item in batch:
        by[item["decision"]].append(item["title"])
    lines = []
    if by["approve"]:
        lines.append((f"{len(by['approve'])} approved", "the agent applies the work "
                      "as it stands, and these leave your list", OK))
    if by["reject"]:
        lines.append((f"{len(by['reject'])} rejected", "the agent revises each one "
                      "using your note, then sends it back here", BAD))
    if by["question"]:
        lines.append((f"{len(by['question'])} questions", "the agent answers, then "
                      "asks you again - these stay on your list", WARN))
    deferred = [i for i in items if i.get("decision") == "defer"]
    if deferred:
        lines.append((f"{len(deferred)} deferred", "nobody is told; they stay "
                      "yours until you decide", DIM))
    waiting = review_rules.summarize(items)["pending"]
    if waiting:
        lines.append((f"{waiting} still undecided", "they are not part of this "
                      "handoff; send again when you have decided them", DIM))
    return lines


def handoff_message(items: list) -> str:
    """One sentence he can paste to any agent - Claude, Crush, or the next one."""
    counts = review_rules.summarize(items)
    return (f"Review Desk: {counts['approve']} approved, {counts['reject']} "
            f"rejected, {counts['question']} questions. Read "
            f"{digest_file()} and act on the actions map.")


def send_to_agent(items: list) -> dict:
    """Hand the decided items over, once, on purpose.

    for_agent.json is still written on every save - nothing is ever lost by not
    pressing the button. This is the part Kris asked for: a moment where he says
    "go", and gets told it happened.
    """
    batch = ready_to_send(items)
    sent = load_sent()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    records = []
    for item in batch:
        item["state"] = "closed"
        sent[item["item_id"]] = {
            **(sent.get(item["item_id"]) or {}),
            "at": stamp,
            "decision": item["decision"],
            "fingerprint": fingerprint(item.get("path", "")),
        }
        records.append({"item_id": item["item_id"], "title": item["title"],
                        "path": item.get("path", ""), "decision": item["decision"],
                        "note": item.get("note", ""),
                        "anchor": item.get("anchor", ""),
                        "action": review_rules.next_action(item)})
    handoff = {"sent_at": stamp, "count": len(records), "items": records,
               "message": handoff_message(items), "digest": str(digest_file())}
    home().mkdir(parents=True, exist_ok=True)
    tmp = handoff_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    os.replace(tmp, handoff_file())
    write_sent(sent)
    tab, newline = chr(9), chr(10)
    with (home() / "handoff.log").open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(tab.join((stamp, record["decision"], record["item_id"],
                               record["action"])) + newline)
    save_queue(items)
    return handoff


def settings_file() -> Path:
    return home() / "desk.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(values: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    settings_file().write_text(json.dumps(values, indent=2), encoding="utf-8")


# Kris 2026-10-13: a long note on a test card was lost when the Desk crashed before it
# was sent - "it should autosave but not auto commit my data". A note is saved as it is
# typed, to drafts.json and never to the queue, and comes back when its item is opened
# again, even after a crash. Nothing reaches the agent until a decision is made and sent.
def drafts_file() -> Path:
    return home() / "drafts.json"


def load_drafts() -> dict:
    try:
        data = json.loads(drafts_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_draft(item_id: str, text: str, saved_at: str | None = None) -> dict:
    """Keep `text` as the unsent note for `item_id` (blank text removes it)."""
    drafts = load_drafts()
    if text.strip():
        drafts[item_id] = {"note": text,
                           "saved_at": saved_at or time.strftime("%Y-%m-%dT%H:%M:%S")}
    else:
        drafts.pop(item_id, None)
    home().mkdir(parents=True, exist_ok=True)
    tmp = drafts_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(drafts, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, drafts_file())
    return drafts


def clear_draft(item_id: str) -> dict:
    """The note went into a decision, so its draft is done with."""
    drafts = load_drafts()
    return save_draft(item_id, "") if item_id in drafts else drafts


def crew_items() -> list:
    """Everything the crew has staged for review, as queue records.

    One item per output FILE, because that is what a human reads and what a note
    should attach to.
    """
    from crew.core import Crew
    crew = Crew()
    out = []
    for brief in crew.inbox()["needs_review"]:
        job_id = brief["task_id"]
        jdir = crew.store.job_dir(job_id)
        files = (crew.store.load(job_id).get("result") or {}).get("files") or []
        for rel in files:
            path = jdir / "output" / rel
            if not path.is_file():
                continue
            out.append(review_index.new_item(
                item_id=f"{job_id}:{rel}",
                title=f"{rel} - {brief['title']}"[:110],
                path=str(path),
                origin=f"crew:{brief['task_type']}:{brief['assigned_to']}"))
    return out


def seed(extra_paths=()) -> list:
    """Merge fresh crew work, and anything named on the command line, into the
    queue. A decision already made is never disturbed."""
    items = load_queue()
    # Kris 2026-10-15: the PA checks and closes crew output itself (`crew review <job> approve
    # --by Claude`); it reaches the Desk only when the PA queues it as a card, or when the
    # setting crew_outputs_on_desk is turned on.
    incoming = crew_items() if load_settings().get("crew_outputs_on_desk") else []
    for raw in extra_paths:
        path = Path(raw).resolve()
        if path.is_file():
            incoming.append(review_index.new_item(
                item_id=f"file:{path.name}", title=path.name, path=str(path),
                origin="named by hand"))
    merged = review_index.merge(items, incoming)
    save_queue(merged)
    return merged


def reconcile(disk: list, mine: list, touched: set) -> list:
    """The queue as it should be saved by an open Desk: the file's current items,
    with the Desk's own version only of items it changed this session.

    2026-09-26: the Desk loaded the queue once and saved its whole copy on every
    decision or SEND, so an item the PA queued (or withdrew) while it was open was
    silently undone. Items the Desk never touched now always come from the file; an
    item that left the file stays gone unless Kris decided it here."""
    own = {i["item_id"]: i for i in mine if i["item_id"] in touched}
    merged = [own.pop(i["item_id"], i) for i in disk]
    return merged + list(own.values())


def queue_mtime() -> float:
    try:
        return queue_file().stat().st_mtime
    except OSError:
        return 0.0


# -- the window ------------------------------------------------------------------

class Desk:
    def __init__(self, items: list):
        import tkinter as tk
        from tkinter import font as tkfont

        self.tk = tk
        self.items = items
        self.current = None
        self.file_text = ""
        self.visible = []                 # positions in the list -> self.items
        self.sent = load_sent()
        self.settings = load_settings()
        self.scale = int(self.settings.get("font_scale", 0))
        self.offered = None                # the batch the modal has already offered
        self.touched = set()               # item ids this Desk changed (see reconcile)
        self.drafts = load_drafts()        # unsent notes, saved as they are typed
        self.draft_job = None
        self.seen_mtime = queue_mtime()
        self.root = tk.Tk()
        self.root.title("Review Desk")
        self.root.configure(bg=BG)
        self.root.geometry("1180x820")
        self.fonts = {"code": tkfont.Font(family="Consolas", size=10),
                      "body": tkfont.Font(family="Segoe UI", size=10),
                      "list": tkfont.Font(family="Segoe UI", size=9)}
        self._build()
        self.apply_scale(0)
        self.refresh_list()
        self.show_guide(add=False)         # never open on a finished item
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if self.drafts:
            self.say(f"{len(self.drafts)} unsent note(s) kept from last time - "
                     f"marked [draft] in the list", ACCENT)
        self.root.after(4000, self.poll_disk)

    # -- keeping in step with the queue file ----------------------------------------
    def sync(self, *changed) -> None:
        """Merge with the file before writing; changed = item ids just edited here."""
        self.touched.update(changed)
        current_id = (self.items[self.current]["item_id"]
                      if self.current is not None and self.current < len(self.items) else None)
        before = [i["item_id"] for i in self.items]
        self.items[:] = reconcile(load_queue(), self.items, self.touched)
        ids = [i["item_id"] for i in self.items]
        self.current = ids.index(current_id) if current_id in ids else None
        if ids != before:
            self.refresh_list()
            self.reselect()

    def save(self, *changed) -> None:
        self.sync(*changed)
        save_queue(self.items)
        self.seen_mtime = queue_mtime()

    def poll_disk(self) -> None:
        """New items the PA queues while the Desk is open appear without a restart."""
        try:
            if queue_mtime() != self.seen_mtime:
                n = len(self.items)
                self.sync()
                self.seen_mtime = queue_mtime()
                self.refresh_list()
                self.reselect()
                if len(self.items) > n:
                    self.say(f"{len(self.items) - n} new item(s) arrived", ACCENT)
        finally:
            self.root.after(4000, self.poll_disk)

    # -- widgets -----------------------------------------------------------------
    def _label(self, parent, text, **kw):
        opts = {"bg": BG, "fg": FG, "font": ("Segoe UI", 10)}
        opts.update(kw)
        return self.tk.Label(parent, text=text, **opts)

    def _button(self, parent, text, cmd, colour=None, big=False):
        b = self.tk.Button(parent, text=text, command=cmd, relief="flat",
                           bg=colour or "#22303C",
                           fg="#101318" if colour else FG,
                           activebackground=colour or "#2E4152",
                           font=("Segoe UI", 11, "bold") if big
                           else ("Segoe UI", 9),
                           padx=12 if big else 8, pady=6 if big else 2)
        b.pack(side="left", padx=(0, 6))
        return b

    def _build(self):
        head = self.tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=10, pady=(10, 4))
        self._label(head, "Review Desk", font=("Segoe UI", 15, "bold"),
                    fg=ACCENT).pack(side="left")
        self.counts = self._label(head, "", fg=DIM)
        self.counts.pack(side="left", padx=14)
        self._button(head, "how to use the Desk", self.show_guide)
        self._button(head, "refresh from the crew", self.do_seed)
        self._button(head, "open the index", lambda: self.open_path(queue_file()))
        self._button(head, "A-", lambda: self.apply_scale(-1))
        self._button(head, "A+", lambda: self.apply_scale(+1))
        self._label(head, "(or Ctrl + wheel)", fg=DIM,
                    font=("Segoe UI", 8)).pack(side="left")
        self.finished = self.tk.BooleanVar(value=False)
        self.tk.Checkbutton(
            head, text="show what I have finished", variable=self.finished,
            command=self.refresh_list, bg=BG, fg=DIM, selectcolor=PANEL,
            activebackground=BG, activeforeground=FG, relief="flat",
            font=("Segoe UI", 8), highlightthickness=0).pack(side="right")

        body = self.tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=4)

        left = self.tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        self._label(left, "waiting for you", fg=DIM).pack(anchor="w")
        self.listbox = self.tk.Listbox(left, width=44, height=28, bg=PANEL, fg=FG,
                                       selectbackground=ACCENT,
                                       selectforeground="#101318",
                                       font=self.fonts["list"], relief="flat",
                                       activestyle="none")
        self.listbox.pack(fill="y", expand=True, pady=(2, 0))
        self.listbox.bind("<<ListboxSelect>>",
                          lambda _e: self.select_at(self.listbox.curselection()[0]
                                                    if self.listbox.curselection()
                                                    else None))

        right = self.tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.title_label = self._label(right, "nothing selected",
                                       font=("Segoe UI", 11, "bold"))
        self.title_label.pack(anchor="w")
        self.origin_label = self._label(right, "", fg=DIM, font=("Consolas", 8))
        self.origin_label.pack(anchor="w")

        tools = self.tk.Frame(right, bg=BG)
        tools.pack(fill="x", pady=(6, 2))
        self._button(tools, "open the file", self.open_current)
        self._button(tools, "attach my note to the selected lines", self.attach)
        self._button(tools, "clear the anchor", self.clear_anchor)
        self.anchor_label = self._label(tools, "", fg=DIM, font=("Consolas", 9))
        self.anchor_label.pack(side="left", padx=8)

        self.viewer = self.tk.Text(right, bg=PANEL, fg=FG, insertbackground=FG,
                                   font=self.fonts["code"], relief="flat",
                                   wrap="none", height=22)
        self.viewer.pack(fill="both", expand=True)
        self.viewer.tag_config("anchored", background="#2A3340")

        self.note_label = self._label(right, "", fg=DIM)
        self.note_label.pack(anchor="w", pady=(8, 0))
        self.note = self.tk.Text(right, bg=PANEL, fg=FG, insertbackground=FG,
                                 font=self.fonts["body"], relief="flat", height=4,
                                 wrap="word")
        self.note.pack(fill="x")
        self.note.bind("<<Modified>>", self.on_note_change)
        self.draft_label = self._label(right, "", fg=DIM, font=("Segoe UI", 8))
        self.draft_label.pack(anchor="w")

        buttons = self.tk.Frame(right, bg=BG)
        buttons.pack(fill="x", pady=8)
        self.approve_button = self._button(buttons, "APPROVE", lambda: self.decide("approve"),
                                           OK, True)
        self._button(buttons, "REJECT", lambda: self.decide("reject"), BAD, True)
        self._button(buttons, "QUESTION", lambda: self.decide("question"), WARN, True)
        self._button(buttons, "DEFER", lambda: self.decide("defer"), None, True)
        self._button(buttons, "clear my decision", self.undecide)
        self.send_button = self._button(buttons, "SEND TO THE AGENT",
                                       self.offer_handoff, ACCENT, True)

        self.status = self._label(self.root, "ready", fg=OK)
        self.status.pack(anchor="w", padx=10, pady=(0, 10))

        self.root.bind_all("<Control-MouseWheel>", self.on_wheel)
        self.root.bind_all("<Control-plus>", lambda _e: self.apply_scale(+1))
        self.root.bind_all("<Control-minus>", lambda _e: self.apply_scale(-1))

    # -- reading it ---------------------------------------------------------------
    def apply_scale(self, step: int) -> None:
        """Kris: "My eyes are bad, can we make the windows font dynamic using the
        scroll wheel?"  The file, the index and the note box grow together, and the
        size is remembered for next time."""
        self.scale = max(-3, min(14, self.scale + step))
        for key, base in (("code", 10), ("body", 10), ("list", 9)):
            self.fonts[key].configure(size=base + self.scale)
        if self.settings.get("font_scale") != self.scale:   # not on every launch
            self.settings["font_scale"] = self.scale
            save_settings(self.settings)
        if step:
            self.say(f"font {10 + self.scale} point "
                     f"({self.scale:+d}) - Ctrl + wheel, or A- / A+", DIM)

    def on_wheel(self, event) -> str:
        self.apply_scale(1 if event.delta > 0 else -1)
        return "break"          # do not scroll as well as resize

    # -- state -------------------------------------------------------------------
    def say(self, text: str, colour=FG) -> None:
        self.status.config(text=text, fg=colour)
        self.root.update_idletasks()

    def refresh_list(self) -> None:
        """What is on your plate. Approved work that has been sent drops off -
        Kris: "Any approved items would be removed from the list and used, while
        the ones with questions would remain with a color change showing when they
        have been updated for a new review"."""
        self.listbox.delete(0, "end")
        self.visible = []
        show_all = bool(getattr(self, "finished", None) and self.finished.get())
        rows = {kind: [] for kind in KINDS}
        for index, item in enumerate(self.items):
            decision = item.get("decision") or ""
            done = item.get("state") == "closed"
            touched = changed_since_he_looked(item, self.sent)
            if done and decision == "approve" and not touched and not show_all:
                continue                        # applied; off your plate
            mark = {"approve": "[ok] ", "reject": "[no] ",
                    "question": "[?]  ", "defer": "[...] "}.get(decision, "     ")
            if decision and not review_rules.is_complete(item):
                mark = "[!]  "
            if item["item_id"] in self.drafts:
                mark = "[draft] "               # a note typed here and not yet sent
            if touched:
                mark = "[new] "
            colour = ACCENT if touched else DECISION_COLOUR.get(decision, FG)
            rows[item_kind(item)].append((index, mark + item["title"],
                                          colour if (decision or touched) else None))
        # A heading row per kind; headings map to no item, so they can't be picked.
        for kind in KINDS:
            if not rows[kind]:
                continue
            self.visible.append(None)
            self.listbox.insert("end", f"--- {KIND_HEAD[kind]} ({len(rows[kind])}) ---")
            self.listbox.itemconfig("end", foreground=DIM)
            for index, text, colour in rows[kind]:
                self.visible.append(index)
                self.listbox.insert("end", text)
                if colour:
                    self.listbox.itemconfig("end", foreground=colour)
        waiting = [i for i in self.items if not i.get("decision") and i.get("state") != "closed"]
        by_kind = {kind: sum(1 for i in waiting if item_kind(i) == kind) for kind in KINDS}
        counts = review_rules.summarize(self.items)
        digest = review_rules.agent_digest(self.items)
        self.counts.config(
            text=f"{by_kind['decide']} decisions for you, {by_kind['try']} to try, "
                 f"{by_kind['read']} to read - "
                 f"{counts['approve']} approved, {counts['reject']} rejected, "
                 f"{counts['question']} questions, {counts['defer']} deferred"
                 + (f", {counts['incomplete']} need a reason"
                    if counts["incomplete"] else "")
                 + (f" | {len(ready_to_send(self.items))} ready to send"
                    if ready_to_send(self.items) else "")
                 + (f" | {len(digest['waiting_on_agent'])} with the agent"
                    if digest["waiting_on_agent"] else ""))
        if hasattr(self, "send_button"):
            waiting = len(ready_to_send(self.items))
            self.send_button.config(
                text=f"SEND {waiting} TO THE AGENT" if waiting
                else "NOTHING TO SEND",
                state="normal" if waiting else "disabled")

    def reselect(self) -> None:
        """Keep the same item highlighted after the list is rebuilt."""
        self.listbox.selection_clear(0, "end")
        if self.current in self.visible:
            self.listbox.selection_set(self.visible.index(self.current))

    def select_at(self, position) -> None:
        """The list can hide finished work, so a row is not an item number."""
        if position is None or not (0 <= position < len(self.visible)):
            return
        self.select(self.visible[position])

    def show_guide(self, add: bool = True) -> None:
        """Select the guide item (adding it if the queue lacks it and add is set)."""
        if add and not any(i["item_id"] == GUIDE_ID for i in self.items):
            self.items[:] = ensure_guide(self.items)
            if any(i["item_id"] == GUIDE_ID for i in self.items):
                self.save(GUIDE_ID)
                self.refresh_list()
        ids = [i["item_id"] for i in self.items]
        if GUIDE_ID in ids:
            self.select(ids.index(GUIDE_ID))
            self.reselect()
        else:
            self.current = None
            self.title_label.config(text="pick an item on the left")

    def select(self, index) -> None:
        if index is None or not (0 <= index < len(self.items)):
            return
        self.flush_draft()                 # keep what was typed on the item being left
        self.note_label.config(text="your note - required for reject, question and defer"
                               + ("  (on this guide: your feedback about the Desk)"
                                  if self.items[index]["item_id"] == GUIDE_ID else ""))
        self.current = index
        item = self.items[index]
        if hasattr(self, "approve_button"):
            self.approve_button.config(text="SEEN" if item_kind(item) == "read" else "APPROVE")
        self.title_label.config(text=item["title"])
        self.origin_label.config(text=f"{item.get('origin', '')}   {item['path']}")
        self.note.delete("1.0", "end")
        draft = self.drafts.get(item["item_id"])
        if draft and draft.get("note", "").strip() != item.get("note", "").strip():
            self.note.insert("1.0", draft["note"])
            self.draft_label.config(
                text=f"your unsent note, kept from {draft.get('saved_at', '?').replace('T', ' ')}"
                     f" - press a decision to send it", fg=ACCENT)
        else:
            self.note.insert("1.0", item.get("note", ""))
            self.draft_label.config(text="", fg=DIM)
        self.note.edit_modified(False)
        self.load_file(item)
        self.say(f"{review_rules.next_action(item)}", DIM)

    # -- drafts: saved as typed, never sent until a decision ------------------------
    def note_text(self) -> str:
        return self.note.get("1.0", "end-1c")

    def on_note_change(self, _event=None) -> None:
        """Typing (or pasting) schedules a save a moment later."""
        if not self.note.edit_modified():
            return
        self.note.edit_modified(False)
        if self.draft_job is not None:
            self.root.after_cancel(self.draft_job)
        self.draft_job = self.root.after(700, self.flush_draft)

    def flush_draft(self) -> None:
        """Save the note box as the current item's draft, unless it says just what the
        item already holds. Never touches the queue or what the agent reads."""
        if self.draft_job is not None:
            self.root.after_cancel(self.draft_job)
            self.draft_job = None
        if self.current is None or self.current >= len(self.items):
            return
        item_id = self.items[self.current]["item_id"]
        text = self.note_text()
        had = item_id in self.drafts
        try:
            if text.strip() == self.items[self.current].get("note", "").strip():
                self.drafts = clear_draft(item_id)
                self.draft_label.config(text="", fg=DIM)
            else:
                self.drafts = save_draft(item_id, text)
                self.draft_label.config(
                    text=f"draft saved {time.strftime('%H:%M:%S')} - not sent until "
                         f"you press a decision", fg=DIM)
        except OSError as exc:
            self.draft_label.config(text=f"could not save the draft: {exc}", fg=BAD)
            return
        if had != (item_id in self.drafts):
            self.refresh_list()
            self.reselect()

    def close(self) -> None:
        self.flush_draft()
        self.root.destroy()

    def load_file(self, item) -> None:
        self.viewer.delete("1.0", "end")
        path = Path(item["path"])
        try:
            self.file_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.file_text = ""
            self.viewer.insert("end", f"cannot read {path}: {exc}")
            self.anchor_label.config(text="", fg=DIM)
            return
        width = len(str(len(self.file_text.splitlines()))) or 1
        self.links = 0
        for number, line in enumerate(self.file_text.splitlines(), 1):
            prefix = f"{number:>{width}}: "
            self.viewer.insert("end", f"{prefix}{line}\n")
            for start, end, target in links_in(line):
                at = len(prefix)
                self.link(f"{number}.{at + start}", f"{number}.{at + end}", target)
        self.show_anchor(item)

    def link(self, start: str, end: str, target: str) -> None:
        """A clickable file path or web link in the pane (see LINK)."""
        tag, view = f"link{self.links}", self.viewer
        self.links += 1
        view.tag_add(tag, start, end)
        view.tag_config(tag, foreground=ACCENT, underline=True)
        view.tag_bind(tag, "<Button-1>", lambda _e, t=target: self.open_target(t))
        view.tag_bind(tag, "<Enter>", lambda _e: view.config(cursor="hand2"))
        view.tag_bind(tag, "<Leave>", lambda _e: view.config(cursor="xterm"))

    def open_target(self, target: str) -> None:
        if target.startswith(("http://", "https://")):
            import webbrowser
            webbrowser.open(target)
            self.say(f"opened {target[:60]}", DIM)
        else:
            self.open_path(Path(target))

    def show_anchor(self, item) -> None:
        label = item.get("anchor") or ""
        self.viewer.tag_remove("anchored", "1.0", "end")
        if not label:
            self.anchor_label.config(text="no note anchor", fg=DIM)
            return
        try:
            anchor = review_anchors.parse_anchor(label)
        except ValueError:
            self.anchor_label.config(text=f"anchor {label!r} is unreadable", fg=BAD)
            return
        # Has the file moved under the note? relocate() answers honestly.
        full = dict(anchor)
        lines = self.file_text.split("\n")
        first, last = anchor["first_line"], anchor["last_line"]
        if 1 <= first <= last <= len(lines):
            full["quote"] = "\n".join(lines[first - 1:last])
        else:
            full["quote"] = ""
        moved = review_anchors.relocate(
            {**full, "digest": anchor["digest"]}, self.file_text)
        status = moved["status"]
        shown_first = moved["first_line"]
        shown_last = moved["last_line"]
        colours = {"unchanged": OK, "moved": WARN, "ambiguous": WARN, "stale": BAD}
        words = {"unchanged": "still the same lines",
                 "moved": f"moved {moved['moved_by']:+d} lines",
                 "ambiguous": "appears more than once - a human must decide",
                 "stale": "STALE: those lines have changed"}
        self.anchor_label.config(
            text=f"{label}  ({words.get(status, status)})",
            fg=colours.get(status, DIM))
        self.viewer.tag_add("anchored", f"{shown_first}.0", f"{shown_last + 1}.0")

    # -- actions -----------------------------------------------------------------
    def selected_lines(self):
        try:
            start = int(self.viewer.index("sel.first").split(".")[0])
            end = int(self.viewer.index("sel.last").split(".")[0])
            return start, end
        except Exception:                                   # noqa: BLE001
            return None

    def attach(self) -> None:
        if self.current is None:
            return
        span = self.selected_lines()
        if not span:
            self.say("select the lines in the file first, then attach", WARN)
            return
        try:
            anchor = review_anchors.make_anchor(self.file_text, span[0], span[1])
        except ValueError as exc:
            self.say(f"cannot anchor there: {exc}", BAD)
            return
        item = self.items[self.current]
        item["anchor"] = review_anchors.format_anchor(anchor)
        self.save(item["item_id"])
        self.show_anchor(item)
        excerpt = review_anchors.excerpt(self.file_text, anchor)
        self.say(f"note anchored to lines {span[0]}-{span[1]}: "
                 f"{excerpt.splitlines()[0][:60]}...", OK)

    def clear_anchor(self) -> None:
        if self.current is None:
            return
        self.items[self.current]["anchor"] = ""
        self.save(self.items[self.current]["item_id"])
        self.show_anchor(self.items[self.current])
        self.say("anchor cleared", DIM)

    def decide(self, decision: str) -> None:
        if self.current is None:
            self.say("nothing selected", WARN)
            return
        item = self.items[self.current]
        note = self.note.get("1.0", "end").strip()
        problems = review_rules.validate(decision, note)
        if problems:
            # Kris's rule, enforced by the crew's own module: approval needs no
            # explanation, the others do. The module answers in one word ("note"),
            # which is true and useless to a person, so the desk says it properly.
            # (The contract asked only for a problem "mentioning note" - too weak a
            # specification, and the module is within its rights.)
            self.say(self.explain(decision, problems), BAD)
            self.note.focus_set()
            return
        item.update(decision=decision, note=note, state="decided",
                    decided_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        if decision == "approve" and item_kind(item) == "read":
            item["state"] = "closed"           # seen: nothing to hand the agent
        self.save(item["item_id"])
        self.forget_draft(item["item_id"])     # the note is in the decision now
        stamp_decision(item)
        self.sent = load_sent()
        self.refresh_list()
        self.reselect()
        self.say(f"{decision}: {review_rules.next_action(item)} "
                 f"- press SEND when you are ready", OK)
        self.maybe_offer()

    # -- handing it over -----------------------------------------------------------
    def maybe_offer(self) -> None:
        """When the last item is decided, say so - unprompted, once per batch."""
        batch = ready_to_send(self.items)
        if not batch or review_rules.summarize(self.items)["pending"]:
            return
        signature = tuple(sorted(item["item_id"] for item in batch))
        if signature == self.offered:
            return
        self.offered = signature
        self.offer_handoff(complete=True)

    def offer_handoff(self, complete: bool = False) -> None:
        batch = ready_to_send(self.items)
        if not batch:
            self.say("nothing new to send - every decision has been handed over",
                     DIM)
            return
        self.modal(batch, complete)

    def modal(self, batch: list, complete: bool) -> None:
        tk = self.tk
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Ready to hand over")
        win.transient(self.root)
        win.geometry("620x440")
        win.grab_set()

        head = ("Everything is reviewed." if complete
                else f"{len(batch)} decision(s) ready.")
        tk.Label(win, text=head, bg=BG, fg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16,
                                                     pady=(16, 2))
        tk.Label(win, text="What happens when you send:", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        for count, what, colour in next_steps(self.items):
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=16, pady=1)
            tk.Label(row, text=count, bg=BG, fg=colour, width=16, anchor="w",
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            tk.Label(row, text=what, bg=BG, fg=FG, anchor="w", justify="left",
                     wraplength=420, font=("Segoe UI", 9)).pack(side="left")

        tk.Label(win, text="Then, on your side:", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(12, 0))
        yours = tk.Label(
            win, bg=BG, fg=FG, justify="left", wraplength=560,
            font=("Segoe UI", 9),
            text="Nothing, if an agent is already working with you: it reads "
                 "for_agent.json at the start of its turn.\nIf you want it picked "
                 "up right now, press copy and paste the line into the chat - it "
                 "works for Claude or for Crush.\nApproved work leaves this list. "
                 "Anything you rejected or asked about comes back here in orange "
                 "when the file has been touched.")
        yours.pack(anchor="w", padx=16)

        status = tk.Label(win, text="", bg=BG, fg=OK, font=("Segoe UI", 9))
        status.pack(anchor="w", padx=16, pady=(10, 0))

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=16, pady=14)

        def do_send():
            self.sync()                        # never send over a newer queue file
            self.touched.update(i["item_id"] for i in ready_to_send(self.items))
            handoff = send_to_agent(self.items)
            self.seen_mtime = queue_mtime()
            self.sent = load_sent()
            self.refresh_list()
            self.reselect()
            status.config(
                text=f"sent {handoff['count']} item(s) at "
                     f"{handoff['sent_at'][11:]} - written to handoff.json, "
                     f"for_agent.json and handoff.log",
                fg=OK)
            send.config(text="sent", state="disabled")
            self.say(f"handed {handoff['count']} item(s) to the agent at "
                     f"{handoff['sent_at'][11:]}", OK)

        def copy_line():
            self.root.clipboard_clear()
            self.root.clipboard_append(handoff_message(self.items))
            status.config(text="copied - paste it to any agent", fg=ACCENT)

        send = tk.Button(row, text=f"SEND {len(batch)} TO THE AGENT",
                         command=do_send, relief="flat", bg=ACCENT, fg="#101318",
                         font=("Segoe UI", 11, "bold"), padx=14, pady=6)
        send.pack(side="left")
        tk.Button(row, text="copy the message", command=copy_line, relief="flat",
                  bg="#22303C", fg=FG, font=("Segoe UI", 9), padx=10,
                  pady=4).pack(side="left", padx=8)
        # Kris 2026-09-26: the pop-up should also close the whole Desk
        tk.Button(row, text="close the Review Desk", command=self.close,
                  relief="flat", bg="#22303C", fg=FG, font=("Segoe UI", 9), padx=10,
                  pady=4).pack(side="right")
        tk.Button(row, text="close this", command=win.destroy, relief="flat",
                  bg="#22303C", fg=FG, font=("Segoe UI", 9), padx=10,
                  pady=4).pack(side="right", padx=8)
        self.modal_window = win

    @staticmethod
    def explain(decision: str, problems: list) -> str:
        """Turn the rule module's terse verdict into something a person can act
        on, without pretending the rule came from anywhere else."""
        joined = " ".join(str(p).lower() for p in problems)
        if "note" in joined:
            return (f"A {decision} needs a reason of at least "
                    f"{review_rules.MIN_NOTE_CHARS} characters - say what is "
                    f"wrong, or what you are asking. Only an approval needs no "
                    f"explanation.")
        if "decision" in joined:
            return f"{decision!r} is not one of {review_rules.DECISIONS}."
        return " | ".join(str(p) for p in problems)

    def undecide(self) -> None:
        if self.current is None:
            return
        item = self.items[self.current]
        item.update(decision="", note=self.note.get("1.0", "end").strip(),
                    state="pending", decided_at="")
        self.save(item["item_id"])
        self.forget_draft(item["item_id"])
        self.refresh_list()
        self.reselect()
        self.offered = None
        self.say("decision cleared; it is waiting for you again", DIM)

    def forget_draft(self, item_id: str) -> None:
        if self.draft_job is not None:
            self.root.after_cancel(self.draft_job)
            self.draft_job = None
        try:
            self.drafts = clear_draft(item_id)
        except OSError:
            pass                                # an orphan draft is harmless
        self.draft_label.config(text="", fg=DIM)

    def do_seed(self) -> None:
        self.items[:] = reconcile(ensure_guide(seed()), self.items, self.touched)
        self.sent = load_sent()
        self.refresh_list()
        self.say(f"{len(self.items)} item(s) in the queue", OK)

    def open_current(self) -> None:
        if self.current is None:
            return
        self.open_path(Path(self.items[self.current]["path"]))

    def open_path(self, path: Path) -> None:
        try:
            os.startfile(str(path))                         # noqa: S606
            self.say(f"opened {path.name}", DIM)
        except Exception as exc:                            # noqa: BLE001
            try:
                subprocess.Popen(["notepad.exe", str(path)])
                self.say(f"opened {path.name} in Notepad", DIM)
            except Exception:                               # noqa: BLE001
                self.say(f"could not open {path}: {exc}", BAD)

    def run(self) -> None:
        self.root.mainloop()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true",
                    help="pull anything the crew has staged for review into the queue")
    ap.add_argument("--file", action="append", default=[],
                    help="also queue this file by hand, repeatable")
    ap.add_argument("--digest", action="store_true",
                    help="print what the agent would read, and exit")
    args = ap.parse_args(argv)

    items = seed(args.file) if (args.seed or args.file) else load_queue()
    if not any(i["item_id"] == GUIDE_ID for i in items):
        items = ensure_guide(items)
        save_queue(items)
    if args.digest:
        print(json.dumps(write_digest(items), indent=2))
        return 0
    if not items:
        print("nothing is waiting for review. Pull the crew's work in with:\n"
              "    python crew/runners/review_desk.py --seed")
        return 0
    Desk(items).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
