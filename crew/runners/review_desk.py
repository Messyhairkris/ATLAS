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
import json
import os
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


def home() -> Path:
    from crew.config import load_config
    return Path(load_config().state_home) / "review"


def queue_file() -> Path:
    return home() / "queue.ini"


def digest_file() -> Path:
    return home() / "for_agent.json"


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
    incoming = crew_items()
    for raw in extra_paths:
        path = Path(raw).resolve()
        if path.is_file():
            incoming.append(review_index.new_item(
                item_id=f"file:{path.name}", title=path.name, path=str(path),
                origin="named by hand"))
    merged = review_index.merge(items, incoming)
    save_queue(merged)
    return merged


# -- the window ------------------------------------------------------------------

class Desk:
    def __init__(self, items: list):
        import tkinter as tk

        self.tk = tk
        self.items = items
        self.current = None
        self.file_text = ""
        self.root = tk.Tk()
        self.root.title("Review Desk")
        self.root.configure(bg=BG)
        self.root.geometry("1180x820")
        self._build()
        self.refresh_list()
        if self.items:
            self.select(0)

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
        self._button(head, "refresh from the crew", self.do_seed)
        self._button(head, "open the index", lambda: self.open_path(queue_file()))

        body = self.tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=4)

        left = self.tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        self._label(left, "waiting for you", fg=DIM).pack(anchor="w")
        self.listbox = self.tk.Listbox(left, width=44, height=28, bg=PANEL, fg=FG,
                                       selectbackground=ACCENT,
                                       selectforeground="#101318",
                                       font=("Segoe UI", 9), relief="flat",
                                       activestyle="none")
        self.listbox.pack(fill="y", expand=True, pady=(2, 0))
        self.listbox.bind("<<ListboxSelect>>",
                          lambda _e: self.select(self.listbox.curselection()[0]
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
                                   font=("Consolas", 10), relief="flat",
                                   wrap="none", height=22)
        self.viewer.pack(fill="both", expand=True)
        self.viewer.tag_config("anchored", background="#2A3340")

        self._label(right, "your note - required for reject, question and defer",
                    fg=DIM).pack(anchor="w", pady=(8, 0))
        self.note = self.tk.Text(right, bg=PANEL, fg=FG, insertbackground=FG,
                                 font=("Segoe UI", 10), relief="flat", height=4,
                                 wrap="word")
        self.note.pack(fill="x")

        buttons = self.tk.Frame(right, bg=BG)
        buttons.pack(fill="x", pady=8)
        self._button(buttons, "APPROVE", lambda: self.decide("approve"), OK, True)
        self._button(buttons, "REJECT", lambda: self.decide("reject"), BAD, True)
        self._button(buttons, "QUESTION", lambda: self.decide("question"), WARN, True)
        self._button(buttons, "DEFER", lambda: self.decide("defer"), None, True)
        self._button(buttons, "clear my decision", self.undecide)

        self.status = self._label(self.root, "ready", fg=OK)
        self.status.pack(anchor="w", padx=10, pady=(0, 10))

    # -- state -------------------------------------------------------------------
    def say(self, text: str, colour=FG) -> None:
        self.status.config(text=text, fg=colour)
        self.root.update_idletasks()

    def refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for item in self.items:
            decision = item.get("decision") or ""
            mark = {"approve": "[ok] ", "reject": "[no] ",
                    "question": "[?]  ", "defer": "[...] "}.get(decision, "     ")
            if decision and not review_rules.is_complete(item):
                mark = "[!]  "
            self.listbox.insert("end", mark + item["title"])
            if decision:
                self.listbox.itemconfig(
                    "end", foreground=DECISION_COLOUR.get(decision, FG))
        counts = review_rules.summarize(self.items)
        digest = review_rules.agent_digest(self.items)
        self.counts.config(
            text=f"{counts['pending']} waiting on you - "
                 f"{counts['approve']} approved, {counts['reject']} rejected, "
                 f"{counts['question']} questions, {counts['defer']} deferred"
                 + (f", {counts['incomplete']} need a reason"
                    if counts["incomplete"] else "")
                 + (f" | {len(digest['waiting_on_agent'])} ready for the agent"
                    if digest["waiting_on_agent"] else ""))

    def select(self, index) -> None:
        if index is None or not (0 <= index < len(self.items)):
            return
        self.current = index
        item = self.items[index]
        self.title_label.config(text=item["title"])
        self.origin_label.config(text=f"{item.get('origin', '')}   {item['path']}")
        self.note.delete("1.0", "end")
        self.note.insert("1.0", item.get("note", ""))
        self.load_file(item)
        self.say(f"{review_rules.next_action(item)}", DIM)

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
        for number, line in enumerate(self.file_text.splitlines(), 1):
            self.viewer.insert("end", f"{number:>{width}}: {line}\n")
        self.show_anchor(item)

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
        save_queue(self.items)
        self.show_anchor(item)
        excerpt = review_anchors.excerpt(self.file_text, anchor)
        self.say(f"note anchored to lines {span[0]}-{span[1]}: "
                 f"{excerpt.splitlines()[0][:60]}...", OK)

    def clear_anchor(self) -> None:
        if self.current is None:
            return
        self.items[self.current]["anchor"] = ""
        save_queue(self.items)
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
        save_queue(self.items)
        self.refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(self.current)
        self.say(f"{decision}: {review_rules.next_action(item)} "
                 f"- the agent has been told", OK)

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
        save_queue(self.items)
        self.refresh_list()
        self.say("decision cleared; it is waiting for you again", DIM)

    def do_seed(self) -> None:
        self.items = seed()
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
