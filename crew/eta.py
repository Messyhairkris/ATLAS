"""When will it be done? Estimates from how long each member has actually taken.

Kris, 2026-09-26: slow is fine, but "patience and ways to track when the
operation is complete should be continued to be developed and refined". Every
running thing's status.json gets a likely finish time and a worst case, from
the telemetry ledger: the model time of each past job, grouped by member and
duty (crew:scout, crew:code_task, crew:opencode_trial, ...). Model time is the
sum of call latencies, so tool and test time on our side is not counted - the
estimate is a floor, labelled as such by `basis`.
"""

import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional

LEDGER = Path("C:/Users/user/Documents/Obsidian/Knowledge_Base/wiki/experiments/"
              "atlas-api-harness/runs/telemetry.jsonl")
_cache = {"mtime": None, "table": {}}


def _table() -> dict:
    """(persona, duty) -> sorted list of per-job model seconds."""
    try:
        mtime = LEDGER.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] == mtime:
        return _cache["table"]
    per_job = defaultdict(float)
    key_of = {}
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            run, persona, duty = e.get("run_id"), e.get("persona"), e.get("duty")
            if not (run and persona and duty):
                continue
            per_job[run] += float(e.get("latency_ms") or 0) / 1000
            key_of[run] = (persona, duty)
    table = defaultdict(list)
    for run, secs in per_job.items():
        if secs > 0:
            table[key_of[run]].append(secs)
    for v in table.values():
        v.sort()
    _cache.update(mtime=mtime, table=dict(table))
    return _cache["table"]


def _pct(v, q):
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))]


def estimate(member: str, duty: str, started: Optional[dt.datetime] = None) -> dict:
    """{likely_minutes, worst_minutes, likely_by, worst_by, basis} or a 'no history' note."""
    started = started or dt.datetime.now()
    runs = _table().get((member, duty)) or []
    if len(runs) < 2:
        # fall back to the member's other duties, then to everyone on this duty
        mine = [s for (m, _), v in _table().items() if m == member for s in v]
        runs, basis = (sorted(mine), f"{member}, all duties") if len(mine) >= 2 else (
            sorted(s for (_, d), v in _table().items() if d == duty for s in v), f"all members, {duty}")
    else:
        basis = f"{member} on {duty}"
    if len(runs) < 2:
        return {"basis": "no history yet - no estimate"}
    likely, worst = _pct(runs, 0.5), _pct(runs, 0.9)
    return {"likely_minutes": round(likely / 60, 1), "worst_minutes": round(worst / 60, 1),
            "likely_by": (started + dt.timedelta(seconds=likely)).strftime("%H:%M"),
            "worst_by": (started + dt.timedelta(seconds=worst)).strftime("%H:%M"),
            "basis": f"{basis}: {len(runs)} past jobs (model time only)"}
