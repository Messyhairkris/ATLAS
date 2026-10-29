"""alive_lib.py - determine turn state and format status line.

Implements the contract for STATES, state_of, age_of, doing_of,
steps_notice, hit_ceiling, and line.
"""

from __future__ import annotations

import json
from typing import Any

STATES = ("WORKING", "QUIET", "DEAD", "STEPS")
DEFAULT_QUIET_S = 120
MAX_STEPS_MARKER = "CRITICAL - MAXIMUM STEPS REACHED"


def _is_number(value: Any) -> bool:
    """Return True for int/float that is not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def state_of(
    now: Any,
    started: Any = None,
    activity: Any = None,
    engine_start: Any = None,
    alive: Any = None,
    quiet_s: int = DEFAULT_QUIET_S,
    steps: bool = False,
) -> str:
    """Rule 0-5: return the first matching state."""
    # 0. steps ceiling hit
    if steps:
        return "STEPS"
    # 1. process gone
    if alive is False:
        return "DEAD"
    # 2. started before current engine
    if started is not None and engine_start is not None:
        if _is_number(started) and _is_number(engine_start) and started < engine_start:
            return "DEAD"
    # 3. no activity yet
    if activity is None:
        return "QUIET"
    # 4. recent activity (only when quiet_s > 0)
    if quiet_s > 0 and _is_number(now) and _is_number(activity):
        if now - activity < quiet_s:
            return "WORKING"
    # 5. default quiet
    return "QUIET"


def age_of(now: Any, activity: Any) -> int | None:
    """Return int(now-activity) when both are numbers, else None."""
    if _is_number(now) and _is_number(activity):
        return int(now - activity)
    return None


def doing_of(part: Any) -> str:
    """Return a short description of what the part is doing."""
    if not isinstance(part, dict):
        return ""
    part_type = part.get("type")
    if part_type == "tool":
        tool = part.get("tool")
        if isinstance(tool, str) and tool:
            return f"tool {tool}"
        return "tool"
    if isinstance(part_type, str):
        return part_type
    return ""


def steps_notice(part: Any) -> bool:
    """True when part is the engine's max-steps notice answer."""
    if not isinstance(part, dict):
        return False
    if part.get("type") != "text":
        return False
    text = part.get("text")
    if not isinstance(text, str):
        return False
    return text.strip().startswith(MAX_STEPS_MARKER)


def hit_ceiling(steps_used: Any, limit: Any) -> bool:
    """True when both are numbers, limit >= 1, and steps_used >= limit."""
    if not (_is_number(steps_used) and _is_number(limit)):
        return False
    if limit < 1:
        return False
    return steps_used >= limit


def line(
    now: Any,
    started: Any = None,
    activity: Any = None,
    engine_start: Any = None,
    alive: Any = None,
    quiet_s: int = DEFAULT_QUIET_S,
    doing: str = "",
    steps: bool = False,
) -> str:
    """Format a status line matching the contract."""
    state = state_of(
        now,
        started=started,
        activity=activity,
        engine_start=engine_start,
        alive=alive,
        quiet_s=quiet_s,
        steps=steps,
    )

    if state == "STEPS":
        return (
            "STEPS    the step ceiling ended this turn (text only); "
            "send the next message to continue"
        )

    if state == "WORKING":
        age = age_of(now, activity)
        base = f"WORKING  last activity {age}s ago"
        return f"{base} ({doing})" if doing else base

    if state == "QUIET":
        age = age_of(now, activity)
        if age is not None:
            return f"QUIET    no activity for {age}s, but the process is alive"
        return "QUIET    no activity yet, but the process is alive"

    # DEAD - choose the appropriate reason
    if alive is False:
        return "DEAD     its process is gone; it will never finish - resend"
    # started before engine case (rule 2)
    return "DEAD     started before this engine; it will never finish - resend"
