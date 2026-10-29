"""alive_lib.py - determine the state of a turn from four facts."""

from __future__ import annotations

from typing import Any, Mapping

STATES = ("WORKING", "QUIET", "DEAD")
DEFAULT_QUIET_S = 120


def _is_number(value: Any) -> bool:
    """Return True if value is an int or float (but not bool)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def state_of(
    now: float | int | None,
    started: float | int | None = None,
    activity: float | int | None = None,
    engine_start: float | int | None = None,
    alive: bool | None = None,
    quiet_s: float | int = DEFAULT_QUIET_S,
) -> str:
    """Return the state string according to the ordered rules."""
    # Rule 1: process known to be gone.
    if alive is False:
        return "DEAD"

    # Rule 2: turn started before the current engine.
    if (
        _is_number(started)
        and _is_number(engine_start)
        and started < engine_start
    ):
        return "DEAD"

    # Normalise activity: treat non-numeric as missing.
    activity_is_num = _is_number(activity)
    activity_val = activity if activity_is_num else None

    # Rule 3: no activity information yet.
    if activity_val is None:
        return "QUIET"

    # Rule 4: recent activity (strictly less than quiet_s).
    if _is_number(now) and _is_number(quiet_s) and quiet_s > 0:
        if (now - activity_val) < quiet_s:
            return "WORKING"

    # Rule 5: otherwise quiet.
    return "QUIET"


def age_of(now: float | int | None, activity: float | int | None) -> int | None:
    """Return the integer age (floor) of the activity, or None if unavailable."""
    if not (_is_number(now) and _is_number(activity)):
        return None
    return int(now - activity)


def doing_of(part: Mapping[str, Any] | None) -> str:
    """Extract a human-readable description of what the part is doing."""
    if not isinstance(part, Mapping):
        return ""
    typ = part.get("type")
    if not isinstance(typ, str):
        return ""
    if typ == "tool":
        tool = part.get("tool")
        if isinstance(tool, str) and tool:
            return f"tool {tool}"
        return "tool"
    return typ


def line(
    now: float | int,
    started: float | int | None = None,
    activity: float | int | None = None,
    engine_start: float | int | None = None,
    alive: bool | None = None,
    quiet_s: float | int = DEFAULT_QUIET_S,
    doing: str = "",
) -> str:
    """Format a one-line status message aligned on the state word."""
    state = state_of(
        now,
        started=started,
        activity=activity,
        engine_start=engine_start,
        alive=alive,
        quiet_s=quiet_s,
    )
    pad_width = max(len(s) for s in STATES)
    prefix = state.ljust(pad_width) + "  "

    if state == "WORKING":
        age = age_of(now, activity)  # activity is numeric here
        base = f"last activity {age}s ago"
        return prefix + (f"{base} ({doing})" if doing else base)

    if state == "QUIET":
        if activity is None or not _is_number(activity):
            return prefix + "no activity yet, but the process is alive"
        age = age_of(now, activity)
        return prefix + f"no activity for {age}s, but the process is alive"

    # state == "DEAD"
    if alive is False:
        reason = "its process is gone; it will never finish - resend"
    else:
        reason = "started before this engine; it will never finish - resend"
    return prefix + reason
