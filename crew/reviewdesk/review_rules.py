"""review_rules: as accepted from the Crew.

Written by Nemotron of the Crew, from the contract `contracts/tts_review_rules.md`, and accepted
only after passing tests it was never allowed to read (campaign review-desk + revision).

Vendored into this project on 2026-09-20. The ONLY change made on the way in was the
import rewrite listed in PROVENANCE.md; the logic is exactly what was accepted.
"""

# Contract: review_rules.py - what a review must say before it counts

DECISIONS = ("approve", "reject", "question", "defer")
NEEDS_NOTE = ("reject", "question", "defer")
MIN_NOTE_CHARS = 12


def validate(decision: str, note: str) -> list:
    """Return problems about a review; empty means acceptable."""
    if decision not in DECISIONS:
        return [f"decision '{decision}' is not one of {DECISIONS}"]
    if decision in NEEDS_NOTE and len(note.strip()) < MIN_NOTE_CHARS:
        return [f"a {decision} needs a note of at least {MIN_NOTE_CHARS} characters saying what is wrong"]
    return []


def is_complete(item: dict) -> bool:
    """True when a review has a decision and no validation problems."""
    decision = item.get("decision", "")
    note = item.get("note", "")
    return bool(decision) and not validate(decision, note)


def next_action(item: dict) -> str:
    """Return the next step for a review item."""
    decision = item.get("decision", "")
    note = item.get("note", "")
    if not decision:
        return "wait for the human"
    if decision == "approve":
        return "apply the work"
    if decision in NEEDS_NOTE:
        if len(note.strip()) < MIN_NOTE_CHARS:
            return "ask the human for a reason"
        if decision == "reject":
            return "revise the work using the note"
        if decision == "question":
            return "answer the question, then ask again"
        # decision == "defer"
        return "leave it queued"
    return "wait for the human"  # fallback, should not be reached


def summarize(items: list) -> dict:
    """Count reviews by status."""
    total = pending = approve = reject = question = defer = incomplete = 0
    for item in items:
        total += 1
        decision = item.get("decision", "")
        note = item.get("note", "")
        if not decision:
            pending += 1
        else:
            if decision == "approve":
                approve += 1
            elif decision == "reject":
                reject += 1
            elif decision == "question":
                question += 1
            elif decision == "defer":
                defer += 1
            if validate(decision, note):
                incomplete += 1
    return {
        "total": total,
        "pending": pending,
        "approve": approve,
        "reject": reject,
        "question": question,
        "defer": defer,
        "incomplete": incomplete,
    }


def agent_digest(items: list) -> dict:
    """Return what the agent needs to know about reviews."""
    needs_agent = False
    waiting_on_human = 0
    waiting_on_agent = []
    needs_human_again = []
    actions = {}
    for item in items:
        item_id = item.get("item_id")
        decision = item.get("decision", "")
        note = item.get("note", "")
        act = next_action(item)
        actions[item_id] = act
        if not decision:
            waiting_on_human += 1
        else:
            if is_complete(item):
                if decision in ("approve", "reject", "question"):
                    needs_agent = True
                    waiting_on_agent.append(item_id)
            else:
                needs_human_again.append(item_id)
    return {
        "needs_agent": needs_agent,
        "waiting_on_human": waiting_on_human,
        "waiting_on_agent": waiting_on_agent,
        "needs_human_again": needs_human_again,
        "actions": actions,
    }
