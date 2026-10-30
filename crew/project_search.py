"""Pure project search utilities."""

from __future__ import annotations

import re
from typing import Any, Dict, List

# Minimal stop-word list; can be extended.
STOPWORDS = (
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "that",
    "this",
    "it",
    "its",
    "with",
    "from",
    "as",
)


def terms(query: str | None) -> List[str]:
    """Extract distinct lower-cased query terms, dropping stop-words."""
    if not isinstance(query, str) or not query:
        return []
    words = re.findall(r"[A-Za-z0-9_]+", query)
    result: List[str] = []
    seen: set[str] = set()
    for w in words:
        w_low = w.lower()
        if w_low in STOPWORDS or not w_low:
            continue
        if w_low not in seen:
            seen.add(w_low)
            result.append(w_low)
    return result


def score(text: str, ts: List[str]) -> int:
    """Count distinct terms from *ts* that appear in *text* (case-insensitive)."""
    if not ts:
        return 0
    lower = text.lower()
    distinct_terms = {term.lower() for term in ts if term}
    return sum(1 for term in distinct_terms if term in lower)


def snippet(text: str, ts: List[str], width: int = 160) -> str:
    """One-line window around the earliest match, trimmed to *width*."""
    if not ts:
        return ""
    line = " ".join(text.split())
    # check presence of any term
    if not any(term.lower() in line.lower() for term in ts):
        return ""
    if len(line) <= width:
        return line
    lower_line = line.lower()
    earliest = len(line)
    for term in ts:
        idx = lower_line.find(term.lower())
        if 0 <= idx < earliest:
            earliest = idx
    if earliest == len(line):
        return ""
    start = max(0, earliest - width // 3)
    end = min(len(line), start + width)
    start = max(0, end - width)
    window = line[start:end]
    if start > 0:
        window = "..." + window
    if end < len(line):
        window = window + "..."
    return window


def _make_hit(doc: Dict[str, Any], sc: int, snip: str) -> Dict[str, Any]:
    """Create a hit dict from a document."""
    return {
        "id": doc.get("id", ""),
        "kind": doc.get("kind", ""),
        "score": sc,
        "snippet": snip,
    }


def rank(
    docs: List[Dict[str, Any]], ts: List[str], limit: int = 20
) -> List[Dict[str, Any]]:
    """Return top hits sorted by score desc then id asc, limited to *limit*."""
    if limit <= 0:
        return []
    hits: List[Dict[str, Any]] = []
    for doc in docs:
        sc = score(doc.get("text", ""), ts)
        if sc <= 0:
            continue
        snip = snippet(doc.get("text", ""), ts)
        hits.append(_make_hit(doc, sc, snip))
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    return hits[:limit]
