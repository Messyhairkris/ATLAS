"""The Crew's schedule: reminders and timed crew jobs.

Kris chose a Schedule pane for The Crew (2026-10-24): reminders show only as
Windows notifications and in the window - nothing leaves the machine. This is
the logic; crew/runners/schedule.py is the command that drives it.

Storage under `home` (the real one is <state_home>/schedule): schedule.json
(the entries), last_fired.json ({id: ISO}), fired.jsonl (one line per firing)
and fired/ lock files so several workers can tick at once (fire_once) and
exactly one fires an occurrence. Missed occurrences collapse into ONE: a PC
off all weekend fires a daily reminder once on Monday, not three times.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_ONCE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
_EVERY_RE = re.compile(r"^every\s+(\d+)([mh])$")


def _parse_time(text: str) -> Optional[Tuple[int, int]]:
    m = _TIME_RE.fullmatch(text.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return (h, mi)


def parse_when(text: str) -> Optional[dict]:
    """`2026-10-27 09:00` / `daily|weekdays|mon,thu 09:00` / `every 30m` (or 2h).

    Case-insensitive; None for anything else (bad time like 25:00, N of 0,
    unknown day). Days are Monday = 0.
    """
    t = (text or "").strip().lower()
    if not t:
        return None
    m = _ONCE_RE.match(t)
    if m:
        try:
            at = datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
            )
        except ValueError:
            return None
        return {"type": "once", "at": at}
    m = _EVERY_RE.match(t)
    if m:
        n = int(m.group(1))
        if n <= 0:
            return None
        return {"type": "every", "minutes": n * 60 if m.group(2) == "h" else n}
    head, _, rest = t.partition(" ")
    tm = _parse_time(rest)
    if tm is None:
        return None
    if head == "daily":
        return {"type": "days", "days": list(range(7)), "time": tm}
    if head == "weekdays":
        return {"type": "days", "days": list(range(5)), "time": tm}
    names = head.split(",")
    if all(name in DAYS for name in names):
        return {
            "type": "days",
            "days": sorted(DAYS[name] for name in names),
            "time": tm,
        }
    return None


def latest(when: dict, now: datetime, created: datetime) -> Optional[datetime]:
    """The most recent scheduled time <= now that is also >= created, else None."""
    if when["type"] == "once":
        at = when["at"]
        return at if created <= at <= now else None
    if when["type"] == "days":
        h, mi = when["time"]
        days = set(when["days"])
        for back in range(8):  # today, then look back at most 7 days
            day = (now - timedelta(days=back)).date()
            if day.weekday() in days:
                cand = datetime(day.year, day.month, day.day, h, mi)
                if created <= cand <= now:
                    return cand
        return None
    step = timedelta(minutes=when["minutes"])
    k = (now - created) // step  # created + k*N minutes, the largest k <= now
    if k < 1:
        return None
    return created + k * step


def next_after(when: dict, now: datetime, created: datetime) -> Optional[datetime]:
    """The earliest scheduled time > now (and >= created), else None."""
    if when["type"] == "once":
        at = when["at"]
        return at if at > now and at >= created else None
    if when["type"] == "days":
        h, mi = when["time"]
        days = set(when["days"])
        start = now.date()
        span = 8 + max(0, (created.date() - start).days)
        for ahead in range(span + 1):
            day = start + timedelta(days=ahead)
            if day.weekday() in days:
                cand = datetime(day.year, day.month, day.day, h, mi)
                if cand > now and cand >= created:
                    return cand
        return None
    step = timedelta(minutes=when["minutes"])
    if now < created:
        return created + step
    k = (now - created) // step
    return created + (k + 1) * step


def due(
    entry: dict, now: datetime, last_fired: Optional[datetime]
) -> Optional[datetime]:
    """The one occurrence this entry owes now, else None.

    None when the entry is disabled or `when` does not parse; else latest(...)
    when it is not None and is newer than last_fired.
    """
    if not entry.get("enabled"):
        return None
    when = parse_when(entry.get("when", ""))
    if when is None:
        return None
    try:
        created = datetime.fromisoformat(entry["created_at"])
    except (KeyError, TypeError, ValueError):
        return None
    at = latest(when, now, created)
    if at is None:
        return None
    if last_fired is not None and at <= last_fired:
        return None
    return at


def load(home: Path) -> List[dict]:
    """schedule.json under home; a missing file gives []."""
    path = Path(home) / "schedule.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save(home: Path, entries: List[dict]) -> None:
    _write_atomic(
        Path(home) / "schedule.json",
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
    )


def load_last_fired(home: Path) -> Dict[str, str]:
    path = Path(home) / "last_fired.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_last_fired(home: Path, data: Dict[str, str]) -> None:
    _write_atomic(Path(home) / "last_fired.json", json.dumps(data, indent=2))


def fired_log(home: Path) -> List[dict]:
    """fired.jsonl as dicts, oldest first; a missing file gives []."""
    path = Path(home) / "fired.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def fire_once(home: Path, entry_id: str, occurrence: datetime) -> bool:
    """Create fired/<id>@<YYYYmmddTHHMM>; True if created, False if it existed."""
    d = Path(home) / "fired"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{entry_id}@{occurrence:%Y%m%dT%H%M}"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.close(fd)
    return True


def tick(home: Path, now: datetime, notify, submit) -> List[dict]:
    """Fire what is due: reminders call notify(title, note), jobs call
    submit(spec) and keep the returned job id. Returns the firings.

    An exception in notify or submit is recorded on that firing as "error"
    and does not stop the others.
    """
    home = Path(home)
    fired_state = load_last_fired(home)
    firings = []
    for entry in load(home):
        entry_id = entry.get("id", "")
        last_dt = None
        raw = fired_state.get(entry_id)
        if raw:
            try:
                last_dt = datetime.fromisoformat(raw)
            except ValueError:
                last_dt = None
        occurrence = due(entry, now, last_dt)
        if occurrence is None:
            continue
        if not fire_once(home, entry_id, occurrence):
            continue  # another worker already fired this occurrence
        firing = {
            "id": entry_id,
            "title": entry.get("title", ""),
            "kind": entry.get("kind", "reminder"),
            "occurrence": occurrence.isoformat(),
            "fired_at": now.isoformat(),
        }
        try:
            if firing["kind"] == "job":
                firing["job_id"] = submit(entry.get("spec"))
            else:
                notify(entry.get("title", ""), entry.get("note") or "")
        except Exception as exc:
            firing["error"] = str(exc)
        fired_state[entry_id] = occurrence.isoformat()
        firings.append(firing)
    if firings:
        save_last_fired(home, fired_state)
        home.mkdir(parents=True, exist_ok=True)
        with open(home / "fired.jsonl", "a", encoding="utf-8") as fh:
            for firing in firings:
                fh.write(json.dumps(firing, ensure_ascii=False) + "\n")
    return firings
