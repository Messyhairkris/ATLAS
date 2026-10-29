"""Reference for contracts/alive_lib.md. Tell alive from dead, from plain facts."""

from __future__ import annotations

from typing import Any, Optional

STATES = ("WORKING", "QUIET", "DEAD")
DEFAULT_QUIET_S = 120


def _num(value: Any) -> Optional[float]:
    """A real number (bool excluded), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def age_of(now: Any, activity: Any) -> Optional[int]:
    """Seconds since the activity, floored; None when either time is missing."""
    at, seen = _num(now), _num(activity)
    if at is None or seen is None:
        return None
    return int(at - seen)


def state_of(now: Any, started: Any = None, activity: Any = None,
             engine_start: Any = None, alive: Any = None,
             quiet_s: Any = DEFAULT_QUIET_S) -> str:
    """WORKING / QUIET / DEAD from the four facts; the first matching rule wins."""
    if alive is False:
        return "DEAD"
    began, engine = _num(started), _num(engine_start)
    if began is not None and engine is not None and began < engine:
        return "DEAD"
    if _num(activity) is None:
        return "QUIET"
    quiet = _num(quiet_s)
    quiet = DEFAULT_QUIET_S if quiet is None else quiet
    age = age_of(now, activity)
    if quiet > 0 and age is not None and age < quiet:
        return "WORKING"
    return "QUIET"


def doing_of(part: Any) -> str:
    """The newest part's own description: `tool read`, or just its type."""
    if not isinstance(part, dict):
        return ""
    kind = part.get("type")
    if not isinstance(kind, str) or not kind:
        return ""
    if kind == "tool":
        tool = part.get("tool")
        return f"tool {tool}" if isinstance(tool, str) and tool else "tool"
    return kind


def line(now: Any, started: Any = None, activity: Any = None, engine_start: Any = None,
         alive: Any = None, quiet_s: Any = DEFAULT_QUIET_S, doing: Any = "") -> str:
    """The one line the header shows, decided by state_of and then formatted."""
    state = state_of(now, started=started, activity=activity, engine_start=engine_start,
                     alive=alive, quiet_s=quiet_s)
    if state == "DEAD":
        if alive is False:
            return "DEAD     its process is gone; it will never finish - resend"
        return "DEAD     started before this engine; it will never finish - resend"
    age = age_of(now, activity)
    if state == "WORKING":
        if isinstance(doing, str) and doing:
            return f"WORKING  last activity {age}s ago ({doing})"
        return f"WORKING  last activity {age}s ago"
    if age is None:
        return "QUIET    no activity yet, but the process is alive"
    return f"QUIET    no activity for {age}s, but the process is alive"
