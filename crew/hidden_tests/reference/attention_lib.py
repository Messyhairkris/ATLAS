"""Reference implementation for the attention_lib.py contract (which conversations need you)."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

STATES = ("needs_attention", "finished", "working", "idle")
DEFAULT_QUIET_S = 120

_LABELS = {"needs_attention": "needs attention", "finished": "finished", "working": "working",
           "idle": "idle"}


def state_for(now, last_activity=None, last_read=None, running=False, alive=None,
              finished_at=None, quiet_s: float = DEFAULT_QUIET_S) -> str:
    """The conversation's state, first rule to match (rules 1-7 of the contract)."""
    if running is True:
        if alive is False:
            return "needs_attention"
        if last_activity is None:
            return "working"
        if _age(now, last_activity) < quiet_s:
            return "working"
        return "needs_attention"
    if finished_at is not None and (last_read is None or _gt(finished_at, last_read)):
        return "finished"
    if last_activity is not None and (last_read is None or _gt(last_activity, last_read)):
        return "needs_attention"
    return "idle"


def label(state) -> str:
    """The phrase the indicator shows; anything unknown reads as idle."""
    return _LABELS.get(state, "idle")


def folder_state(states: Optional[Iterable[Any]]) -> str:
    """The folder's state: the first of the four that appears, else idle."""
    seen = set(states or [])
    for state in STATES:
        if state in seen:
            return state
    return "idle"


def _age(now, then) -> float:
    try:
        return float(now) - float(then)
    except (TypeError, ValueError):
        return float("inf")


def _gt(a, b) -> bool:
    try:
        return float(a) > float(b)
    except (TypeError, ValueError):
        return False
