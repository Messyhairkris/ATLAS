"""Reference implementation for the project_search.py contract (finding inside a project folder)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

STOPWORDS = ("the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are",
             "was", "were", "be", "been", "that", "this", "it", "its", "with", "from", "as")

_WORD = re.compile(r"[A-Za-z0-9_]+")


def terms(query) -> List[str]:
    """The query's words: lowercased, stopwords dropped, repeats dropped keeping the first."""
    if not isinstance(query, str) or not query:
        return []
    out: List[str] = []
    for word in _WORD.findall(query.lower()):
        if word and word not in STOPWORDS and word not in out:
            out.append(word)
    return out


def score(text: str, ts: List[str]) -> int:
    """How many distinct terms appear in text, compared case-insensitively."""
    if not ts:
        return 0
    low = (text or "").lower()
    return sum(1 for term in dict.fromkeys(ts) if term in low)


def snippet(text: str, ts: List[str], width: int = 160) -> str:
    """A one-line window of `width` characters around the earliest match, or "" when none."""
    flat = " ".join((text or "").split())
    if not ts or not flat:
        return ""
    positions = [flat.lower().find(term.lower()) for term in ts]
    found = [p for p in positions if p >= 0]
    if not found:
        return ""
    if len(flat) <= width:
        return flat
    start = max(0, min(found) - width // 3)
    end = min(len(flat), start + width)
    start = max(0, end - width)
    out = flat[start:end]
    if start > 0:
        out = "..." + out
    if end < len(flat):
        out = out + "..."
    return out


def rank(docs: List[Dict[str, Any]], ts: List[str], limit: int = 20) -> List[Dict[str, Any]]:
    """The matching docs, best first: score descending, then id ascending; at most `limit`."""
    if limit <= 0:
        return []
    hits: List[Dict[str, Any]] = []
    for doc in docs or []:
        text = doc.get("text") or ""
        got = score(text, ts)
        if got:
            hits.append({"id": doc.get("id"), "kind": doc.get("kind") or "", "score": got,
                         "snippet": snippet(text, ts)})
    hits.sort(key=lambda h: (-h["score"], str(h["id"])))
    return hits[:limit]
