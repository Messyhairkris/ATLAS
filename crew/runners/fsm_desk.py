"""Learn the Review Desk's state machine from its real window code - hidden.

Kris, 2026-09-26: scale the learner up, starting with the Review Desk. The Desk
is a Tkinter window, not a web page, and clicking it on screen would put
thousands of presses on Kris's real desktop. So:

- the Desk's REAL class is built with its window withdrawn before it is ever
  drawn (no mouse, nothing on screen) and its own handlers are called;
- all state lives in a THROWAWAY crew home (CREW_HOME), never the real review
  queue - no real decision is touched, nothing reaches a real agent;
- the one piece replaced is the hand-over pop-up (a modal with a grab, which a
  hidden window cannot hold): it is recorded as an output, and the "send" input
  runs the same calls the pop-up's SEND button runs (send_to_agent, then
  refresh). That adapter is the only non-original code on the path.

Inputs are SYMBOLIC classes (Huang & Peleska): a note is empty, too short, or
long enough - the three classes review_rules.validate treats differently.
One review item = one component; the paper's answer to state explosion is to
learn components separately.

  python C:/Users/user/ATLAS-api-harness/crew/runners/fsm_desk.py [items=1]
"""

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
SANDBOX = Path(tempfile.mkdtemp(prefix="desk-fsm-"))
os.environ["CREW_HOME"] = str(SANDBOX)          # before anything reads the config

from aalpy.base import SUL  # noqa: E402
from aalpy.learning_algs import run_Lstar  # noqa: E402
from aalpy.oracles import RandomWMethodEqOracle, WMethodEqOracle  # noqa: E402

from crew.reviewdesk import review_rules  # noqa: E402
from crew.runners import review_desk as rd  # noqa: E402

import tkinter  # noqa: E402

_RealTk = tkinter.Tk


class _HiddenTk(_RealTk):
    """A Tk root that is withdrawn, transparent and off-screen from its first
    moment. (2026-09-26: withdrawing AFTER rd.Desk() let the window flash on
    Kris's screen at every reset - hundreds of times. It is now hidden before
    the Desk's own code runs, and every step checks it stayed hidden.)"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.withdraw()
        self.attributes("-alpha", 0.0)
        self.geometry("+-32000+-32000")


tkinter.Tk = _HiddenTk

TIME = re.compile(r"\d{1,2}:\d{2}(:\d{2})?")


class DeskSUL(SUL):
    def __init__(self, n_items: int):
        super().__init__()
        self.n = n_items
        self.desk = None
        self.offers = []
        self.steps = self.resets = 0
        self.short = "x" * max(1, review_rules.MIN_NOTE_CHARS - 1)
        self.long = "a real reason " * (review_rules.MIN_NOTE_CHARS // 10 + 2)

    # -- a fresh desk over a fresh throwaway queue ---------------------------------
    def pre(self):
        if self.desk is not None:
            self.desk.root.destroy()
        home = SANDBOX / "review"
        if home.exists():
            shutil.rmtree(home)
        home.mkdir(parents=True)
        files = SANDBOX / "files"
        files.mkdir(exist_ok=True)
        items = []
        for i in range(1, self.n + 1):
            f = files / f"item{i}.py"
            f.write_text(f"# item {i}\nx = {i}\n", encoding="utf-8")
            items.append({"item_id": f"item{i}", "title": f"item {i}", "path": str(f),
                          "origin": "fsm", "state": "pending", "decision": "", "note": ""})
        rd.save_queue(items)
        self.desk = rd.Desk(rd.load_queue())     # its Tk root is _HiddenTk: never drawn
        self.offers = []
        desk = self.desk
        desk.modal = lambda batch, complete: self.offers.append(
            ("offer-complete" if complete else "offer", len(batch)))
        self.resets += 1

    def post(self):
        pass

    # -- inputs ----------------------------------------------------------------------
    def _note(self, text):
        self.desk.note.delete("1.0", "end")
        self.desk.note.insert("1.0", text)

    def step(self, letter):
        self.steps += 1
        d = self.desk
        if d.root.winfo_viewable() or d.root.state() != "withdrawn":
            raise SystemExit("the desk window became visible - stopping so nothing "
                             "appears on the user's screen")
        before = len(self.offers)
        if letter.startswith("select"):
            d.select(int(letter[-1]) - 1)
        elif letter == "note_empty":
            self._note("")
        elif letter == "note_short":
            self._note(self.short)
        elif letter == "note_ok":
            self._note(self.long)
        elif letter in ("approve", "reject", "question", "defer"):
            d.decide(letter)
        elif letter == "undecide":
            d.undecide()
        elif letter == "send":
            # the pop-up's SEND button: the same calls, in the same order
            if rd.ready_to_send(d.items):
                rd.send_to_agent(d.items)
                d.sent = rd.load_sent()
                d.refresh_list()
                d.reselect()
            else:
                d.offer_handoff()
        return self.observe(len(self.offers) > before)

    # -- what the window would show ------------------------------------------------
    def observe(self, offered: bool) -> str:
        d = self.desk
        status = TIME.sub("T", d.status.cget("text"))
        send = d.send_button.cget("text")
        rows = [d.listbox.get(i) for i in range(d.listbox.size())]
        return " | ".join([send, "rows=" + ";".join(rows), status]
                          + ([f"offer:{self.offers[-1]}"] if offered else []))


def main(n_items: int = 1):
    # hard stop: the desk must be writing into the throwaway home, never the real queue
    if SANDBOX.resolve() not in rd.home().resolve().parents:   # resolve both: 8.3 vs long names
        raise SystemExit(f"refusing to run: the desk would write to {rd.home()}, "
                         f"not the sandbox {SANDBOX}")
    out = REPO / "runs" / "crew" / "fsm" / f"review-desk-{n_items}-item"
    out.mkdir(parents=True, exist_ok=True)
    (out / "status.json").write_text(json.dumps({"state": "running", "pid": os.getpid(),
                                                 "you_might_see": "nothing - hidden Review Desk "
                                                 "windows are created and destroyed off-screen; "
                                                 "if one ever flashes, this run is why (it stops "
                                                 "itself if a window becomes visible)",
                                                 "started": time.strftime("%H:%M:%S")}))
    sul = DeskSUL(n_items)
    alphabet = ["note_empty", "note_short", "note_ok", "approve", "reject", "question",
                "defer", "undecide", "send"] + [f"select{i}" for i in range(1, n_items + 1)
                                                 if n_items > 1]
    t0 = time.time()
    # explore with random W-method walks, then certify: W-method is complete for any
    # desk with at most (found + 1) states
    explore = RandomWMethodEqOracle(alphabet, sul, walks_per_state=30, walk_len=10)
    model = run_Lstar(alphabet, sul, explore, automaton_type="mealy", print_level=0)
    found = len(model.states)
    certify = WMethodEqOracle(alphabet, sul, max_number_of_states=found + 1)
    model = run_Lstar(alphabet, sul, certify, automaton_type="mealy", print_level=0)
    (out / "model.dot").write_text(str(model), encoding="utf-8")
    result = {"component": f"review desk, {n_items} item(s)", "states": len(model.states),
              "states_after_exploring": found, "certified_up_to": found + 1,
              "alphabet": alphabet, "steps": sul.steps, "resets": sul.resets,
              "seconds": round(time.time() - t0, 1),
              "note_classes": {"short": len(sul.short), "long": len(sul.long),
                               "MIN_NOTE_CHARS": review_rules.MIN_NOTE_CHARS},
              "sandbox": str(SANDBOX)}
    (out / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (out / "status.json").write_text(json.dumps({"state": "finished", **result}))
    if sul.desk is not None:
        sul.desk.root.destroy()
    shutil.rmtree(SANDBOX, ignore_errors=True)
    return result


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1), indent=1))
