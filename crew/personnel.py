"""The building: who holds which post, and what resources a job gets.

Kris, 2026-09-25: think of the crew as a building of personnel, each called
to the role they have proven good at and given enough resources to do it
efficiently. This module reads crew/personnel.json and answers three things:

- resolve(assigned_to): "@scout" -> the first holder of that post;
- budget_for(member, task_type): requests from what this member's PASSING jobs
  of this type actually needed (p75 + headroom), a token ceiling that does not
  starve verbose thinkers, and a working-context ceiling from its window;
- system_addenda(member) / leash(member): the member's quirk profile.

Trials the Inspector is running (runs/crew/inspector/trials.json) are layered
on top, so a proposed change is measured before it is kept.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from .config import CREW_DIR, CrewError

PERSONNEL_FILE = CREW_DIR / "personnel.json"
MIN_REQUESTS, MAX_REQUESTS = 3, 30
HEADROOM = 2          # requests on top of what passing jobs needed
MIN_SAMPLES = 3       # passing jobs before history outranks the baseline


def load(path: Optional[Path] = None) -> dict:
    p = Path(path or PERSONNEL_FILE)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"members": {}}


def member(data: dict, name: str) -> dict:
    return (data.get("members") or {}).get(name) or {}


def resolve(assigned_to: str, data: dict, denied: List[str] = ()) -> str:
    """'@post' -> first holder not denied; a plain name passes through."""
    if not assigned_to or not assigned_to.startswith("@"):
        return assigned_to
    post = assigned_to[1:]
    holders = (data.get("posts") or {}).get(post)
    if holders is None:
        raise CrewError(f"no post {post!r}; posts: {', '.join(p for p in data.get('posts', {}) if p != 'comment')}")
    for h in holders:
        if h not in denied:
            return h
    raise CrewError(f"every holder of post {post!r} is denied: {holders}")


def history(jobs_dir: Path) -> Dict[tuple, List[dict]]:
    """(member, task_type) -> [{passed, requests, tokens}] from finished jobs."""
    out: Dict[tuple, List[dict]] = {}
    for f in Path(jobs_dir).glob("*/job.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        r = j.get("result") or {}
        if "passed" not in r:
            continue
        out.setdefault((j.get("assigned_to"), j.get("task_type")), []).append(
            {"job": j.get("task_id"), "passed": bool(r["passed"]),
             "requests": int(r.get("requests") or 0), "tokens": int(r.get("tokens") or 0)})
    return out


def _p75(values: List[int]) -> int:
    s = sorted(values)
    return s[min(len(s) - 1, math.ceil(0.75 * len(s)) - 1)]


def working_context_tokens(data: dict, name: str, ceiling: Optional[float] = None) -> int:
    pol = data.get("context_policy") or {}
    frac = ceiling if ceiling is not None else float(pol.get("context_ceiling", 0.5))
    frac = min(frac, float(pol.get("context_ceiling_max", 0.75)))
    window = int(member(data, name).get("context_window") or 131072)
    window = min(window, int(pol.get("practical_cap_tokens", 200000)))
    return int(window * frac)


def budget_for(data: dict, name: str, task_type: str,
               hist: Dict[tuple, List[dict]], trial: Optional[dict] = None) -> dict:
    """The resources one job gets. `trial` is an Inspector trial's overrides
    for this (member, task_type), if one is running."""
    trial = trial or {}
    runs = hist.get((name, task_type), [])
    passing = [r["requests"] for r in runs if r["passed"] and r["requests"]]
    base = int((data.get("task_baselines") or {}).get(task_type, 12))
    if len(passing) >= MIN_SAMPLES:
        requests, source = _p75(passing) + HEADROOM, f"p75 of {len(passing)} passing jobs + {HEADROOM}"
    else:
        requests, source = base, f"task baseline ({len(passing)} passing jobs so far)"
    requests += int(trial.get("extra_requests", 0))
    requests = max(MIN_REQUESTS, min(MAX_REQUESTS, requests))
    ctx = working_context_tokens(data, name, trial.get("context_ceiling"))
    # Tokens: a runaway stop, not a diet - but tokens are credits, so the
    # member's own history sets it where there is one: twice what its 90th
    # percentile PASSING job used (Qwen's research needed ~141k on average and
    # lost 11 jobs to a flat 60k ceiling). Without history, 15% of the working
    # context per request (30% let a history-less scout reach 1M tokens).
    # Verbose thinkers (token_factor) get more room.
    factor = float((member(data, name).get("quirks") or {}).get("token_factor", 1.0))
    factor *= float(trial.get("token_factor", 1.0))
    upper = int(requests * ctx * 0.6 * factor)
    used = sorted(r["tokens"] for r in runs if r["passed"] and r["tokens"])
    if len(used) >= MIN_SAMPLES:
        p90 = used[min(len(used) - 1, math.ceil(0.9 * len(used)) - 1)]
        max_tokens = min(upper, max(60000, int(2 * p90 * factor)))
    else:
        max_tokens = min(upper, max(60000, int(requests * ctx * 0.15 * factor)))
    pol = data.get("context_policy") or {}
    obs_chars = int(min(24000, max(6000, ctx * float(pol.get("chars_per_token", 3.5)) / 12)))
    return {"max_requests": requests, "max_tokens": max_tokens,
            "context_tokens": ctx, "observation_chars": obs_chars, "source": source}


def system_addenda(data: dict, name: str, extra: List[str] = ()) -> str:
    lines = list((member(data, name).get("quirks") or {}).get("addenda") or []) + list(extra)
    if not lines:
        return ""
    return "\nHOUSE NOTES FOR YOU (learned from your earlier work; follow them):\n" + \
        "\n".join(f"- {l}" for l in lines)


def leash(data: dict, name: str) -> dict:
    return dict((member(data, name).get("quirks") or {}).get("leash") or {})
