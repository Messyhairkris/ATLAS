"""The Inbox The Crew window opens on: gathers the inputs, crew/inbox.py (crew-built) orders them.

Round 3 (2026-10-26; the Antigravity study's "Inbox (landing view)", Gordon's "oversight digest"
- what changed while Kris was away, questions as cards, the next action). Everything is read
from files the harness already writes; nothing here calls a model.

  python -m crew cards [--seen ISO] [--mark-seen]
"""

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from . import inbox


def _seen_file(cfg) -> Path:
    return Path(cfg.state_home) / "pa" / "landing_seen.json"


def seen_at(cfg) -> str:
    try:
        return json.loads(_seen_file(cfg).read_text(encoding="utf-8")).get("seen_at", "")
    except (OSError, ValueError):
        return ""


def mark_seen(cfg, when: Optional[str] = None) -> str:
    when = when or dt.datetime.now().isoformat(timespec="seconds")
    path = _seen_file(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seen_at": when}), encoding="utf-8")
    return when


def _desk() -> list:
    try:
        from .runners import desk_cli
        listing = desk_cli.listing()
    except Exception:  # noqa: BLE001 - a broken Desk must not empty the Inbox
        return []
    return [{"item_id": i.get("item_id", ""), "title": i.get("title", ""),
             "kind": i.get("kind", ""), "decision": i.get("decision", ""),
             "state": i.get("state", ""), "added": i.get("added", "")}
            for i in listing.get("items", [])]


def _campaigns(state: Path) -> list:
    out = []
    for status in sorted((state / "campaigns").glob("*/status.json")):
        try:
            s = json.loads(status.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        done = (status.parent / "summary.json").is_file()
        out.append({"name": s.get("campaign") or status.parent.name,
                    "state": "done" if done else "active", "updated": s.get("updated", "")})
    return out


def _fired(state: Path, limit: int = 200) -> list:
    path = state / "schedule" / "fired.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _night(state: Path) -> Optional[dict]:
    reports = sorted((state / "night").glob("night-*.json"))
    if not reports:
        return None
    try:
        r = json.loads(reports[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fixers = [{"signature": g.get("signature", ""), "count": g.get("count", 0),
               "example_job": (g.get("job_ids") or [""])[0]}
              for g in r.get("groups", []) if g.get("candidate")]
    return {"at": r.get("generated", ""), "fixer_candidates": fixers}


def cards(cfg, store, seen: Optional[str] = None, now: Optional[dt.datetime] = None) -> dict:
    state = Path(cfg.state_home)
    now = now or dt.datetime.now()
    seen = seen_at(cfg) if seen is None else seen
    out = inbox.cards(desk=_desk(), jobs=list(store.all_jobs()), campaigns=_campaigns(state),
                      fired=_fired(state), night=_night(state), now=now, seen_at=seen)
    return {"now": now.isoformat(timespec="seconds"), "seen_at": seen, "cards": out,
            "counts": inbox.counts(out)}
