"""One heavy process at a time: a first-in, first-out queue with a visible place in line.

Kris, 2026-09-26: "Queueing after Nemotron or another process that is commanding
resources has completed sounds perfectly acceptable. Please make sure that is on
the tool they are marked as queued and the number of which heavy process will
run next."

Heavy = spends credits over many requests or runs for many minutes (OpenCode
trials and rescues, special-teams missions, campaigns). Items wait while:
  - another item from this queue is running, or
  - a heavy run started some other way is live (opencode/special_teams status.json
    saying running, with a live pid), or
  - the machine is busy (CPU above BUSY_CPU averaged over a few seconds).
The status overlay shows every waiting item as "QUEUED #n" (#1 = next) and what
the queue is waiting on. A dispatcher starts itself when something is added and
exits when the queue is empty.

    python heavy_queue.py add --label "rescue job-X" --member Nemotron --duty crew:rescue -- python crew/runners/rescue.py job-X
    python heavy_queue.py list
    python heavy_queue.py run          # the dispatcher (normally started by add)
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

HOME = REPO / "runs" / "crew" / "heavy"
QUEUE = HOME / "queue.json"
DISPATCHER = HOME / "dispatcher.json"
BUSY_CPU = 85.0
POLL_S = 15
# the interpreter heavy jobs run under - pinned, not whatever "python" is on PATH
# (on this machine plain `python` is the Hermes venv, 2026-09-26)
PYTHON = r"C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe"
PYTHONW = PYTHON[:-len("python.exe")] + "pythonw.exe"
CREATE_NO_WINDOW = 0x08000000
EXTERNAL_HEAVY = ("opencode/*/status.json", "special_teams/*/status.json")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def load() -> list:
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        return []


def save(items: list) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": items}, indent=1), encoding="utf-8")
    os.replace(tmp, QUEUE)


def _alive(pid) -> bool:
    import psutil
    try:
        return bool(pid) and psutil.pid_exists(int(pid))
    except (TypeError, ValueError):
        return False


def add(label: str, argv: list, member: str = "", duty: str = "", note: str = "") -> dict:
    items = load()
    item = {"id": uuid.uuid4().hex[:8], "label": label, "argv": argv, "member": member,
            "duty": duty, "note": note, "state": "queued", "added": _now()}
    items.append(item)
    save(items)
    ensure_dispatcher()
    return item


def waiting() -> list:
    """Queued items in run order, each with its place in line (1 = next)."""
    q = [i for i in load() if i.get("state") == "queued"]
    for n, i in enumerate(q, 1):
        i["position"] = n
    return q


def running() -> list:
    return [i for i in load() if i.get("state") == "running" and _alive(i.get("pid"))]


def busy_reason(sample_cpu: bool = True) -> str:
    """Why the next item cannot start yet ('' = free to start)."""
    live = running()
    if live:
        return f"queue item running: {live[0]['label']}"
    runs = REPO / "runs" / "crew"
    ours = {i.get("pid") for i in load()}
    for pattern in EXTERNAL_HEAVY:
        for p in runs.glob(pattern):
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if s.get("state") == "running" and _alive(s.get("pid")) and s.get("pid") not in ours:
                if time.time() - p.stat().st_mtime < 3 * 3600:
                    return f"heavy run live: {p.parent.name}"
    if sample_cpu:
        import psutil
        cpu = psutil.cpu_percent(interval=3)
        if cpu > BUSY_CPU:
            return f"machine busy: CPU {cpu:.0f}%"
    return ""


def ensure_dispatcher() -> None:
    try:
        d = json.loads(DISPATCHER.read_text(encoding="utf-8"))
        if _alive(d.get("pid")):
            return
    except (OSError, ValueError):
        pass
    subprocess.Popen([PYTHONW, str(Path(__file__).resolve()), "run"], cwd=str(REPO),
                     creationflags=CREATE_NO_WINDOW)


def _launch(item: dict) -> subprocess.Popen:
    argv = [PYTHON if a in ("python", "python.exe") else a for a in item["argv"]]
    log = HOME / "logs" / f"{item['id']}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, "w", encoding="utf-8")
    return subprocess.Popen(argv, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                            creationflags=CREATE_NO_WINDOW)


def _update(item_id: str, **fields) -> None:
    items = load()
    for i in items:
        if i["id"] == item_id:
            i.update(fields)
    save(items)


def dispatch() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    DISPATCHER.write_text(json.dumps({"pid": os.getpid(), "started": _now()}), encoding="utf-8")
    # an item left "running" by a dead dispatcher is lost, not silently re-run
    for i in load():
        if i.get("state") == "running" and not _alive(i.get("pid")):
            _update(i["id"], state="lost", finished=_now())
    while True:
        q = waiting()
        if not q:
            break
        reason = busy_reason()
        DISPATCHER.write_text(json.dumps({"pid": os.getpid(), "waiting_on": reason,
                                          "checked": _now()}), encoding="utf-8")
        if reason:
            time.sleep(POLL_S)
            continue
        item = q[0]
        proc = _launch(item)
        _update(item["id"], state="running", pid=proc.pid, started=_now())
        code = proc.wait()
        _update(item["id"], state="done" if code == 0 else "failed", exit=code,
                finished=_now())
    DISPATCHER.write_text(json.dumps({"pid": None, "stopped": _now()}), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--label", required=True)
    a.add_argument("--member", default="")
    a.add_argument("--duty", default="")
    a.add_argument("--note", default="")
    a.add_argument("argv", nargs=argparse.REMAINDER)
    sub.add_parser("list")
    sub.add_parser("run")
    args = ap.parse_args()
    if args.cmd == "add":
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        print(json.dumps(add(args.label, argv, args.member, args.duty, args.note), indent=1))
    elif args.cmd == "list":
        print(json.dumps({"waiting_on": busy_reason(), "running": running(),
                          "queued": waiting()}, indent=1))
    else:
        dispatch()
