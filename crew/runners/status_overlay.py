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

The window never takes keyboard focus. Right-click closes it; double-click
toggles between compact and detailed.

    pythonw C:/Users/user/ATLAS-api-harness/crew/runners/status_overlay.py
"""

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

RUNS = REPO / "runs" / "crew"
LOAD_LOG = RUNS / "load" / "load.jsonl"
RECENT_S = 3 * 3600                  # a "running" file older than this is stale
DESKTOP_TASKS = {"ui_sweep", "ahk_code_task", "ahk_code_tests"}   # these drive the screen
BG, FG, DIM, ACCENT, OK, BAD = "#161A20", "#E8EAED", "#9AA4B2", "#FF9E3D", "#5BD675", "#FF6B6B"


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
            steps.append({"what": f"{s.get('member') or s.get('mission') or p.parent.name}",
                          "group": f"{kind}: {p.parent.name}"[:48], "likely": likely,
                          "worst": worst, "queued_minutes": 0, "desktop": False, "note": s.get("you_might_see", ""),
                          "started": (s.get("started") or "")[-8:-3]})
    return steps


def totals(steps):
    """All work: concurrent steps count once (latest finish); queued work adds on.
    An OVERDUE step (past its worst case) has no honest estimate left, so it is
    counted as unknown rather than pulling the total into the past."""
    now = dt.datetime.now()
    live = [s for s in steps if s["likely"] and s["worst"] and s["worst"] >= now]
    likely = [max(s["likely"], now) + dt.timedelta(minutes=s["queued_minutes"]) for s in live]
    worst = [s["worst"] + dt.timedelta(minutes=s["queued_minutes"]) for s in live]
    unknown = len(steps) - len(live)
    return (max(likely) if likely else None, max(worst) if worst else None, unknown, now)


def load_sample():
    import psutil
    procs = [p for p in psutil.process_iter(["name", "cmdline"])
             if (p.info["name"] or "").lower() in ("python.exe", "pythonw.exe", "node.exe")]
    return {"cpu": psutil.cpu_percent(interval=None),
            "mem": psutil.virtual_memory().percent, "workers": len(procs)}


def main():
    import tkinter as tk
    root = tk.Tk()
    root.overrideredirect(True)                  # no title bar; never in the taskbar
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)
    root.configure(bg=BG)
    root.geometry("+8+8")
    state = {"detail": True, "last_log": 0.0}
    frame = tk.Frame(root, bg=BG, padx=10, pady=8, highlightthickness=1,
                     highlightbackground=ACCENT)
    frame.pack()
    head = tk.Label(frame, bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"), anchor="w",
                    justify="left")
    head.pack(anchor="w")
    body = tk.Label(frame, bg=BG, fg=FG, font=("Consolas", 9), anchor="w", justify="left")
    body.pack(anchor="w")
    foot = tk.Label(frame, bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w", justify="left")
    foot.pack(anchor="w")
    import psutil
    psutil.cpu_percent(interval=None)            # prime the counter

    def refresh():
        try:
            steps = gather()
        except Exception as e:  # noqa: BLE001 - the overlay must never crash
            steps = []
            body.config(text=f"(could not read status: {e})")
        likely, worst, unknown, now = totals(steps)
        hands_off = any(s["desktop"] for s in steps)
        if not steps:
            head.config(text="Crew: idle", fg=DIM)
        else:
            head.config(text=(f"Crew: {len(steps)} active step(s)  -  "
                              + (f"all done ~{_hm(likely)} (worst {_hm(worst)})" if likely
                                 else "no total estimate yet")
                              + (f", {unknown} without a live estimate" if unknown else "")),
                        fg=ACCENT)
        if state["detail"] and steps:
            lines = []
            for s in sorted(steps, key=lambda s: s["likely"] or now + dt.timedelta(days=1)):
                if not s["likely"]:
                    eta = "no estimate yet"
                elif s["worst"] and s["worst"] < now:
                    eta = f"OVERDUE (estimate was ~{_hm(s['likely'])})"
                else:
                    eta = f"~{_hm(s['likely'])} (worst {_hm(s['worst'])})"
                q = f" +{s['queued_minutes']:.0f}m queued" if s["queued_minutes"] else ""
                note = f"\n   you might see: {s['note']}" if s.get("note") else ""
                lines.append(f"{s['what'][:34]:<34} {eta}{q}\n   {s['group']}{note}")
            body.config(text="\n".join(lines))
        elif not state["detail"]:
            body.config(text="")
        else:
            body.config(text="nothing running")
        try:
            load = load_sample()
        except Exception:  # noqa: BLE001
            load = {}
        colour = BAD if hands_off else OK
        foot.config(fg=colour, text=(
            ("HANDS OFF - a run is driving the screen" if hands_off
             else "You can keep working - nothing here uses your screen")
            + (f"\nCPU {load.get('cpu', 0):.0f}%  mem {load.get('mem', 0):.0f}%  "
               f"workers {load.get('workers', 0)}   ({now:%H:%M:%S})" if load else "")))
        if time.time() - state["last_log"] >= 30 and load:
            state["last_log"] = time.time()
            LOAD_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(LOAD_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": now.isoformat(timespec="seconds"), **load,
                                     "active_steps": len(steps),
                                     "steps": [s["what"] for s in steps]}) + "\n")
        root.after(3000, refresh)

    def toggle(_e=None):
        state["detail"] = not state["detail"]
        refresh()

    for w in (root, frame, head, body, foot):
        w.bind("<Double-Button-1>", toggle)
        w.bind("<Button-3>", lambda _e: root.destroy())
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
