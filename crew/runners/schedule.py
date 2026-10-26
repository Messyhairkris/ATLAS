"""The schedule command: the window and the crew worker run this.

    python crew/runners/schedule.py list
    python crew/runners/schedule.py add --title T --when W [--kind reminder|job] [--note N] [--spec FILE]
    python crew/runners/schedule.py remove ID | enable ID | disable ID
    python crew/runners/schedule.py tick [--dry-run]
    python crew/runners/schedule.py fired [--limit 20]

Every command prints JSON (UTF-8). Reminders notify on this machine only -
nothing leaves it. `add` refuses a `when` that does not parse (exit 2). Tests
point CREW_SCHEDULE_HOME at a tmp dir instead of <state_home>/schedule.
"""

import argparse
import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from crew import schedule  # noqa: E402


def home() -> Path:
    override = os.environ.get("CREW_SCHEDULE_HOME")
    if override:
        return Path(override)
    from crew.config import load_config

    return Path(load_config().state_home) / "schedule"


def _print(data) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _error(message: str) -> None:
    _print({"error": message})
    raise SystemExit(2)


def _next_iso(entry: dict, now: datetime) -> Optional[str]:
    when = schedule.parse_when(entry.get("when", ""))
    if when is None:
        return None
    try:
        created = datetime.fromisoformat(entry["created_at"])
    except (KeyError, TypeError, ValueError):
        return None
    nxt = schedule.next_after(when, now, created)
    return nxt.isoformat() if nxt is not None else None


def cmd_list(_args) -> None:
    now = datetime.now()
    entries = []
    for entry in schedule.load(home()):
        item = dict(entry)
        item["next"] = _next_iso(entry, now)
        entries.append(item)
    _print({"entries": entries})


def cmd_add(args) -> None:
    if schedule.parse_when(args.when) is None:
        _error(f"when does not parse: {args.when!r}")
    spec = None
    if args.spec:
        try:
            spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _error(f"cannot read --spec file: {exc}")
    if args.kind == "job" and spec is None:
        _error("a job needs --spec FILE (a JSON crew job spec)")
    entry = {
        "id": "s-" + secrets.token_hex(4),
        "title": args.title,
        "kind": args.kind,
        "when": args.when,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "enabled": True,
        "note": args.note,
        "spec": spec,
    }
    h = home()
    entries = schedule.load(h)
    entries.append(entry)
    schedule.save(h, entries)
    _print({"added": entry})


def cmd_remove(args) -> None:
    h = home()
    entries = schedule.load(h)
    kept = [e for e in entries if e.get("id") != args.id]
    if len(kept) == len(entries):
        _error(f"no entry with id {args.id!r}")
    schedule.save(h, kept)
    _print({"removed": args.id})


def cmd_set_enabled(args, enabled: bool) -> None:
    h = home()
    entries = schedule.load(h)
    for entry in entries:
        if entry.get("id") == args.id:
            entry["enabled"] = enabled
            schedule.save(h, entries)
            _print({"id": args.id, "enabled": enabled})
            return
    _error(f"no entry with id {args.id!r}")


def _submit(spec: dict):
    from crew.core import Crew

    return Crew().submit(spec, "schedule")["task_id"]


def cmd_tick(args) -> None:
    h = home()
    now = datetime.now()
    if args.dry_run:  # report what is due; fire nothing
        last = schedule.load_last_fired(h)
        due_list = []
        for entry in schedule.load(h):
            raw = last.get(entry.get("id", ""))
            last_dt = None
            if raw:
                try:
                    last_dt = datetime.fromisoformat(raw)
                except ValueError:
                    last_dt = None
            occurrence = schedule.due(entry, now, last_dt)
            if occurrence is not None:
                due_list.append(
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title", ""),
                        "kind": entry.get("kind", "reminder"),
                        "occurrence": occurrence.isoformat(),
                    }
                )
        _print({"dry_run": True, "due": due_list})
        return
    from crew.runners.night_shift import notify

    _print({"fired": schedule.tick(h, now, notify, _submit)})


def cmd_fired(args) -> None:
    rows = schedule.fired_log(home())
    _print({"firings": rows[-args.limit :][::-1]})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add")
    a.add_argument("--title", required=True)
    a.add_argument("--when", required=True)
    a.add_argument("--kind", default="reminder", choices=["reminder", "job"])
    a.add_argument("--note", default="")
    a.add_argument("--spec", help="JSON file with a crew job spec (jobs only)")
    for name in ("remove", "enable", "disable"):
        c = sub.add_parser(name)
        c.add_argument("id")
    t = sub.add_parser("tick")
    t.add_argument("--dry-run", action="store_true")
    f = sub.add_parser("fired")
    f.add_argument("--limit", type=int, default=20)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "enable":
        cmd_set_enabled(args, True)
    elif args.command == "disable":
        cmd_set_enabled(args, False)
    elif args.command == "tick":
        cmd_tick(args)
    elif args.command == "fired":
        cmd_fired(args)


if __name__ == "__main__":
    main()
