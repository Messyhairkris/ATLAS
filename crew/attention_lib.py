from __future__ import annotations

STATES = ("needs_attention", "finished", "working", "idle")
DEFAULT_QUIET_S = 120

def state_for(
    now: float | int,
    last_activity: float | int | None = None,
    last_read: float | int | None = None,
    running: bool = False,
    alive: bool | None = None,
    finished_at: float | int | None = None,
    quiet_s: float | int = DEFAULT_QUIET_S
) -> str:
    """Return conversation state based on activity and read status (rules 1-7)."""
    if running and alive is False:
        return "needs_attention"
    elif running and last_activity is None:
        return "working"
    elif running and (now - last_activity) < quiet_s:
        return "working"
    elif running:
        return "needs_attention"
    elif finished_at is not None and (last_read is None or finished_at > last_read):
        return "finished"
    elif last_activity is not None and (last_read is None or last_activity > last_read):
        return "needs_attention"
    else:
        return "idle"

def label(state: object) -> str:
    """Return human label for state, or 'idle' for unknown states."""
    if state == "needs_attention":
        return "needs attention"
    elif state in STATES:
        return state
    else:
        return "idle"

def folder_state(states: list[object] | None) -> str:
    """Return first matching state in priority order, or 'idle' for empty/unknown."""
    if states is None:
        return "idle"
    for state in STATES:
        if state in states:
            return state
    return "idle"
