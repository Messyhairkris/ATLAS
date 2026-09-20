"""review_index: as accepted from the Crew.

Written by Qwen of the Crew, from the contract `contracts/tts_review_index.md`, and accepted
only after passing tests it was never allowed to read (campaign review-desk + revision).

Vendored into this project on 2026-09-20. The ONLY change made on the way in was the
import rewrite listed in PROVENANCE.md; the logic is exactly what was accepted.
"""

# The module's own docstring, unchanged:
# """INI text for the review queue; merge never overwrites a human decision."""

import configparser

STATES = ("pending", "decided", "answered", "closed")
DECISIONS = ("approve", "reject", "question", "defer")
FIELDS = ("item_id", "title", "path", "origin", "state", "decision", "note",
          "anchor", "decided_at")


def new_item(item_id: str, title: str, path: str, origin: str = "",
             anchor: str = "") -> dict:
    """New record starts pending; empty item_id or title is a ValueError."""
    if not item_id or not title:
        raise ValueError("item_id and title must be non-empty")
    return {
        "item_id": item_id,
        "title": title,
        "path": path,
        "origin": origin,
        "state": "pending",
        "decision": "",
        "note": "",
        "anchor": anchor,
        "decided_at": "",
    }


def render(items: list) -> str:
    """One INI section per item in FIELDS order; notes keep newlines as \\n."""
    for item in items:
        if item.get("state") not in STATES:
            raise ValueError("state must be one of STATES")
        decision = item.get("decision", "")
        if decision and decision not in DECISIONS:
            raise ValueError("decision must be empty or one of DECISIONS")
    chunks = []
    for item in items:
        lines = [f"[{item.get('item_id', '')}]"]
        for key in FIELDS[1:]:
            value = item.get(key, "")
            if key == "note":
                value = value.replace("\n", "\\n")
            lines.append(f"{key} = {value}")
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def parse(text: str) -> list:
    """Inverse of render; unreadable text is a ValueError, missing keys empty."""
    if not text:
        return []
    parser = configparser.ConfigParser(interpolation=None,
                                       inline_comment_prefixes=None)
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ValueError(str(exc)) from exc
    items = []
    for section in parser.sections():
        record = {"item_id": section}
        for key in FIELDS[1:]:
            record[key] = parser.get(section, key, fallback="")
        if not record["state"]:
            record["state"] = "pending"
        record["note"] = record["note"].replace("\\n", "\n")
        items.append(record)
    return items


def merge(existing: list, incoming: list) -> list:
    """New items are added; an existing non-empty decision always wins."""
    result = [dict(item) for item in existing]
    by_id = {item["item_id"]: item for item in result}
    for inc in incoming:
        cur = by_id.get(inc["item_id"])
        if cur is None:
            cur = dict(inc)
            result.append(cur)
            by_id[inc["item_id"]] = cur
        elif not cur.get("decision"):
            for key in FIELDS[1:]:
                value = inc.get(key, "")
                if value:
                    cur[key] = value
    return result


def pending(items: list) -> list:
    """Records whose state is pending, in order."""
    return [item for item in items if item.get("state") == "pending"]


def find(items: list, item_id: str) -> dict | None:
    """The record with that item_id, or None."""
    for item in items:
        if item.get("item_id") == item_id:
            return item
    return None
