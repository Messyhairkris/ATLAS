"""What the provider says is left, rather than what we guessed.

Synthetic returns `x-synthetic-quotas` on every chat response. Measured on
2026-09-20 it carries, live:

```json
{"rollingFiveHourLimit": {"remaining": 999.97, "max": 1000, "tickPercent": 0.05,
                          "nextTickAt": "...", "limited": false},
 "weeklyTokenLimit": {"maxCredits": "$48.00", "remainingCredits": "$3.32",
                      "percentRemaining": 6.92, "nextRegenCredits": "$0.96",
                      "nextRegenAt": "..."},
 "subscription": {"limit": 1000, "requests": 0, "renewsAt": "..."}}
```

Two things that only a reading can tell you, both of which broke assumptions we
had been working under:

1. **A cheap model costs about 1/30 of a request.** Two calls took the five-hour
   balance from 1000 to 999.933 - 0.0333 each. Our own governor charged 1.0 per
   call, so it was roughly 30x too cautious and would have idled a campaign that
   had plenty of headroom.
2. **Requests are rarely the binding limit; the weekly credit pool is.** At the
   time of measurement 99.99% of requests were available and 6.9% of credits were.
   A governor that only counts requests will happily run a campaign straight into
   a credit wall.

This module keeps the last reading on disk so any process - a campaign, the CLI,
the MCP server - can see it without making a call of its own.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

STATE_ENV = "ATLAS_QUOTA_FILE"
DEFAULT_STATE = (Path(__file__).resolve().parents[2] / "runs" / "quotas.json")


def state_path() -> Path:
    return Path(os.environ.get(STATE_ENV) or DEFAULT_STATE)


def _money(text) -> Optional[float]:
    """"$3.32" -> 3.32. Returns None rather than inventing a number."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = re.search(r"-?\d+(?:\.\d+)?", str(text))
    return float(match.group()) if match else None


def record(snapshot: Dict) -> Dict:
    """Store a fresh reading. Returns the flattened view."""
    view = summarize(snapshot)
    view["read_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"raw": snapshot, "view": view}, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)
    return view


def summarize(snapshot: Dict) -> Dict:
    """The four numbers a governor actually needs, plus where they came from."""
    five = (snapshot.get("rollingFiveHourLimit") or {})
    week = (snapshot.get("weeklyTokenLimit") or {})
    return {
        "requests_remaining": five.get("remaining"),
        "requests_max": five.get("max"),
        "requests_tick_percent": five.get("tickPercent"),
        "requests_next_tick": five.get("nextTickAt"),
        "requests_limited": bool(five.get("limited")),
        "credits_remaining_usd": _money(week.get("remainingCredits")),
        "credits_max_usd": _money(week.get("maxCredits")),
        "credits_percent_remaining": week.get("percentRemaining"),
        "credits_next_regen_usd": _money(week.get("nextRegenCredits")),
        "credits_next_regen_at": week.get("nextRegenAt"),
    }


def latest() -> Optional[Dict]:
    """The last reading, or None if the provider has never answered us."""
    path = state_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("view")
    except (OSError, json.JSONDecodeError):
        return None


def binding_limit(view: Optional[Dict] = None) -> Dict:
    """Which limit will stop us first, in its own units.

    Returns {"limit": "credits"|"requests"|"unknown", "headroom": float,
             "detail": str}. Credits are compared as a fraction of their pool so
    the two can be ranked at all.
    """
    view = view or latest()
    if not view:
        return {"limit": "unknown", "headroom": 0.0,
                "detail": "the provider has not reported a quota yet; make one "
                          "call and read the header"}
    req_frac = None
    if view.get("requests_remaining") is not None and view.get("requests_max"):
        req_frac = float(view["requests_remaining"]) / float(view["requests_max"])
    cred_frac = None
    if view.get("credits_percent_remaining") is not None:
        cred_frac = float(view["credits_percent_remaining"]) / 100.0
    elif (view.get("credits_remaining_usd") is not None
          and view.get("credits_max_usd")):
        cred_frac = (float(view["credits_remaining_usd"])
                     / float(view["credits_max_usd"]))
    if cred_frac is None and req_frac is None:
        return {"limit": "unknown", "headroom": 0.0,
                "detail": "the quota header carried neither limit"}
    if cred_frac is None or (req_frac is not None and req_frac <= cred_frac):
        return {"limit": "requests", "headroom": req_frac,
                "detail": f"{view['requests_remaining']:.1f} of "
                          f"{view['requests_max']} requests left in this five-hour "
                          f"window"}
    return {"limit": "credits", "headroom": cred_frac,
            "detail": f"${view.get('credits_remaining_usd')} of "
                      f"${view.get('credits_max_usd')} weekly credits left "
                      f"({cred_frac * 100:.1f}%), +$"
                      f"{view.get('credits_next_regen_usd')} at "
                      f"{view.get('credits_next_regen_at')}"}
