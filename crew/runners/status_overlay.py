"""A small always-on-top window, top-left, saying what the crew is doing now.

Kris, 2026-09-26: "let them know with the top left corner what actions are being
taken, what larger campaign they are connected to, and time estimates for
completion of the step. It should also show a total time for completion of all
steps, both concurrent and consecutive tasks. Tracking this will help us pick
more realistic times based on our system, and track system stress created by
campaigns and workloads."

Reads every live status.json the crew's drivers already write (jobs, campaigns,
timed plans, OpenCode trials, special-teams missions, FSM learners). Totals:
steps running side by side count once (the latest finish wins); queued steps
inside a campaign or timed plan are added end to end after the current one.
Every 30 s a load sample (CPU, memory, worker processes, active steps) goes to
runs/crew/load/load.jsonl, so campaigns can be matched to machine stress later.

Starts compact and ghosted (50% opaque, click-through). Hover + middle-click
wakes it: full opacity, detailed, clickable, with the Review Desk one click away.
It returns to ghost a few seconds after the cursor leaves. Right-click while
awake picks the corner it sits in (remembered in runs/crew/load/overlay.json),
for when a tool underneath is hidden even by the ghost.

    pythonw C:/Users/user/ATLAS-api-harness/crew/runners/status_overlay.py
"""

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

RUNS = REPO / "runs" / "crew"
LOAD_LOG = RUNS / "load" / "load.jsonl"
OVERLAY_PREFS = RUNS / "load" / "overlay.json"
CORNERS = {"top-left": "Top left", "top-right": "Top right",
           "bottom-left": "Bottom left", "bottom-right": "Bottom right"}
MARGIN = 8
RECENT_S = 3 * 3600                  # a "running" file older than this is stale
DESKTOP_TASKS = {"ui_sweep", "ahk_code_task", "ahk_code_tests"}   # these drive the screen
BG, FG, DIM, ACCENT, OK, BAD = "#161A20", "#E8EAED", "#9AA4B2", "#FF9E3D", "#5BD675", "#FF6B6B"
WARN_FG = "#FFC857"


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fresh(p: Path, s: dict = None) -> bool:
    """Recent, and - when the file names its process - that process is alive.
    (A killed run leaves its status.json saying 'running' forever.)"""
    try:
        if time.time() - p.stat().st_mtime >= RECENT_S:
            return False
    except OSError:
        return False
    pid = (s or {}).get("pid")
    if pid:
        import psutil
        return psutil.pid_exists(int(pid))
    return True


def _hm(t):
    return t.strftime("%H:%M") if t else "?"


def _at_today(hhmm: str):
    try:
        h, m = map(int, hhmm.split(":"))
        now = dt.datetime.now()
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return t if t >= now - dt.timedelta(hours=12) else t + dt.timedelta(days=1)
    except (ValueError, AttributeError):
        return None


def _eta_times(eta: dict):
    if not eta or "likely_by" not in eta:
        return None, None
    return _at_today(eta["likely_by"]), _at_today(eta["worst_by"])


CREW_EXE_NAMES = ("the-crew.exe", "the_crew.exe")
CREW_TITLE = "the crew"


def is_crew_window(name: str = "", title: str = "") -> bool:
    """Is this the foreground window of TheCrew itself?

    Kris, 2026-10-29: "we don't need to see the overlay if the main window is active". The
    overlay is for when he is looking at something else - the build output, the editor, the
    desktop - not for when the window it duplicates is already in front of him. Pure, so the
    decision is tested without a desktop: the process image name is the reliable signal, the
    window title the fallback (his window is titled "The Crew").
    """
    name, title = (name or "").lower(), (title or "").lower()
    return name in CREW_EXE_NAMES or (not name and CREW_TITLE in title)


def foreground_is_crew() -> bool:
    """Whether TheCrew's own window is in front right now. False when it cannot be told."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = ""
        if pid.value:
            try:
                import psutil
                name = psutil.Process(pid.value).name()
            except Exception:                    # noqa: BLE001 - an unknown name is not a fault
                name = ""
    except Exception:                            # noqa: BLE001 - never break the overlay over this
        return False
    return is_crew_window(name, buf.value)


def build_alive_note(folder: Path, silent_s: float = 120.0, now: float = None) -> str:
    """`silent for 8m` when nothing in a build folder has changed - the `QUIET` signal, cheaply.

    The same idea as `crew/runners/alive.py` (a build that has stopped writing for minutes is not
    progressing), but read from file times instead of a subprocess, because the overlay refreshes
    every few seconds and must not spawn one process per row.
    """
    newest = None
    try:
        for path in folder.iterdir():
            if path.is_file():
                stamp = path.stat().st_mtime
                newest = stamp if newest is None else max(newest, stamp)
    except OSError:
        return ""
    if newest is None:
        return ""
    silent = (time.time() if now is None else now) - newest
    if silent < silent_s:
        return ""
    minutes = int(silent // 60)
    return f"quiet for {minutes}m" if minutes < 60 else f"quiet for {minutes // 60}h{minutes % 60:02d}"


def gather():
    """-> list of steps: {what, group, likely, worst, queued_minutes, desktop}"""
    from crew import eta as eta_mod
    steps = []
    now = dt.datetime.now()
    # single crew jobs (each writes its own status.json since 2026-09-26)
    for p in RUNS.glob("jobs/*/status.json"):
        s = _read(p)
        if not s or s.get("state") != "running" or not _fresh(p, s):
            continue
        job = _read(p.parent / "job.json") or {}
        if job.get("status") not in (None, "in_progress", "ready"):
            continue
        likely, worst = _eta_times(s.get("eta"))
        steps.append({"what": f"{s.get('member')}: {s.get('task_type')}",
                      "group": (job.get("title") or "")[:48], "likely": likely,
                      "worst": worst, "queued_minutes": 0,
                      "desktop": s.get("task_type") in DESKTOP_TASKS,
                      "started": s.get("started", "")[11:16], "note": s.get("you_might_see", "")})
    # PA builds (crew/runners/pa_build.py writes one status.json per build): these were the one
    # kind of work this overlay never showed, which is exactly why a build could be quietly dead
    # for twenty minutes without anything on screen saying so (Kris, 2026-10-29).
    for p in RUNS.glob("pa/builds/*/status.json"):
        s = _read(p)
        if not s or s.get("state") != "running" or not _fresh(p, s):
            continue
        likely, worst = _eta_times(s.get("eta"))
        steps.append({"what": f"{s.get('pa')}: {s.get('branch') or 'build'}",
                      "group": "one feature, in its own worktree",
                      "likely": likely, "worst": worst, "queued_minutes": 0,
                      "desktop": False, "started": s.get("started", "")[11:16],
                      "note": build_alive_note(p.parent) or s.get("you_might_see", "")})
    # campaigns: the running task(s), plus the waiting ones queued after
    for p in RUNS.glob("campaigns/*/status.json"):
        s = _read(p)
        if not s or (p.parent / "summary.json").exists() or not _fresh(p, s):
            continue
        tasks = s.get("tasks") or {}
        queued = 0.0
        for tid, t in tasks.items():
            if t.get("state") == "waiting":
                duty = "crew:code_task" if t.get("kind") == "module" else "crew:code_tests"
                queued += float(eta_mod.estimate(t.get("member", ""), duty).get("likely_minutes") or 0)
        for tid, t in tasks.items():
            if t.get("state") == "running":
                likely, worst = _eta_times(t.get("eta"))
                steps.append({"what": f"{t.get('member')}: {tid}", "group": f"campaign {s.get('campaign')}",
                              "likely": likely, "worst": worst, "queued_minutes": queued,
                              "desktop": False, "started": "", "note": s.get("you_might_see", "")})
                queued = 0
    # timed plans: the current item, plus the items still planned
    for p in RUNS.glob("timed/*/status.json"):
        s = _read(p)
        if not s or not _fresh(p, s) or not s.get("current"):
            continue
        queued = sum(float((i.get("predict") or {}).get("minutes") or 0)
                     for i in s.get("items", []) if i.get("state") in ("planned", "waiting")
                     and i.get("id") != s.get("current"))
        waiting = s.get("waiting_until")
        steps.append({"what": ("waiting: " if waiting else "running: ") + s["current"],
                      "group": f"timed plan {s.get('name')}", "likely": None, "worst": None,
                      "queued_minutes": queued, "desktop": False,
                      "started": (waiting or "")[11:16]})
    # OpenCode trials, special-teams missions, FSM learners
    for kind, pattern in (("opencode", "opencode/*/status.json"),
                          ("special teams", "special_teams/*/status.json"),
                          ("state-machine learner", "fsm/*/status.json")):
        for p in RUNS.glob(pattern):
            s = _read(p)
            if not s or s.get("state") != "running" or not _fresh(p, s):
                continue
            likely, worst = _eta_times(s.get("eta"))
            what = f"{s.get('member') or s.get('mission') or p.parent.name}"
            if s.get("heartbeat"):                 # runs that report progress (fsm_desk)
                try:
                    age = (dt.datetime.now() - dt.datetime.fromisoformat(s["heartbeat"])).seconds
                except ValueError:
                    age = -1
                what += (f" - {s.get('stage', '?')}, {s.get('steps', 0)} steps, "
                         f"{s.get('steps_per_s', 0)}/s, heartbeat {age}s ago")
                if s.get("time_limit_min") and not worst:
                    t0 = _at_today(str(s.get("started", ""))[:5])
                    worst = t0 + dt.timedelta(minutes=s["time_limit_min"]) if t0 else None
            steps.append({"what": what,
                          "group": f"{kind}: {p.parent.name}"[:48], "likely": likely,
                          "worst": worst, "queued_minutes": 0, "desktop": False, "note": s.get("you_might_see", ""),
                          "started": (s.get("started") or "")[-8:-3]})
    # the warm AHK sandbox: open between test runs on purpose (2026-09-26)
    try:
        from crew import ahkrun
        hb = ahkrun.WARM / "heartbeat.txt"
        if ahkrun.warm_alive():
            parts = hb.read_text(encoding="ascii", errors="replace").split()
            info = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
            steps.append({"what": f"Warm sandbox - {info.get('state', '?')}, "
                                  f"{info.get('jobs', '?')} run(s) served",
                          "group": "AHK test sandbox", "likely": None, "worst": None,
                          "queued_minutes": 0, "desktop": False, "started": "",
                          "eta_text": f"closes itself after {ahkrun.WARM_IDLE_S // 60} min idle",
                          "note": "the Windows Sandbox window stays open between tests - "
                                  "that is the warm sandbox saving a 5-minute boot per run"})
    except Exception:  # noqa: BLE001 - the overlay must never crash
        pass
    # the heavy queue: items waiting their turn, #1 runs next
    try:
        from crew.runners import heavy_queue
        disp = _read(heavy_queue.DISPATCHER) or {}
        live = heavy_queue.running()
        reason = (f"runs after {live[0]['label']}" if live
                  else disp.get("waiting_on") or "")
        for item in heavy_queue.waiting():
            mins = float(eta_mod.estimate(item.get("member", ""), item.get("duty", ""))
                         .get("likely_minutes") or 0) if item.get("member") else 0
            n = item["position"]
            steps.append({"what": f"QUEUED #{n}{' (next)' if n == 1 else ''}: {item['label']}",
                          "group": "heavy queue" + (f" - {reason}" if reason
                                                    and n == 1 else ""),
                          "likely": None, "worst": None, "queued_minutes": 0, "desktop": False,
                          "note": item.get("note", ""), "started": "", "queue_minutes": mins,
                          "eta_text": f"~{mins:.0f}m once started" if mins else "no estimate yet"})
    except Exception:  # noqa: BLE001 - the overlay must never crash
        pass
    return steps


def totals(steps):
    """All work: concurrent steps count once (latest finish); queued work adds on.
    An OVERDUE step (past its worst case) has no honest estimate left, so it is
    counted as unknown rather than pulling the total into the past."""
    now = dt.datetime.now()
    queue = [s for s in steps if "queue_minutes" in s]    # heavy queue: one after another
    steps = [s for s in steps if "queue_minutes" not in s]
    after = dt.timedelta(minutes=sum(s["queue_minutes"] for s in queue))
    live = [s for s in steps if s["likely"] and s["worst"] and s["worst"] >= now]
    likely = [max(s["likely"], now) + dt.timedelta(minutes=s["queued_minutes"]) for s in live]
    worst = [s["worst"] + dt.timedelta(minutes=s["queued_minutes"]) for s in live]
    unknown = len(steps) - len(live) + sum(1 for s in queue if not s["queue_minutes"])
    if queue:
        likely, worst = [max(likely or [now]) + after], [max(worst or [now]) + 2 * after]
    return (max(likely) if likely else None, max(worst) if worst else None, unknown, now)


def load_sample():
    import psutil
    procs = [p for p in psutil.process_iter(["name", "cmdline"])
             if (p.info["name"] or "").lower() in ("python.exe", "pythonw.exe", "node.exe")]
    return {"cpu": psutil.cpu_percent(interval=None),
            "mem": psutil.virtual_memory().percent, "workers": len(procs)}


GHOST_ALPHA, AWAKE_ALPHA = 0.5, 0.97
IDLE_BACK_TO_GHOST_S = 3.0
PYTHONW = r"C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe"


def review_waiting():
    """(count, titles) of Review Desk items waiting on Kris."""
    try:
        from crew.runners import review_desk as rd
        items = rd.load_queue()
        pending = [i for i in items if not i.get("decision")]
        return len(pending), [i.get("title", "") for i in pending][:5]
    except Exception:  # noqa: BLE001 - the overlay must never crash
        return 0, []


def main():
    """Ghost by default: compact, 50% opaque, clicks pass through to what is
    underneath. Hover + middle-click wakes it: full opacity, detailed, clickable.
    A few seconds after the cursor leaves, it goes back to ghost. A click-through
    window cannot receive mouse events, so the cursor and the middle button are
    read from Windows directly (GetCursorPos / GetAsyncKeyState)."""
    import ctypes
    import subprocess
    import tkinter as tk
    user32 = ctypes.windll.user32
    root = tk.Tk()
    root.overrideredirect(True)                  # no title bar; never in the taskbar
    root.attributes("-topmost", True)
    root.configure(bg=BG)
    try:
        corner = json.loads(OVERLAY_PREFS.read_text(encoding="utf-8")).get("corner")
    except Exception:  # noqa: BLE001 - no prefs yet
        corner = None
    state_corner = {"corner": corner if corner in CORNERS else "top-left"}
    root.geometry(f"+{MARGIN}+{MARGIN}")
    state = {"awake": False, "last_inside": 0.0, "mb_down": False, "last_log": 0.0}
    frame = tk.Frame(root, bg=BG, padx=10, pady=8, highlightthickness=1,
                     highlightbackground=ACCENT)
    frame.pack()
    head = tk.Label(frame, bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"), anchor="w",
                    justify="left")
    head.pack(anchor="w")
    body = tk.Label(frame, bg=BG, fg=FG, font=("Consolas", 9), anchor="w", justify="left")
    body.pack(anchor="w")
    review = tk.Label(frame, bg=BG, fg=WARN_FG, font=("Segoe UI", 9), anchor="w",
                      justify="left")
    review.pack(anchor="w")
    buttons = tk.Frame(frame, bg=BG)

    def open_desk():
        subprocess.Popen([PYTHONW, str(REPO / "crew" / "runners" / "review_desk.py"), "--seed"],
                         cwd=str(REPO))

    tk.Button(buttons, text="Open Review Desk", command=open_desk, relief="flat",
              bg=ACCENT, fg="#101318", font=("Segoe UI", 9, "bold"), padx=10).pack(side="left")
    def open_watchdog():
        try:
            from crew.runners import watchdog
            os.startfile(str(watchdog.write_readable(wd["report"] or watchdog.scan(act=False))))
        except Exception:  # noqa: BLE001 - the overlay must never crash
            pass

    def seen_watchdog():
        try:
            from crew.runners import watchdog
            watchdog.mark_seen(wd["report"] or {})
            wd["report"] = watchdog.scan(act=True)
            refresh(schedule=False)
        except Exception:  # noqa: BLE001
            pass

    wd_buttons = tk.Frame(frame, bg=BG)
    tk.Button(wd_buttons, text="See what needs a look", command=open_watchdog, relief="flat",
              bg=BAD, fg="#101318", font=("Segoe UI", 9, "bold"), padx=10).pack(side="left")
    tk.Button(wd_buttons, text="Mark as seen", command=seen_watchdog, relief="flat",
              bg="#22303C", fg=FG, font=("Segoe UI", 8), padx=8).pack(side="left", padx=8)
    tk.Button(buttons, text="Close overlay", command=lambda: root.destroy(), relief="flat",
              bg="#22303C", fg=FG, font=("Segoe UI", 8), padx=8).pack(side="left", padx=8)
    foot = tk.Label(frame, bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w", justify="left")
    foot.pack(anchor="w")
    import psutil
    psutil.cpu_percent(interval=None)            # prime the counter

    def hwnd():
        return user32.GetParent(root.winfo_id()) or root.winfo_id()

    def click_through(on: bool):
        GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
        h = hwnd()
        style = user32.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_LAYERED
        style = (style | WS_EX_TRANSPARENT) if on else (style & ~WS_EX_TRANSPARENT)
        user32.SetWindowLongW(h, GWL_EXSTYLE, style)

    def set_mode(awake: bool):
        state["awake"] = awake
        root.attributes("-alpha", AWAKE_ALPHA if awake else GHOST_ALPHA)
        click_through(not awake)
        if awake:
            buttons.pack(anchor="w", pady=(6, 2), before=foot)
            state["last_inside"] = time.time()
        else:
            buttons.pack_forget()
            wd_buttons.pack_forget()
        refresh(schedule=False)

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def poll():
        # Hidden while TheCrew's own window is in front: the overlay repeats what that window
        # already shows, and Kris asked for it only when something else is on screen
        # (2026-10-29). Checked twice a second - GetForegroundWindow is cheap, but not free.
        if time.time() - state.get("last_crew_check", 0.0) > 0.5:
            state["last_crew_check"] = time.time()
            hidden = foreground_is_crew()
            if hidden != state.get("hidden"):
                state["hidden"] = hidden
                if hidden:
                    root.withdraw()
                else:
                    root.deiconify()
                    root.attributes("-topmost", True)   # withdraw/deiconify forgets it
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x0, y0 = root.winfo_rootx(), root.winfo_rooty()
        inside = (x0 <= pt.x <= x0 + root.winfo_width()
                  and y0 <= pt.y <= y0 + root.winfo_height())
        down = bool(user32.GetAsyncKeyState(0x04) & 0x8000)       # VK_MBUTTON
        if inside and down and not state["mb_down"]:
            set_mode(not state["awake"])                         # middle-click toggles
        state["mb_down"] = down
        if state["awake"]:
            if inside:
                state["last_inside"] = time.time()
            elif time.time() - state["last_inside"] > IDLE_BACK_TO_GHOST_S:
                set_mode(False)
        root.after(100, poll)

    wd = {"report": {}, "last": 0.0}

    def watchdog_tick():
        """Every minute, in the background: the watchdog marks lost runs, flags stalled
        or overdue ones, and stops crew-started runs far past their limits."""
        import threading

        def run():
            try:
                from crew.runners import watchdog
                wd["report"] = watchdog.scan(act=True)
            except Exception:  # noqa: BLE001 - the overlay must never crash
                pass
        if time.time() - wd["last"] >= 60:
            wd["last"] = time.time()
            threading.Thread(target=run, daemon=True).start()

    def refresh(schedule=True):
        watchdog_tick()
        try:
            steps = gather()
        except Exception:  # noqa: BLE001 - the overlay must never crash
            steps = []
        likely, worst, unknown, now = totals(steps)
        hands_off = any(s["desktop"] for s in steps)
        waiting, titles = review_waiting()
        if not steps:
            head.config(text="Crew: idle", fg=DIM)
        else:
            nq = sum(1 for s in steps if "queue_minutes" in s)
            head.config(text=(f"Crew: {len(steps) - nq} active"
                              + (f", {nq} queued" if nq else "") + "  -  "
                              + (f"all done ~{_hm(likely)} (worst {_hm(worst)})" if likely
                                 else "no total estimate yet")
                              + (f", {unknown} without a live estimate" if unknown else "")),
                        fg=ACCENT)
        if state["awake"]:
            lines = []
            for s in sorted(steps, key=lambda s: (s["likely"] or now + dt.timedelta(days=1),
                                                  s.get("what", ""))):
                if s.get("eta_text"):
                    eta = s["eta_text"]
                elif not s["likely"]:
                    eta = "no estimate yet"
                elif s["worst"] and s["worst"] < now:
                    eta = f"OVERDUE (estimate was ~{_hm(s['likely'])})"
                else:
                    eta = f"~{_hm(s['likely'])} (worst {_hm(s['worst'])})"
                q = f" +{s['queued_minutes']:.0f}m queued" if s["queued_minutes"] else ""
                note = f"\n   you might see: {s['note']}" if s.get("note") else ""
                lines.append(f"{s['what'][:34]:<34} {eta}{q}\n   {s['group']}{note}")
            body.config(text="\n".join(lines) if lines else "nothing running")
            flagged = (wd["report"] or {}).get("flagged") or []
            if flagged or (wd["report"] or {}).get("recent_failures"):
                wd_buttons.pack(anchor="w", pady=(4, 0), before=buttons)
            else:
                wd_buttons.pack_forget()
            review.config(text=(f"NEEDS YOU: {waiting} item(s) in the Review Desk\n"
                                + "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(titles))
                                if waiting else "Nothing waiting for your review.")
                          + "".join(f"\nWATCHDOG: {f['run']} {f['verdict']} - {f['why']}"
                                    + (f" ({f['action']})" if f.get("action") else "")
                                    for f in flagged[:4])
                          + "".join(f"\nFAILED {f['at']}: {f['run']} - {f['why'][:90]}"
                                    for f in ((wd["report"] or {}).get("recent_failures")
                                              or [])[:4]))
        else:
            body.config(text="hover here + middle-click to expand")
            nflag = len((wd["report"] or {}).get("flagged") or []) + len(
                (wd["report"] or {}).get("recent_failures") or [])
            review.config(text=(f"NEEDS YOU: {waiting} to review" if waiting else "")
                          + (("\n" if waiting else "") + f"WATCHDOG: {nflag} run(s) need a look"
                             if nflag else ""))
        try:
            load = load_sample()
        except Exception:  # noqa: BLE001
            load = {}
        foot.config(fg=BAD if hands_off else OK, text=(
            ("HANDS OFF - a run is driving the screen" if hands_off
             else "You can keep working - nothing here uses your screen")
            + (f"\nCPU {load.get('cpu', 0):.0f}%  mem {load.get('mem', 0):.0f}%  "
               f"workers {load.get('workers', 0)}   ({now:%H:%M:%S})"
               if load and state["awake"] else "")
            + ("\nright-click here: move to another corner" if state["awake"] else "")))
        if time.time() - state["last_log"] >= 30 and load:
            state["last_log"] = time.time()
            LOAD_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(LOAD_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": now.isoformat(timespec="seconds"), **load,
                                     "active_steps": len(steps), "review_waiting": waiting,
                                     "steps": [s["what"] for s in steps]}) + "\n")
        root.update_idletasks()
        place()
        if schedule:
            root.after(3000, refresh)

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

    def place():
        """Pin the window to its corner of the work area (the screen minus the
        taskbar); re-run after every refresh because the size changes."""
        wa = RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)   # SPI_GETWORKAREA
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        c = state_corner["corner"]
        x = wa.l + MARGIN if c.endswith("left") else wa.r - w - MARGIN
        y = wa.t + MARGIN if c.startswith("top") else wa.b - h - MARGIN
        if (root.winfo_x(), root.winfo_y()) != (x, y):
            root.geometry(f"+{x}+{y}")

    def move_to(c):
        state_corner["corner"] = c
        try:
            OVERLAY_PREFS.parent.mkdir(parents=True, exist_ok=True)
            OVERLAY_PREFS.write_text(json.dumps({"corner": c}), encoding="utf-8")
        except Exception:  # noqa: BLE001 - a lost preference is not worth a crash
            pass
        root.update_idletasks()
        place()

    menu = tk.Menu(root, tearoff=0)
    for key, label in CORNERS.items():
        menu.add_command(label=f"Move to {label.lower()}", command=lambda k=key: move_to(k))
    menu.add_separator()
    menu.add_command(label="Close overlay", command=root.destroy)

    def on_right_click(e):
        state["last_inside"] = time.time()
        menu.tk_popup(e.x_root, e.y_root)

    root.bind("<Button-3>", on_right_click)   # awake only (a ghost passes clicks through)
    root.update_idletasks()
    set_mode(False)                                     # start compact and ghosted
    refresh()
    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
