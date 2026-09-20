"""Zero-token repairs applied to a submission BEFORE the gates see it.

Kris's point: a gate that fails a report over "97.73 s" versus "97.73s", or a
one-letter typo in a filename, is spending a model request to fix something a
linter can fix for nothing. So the harness corrects near-misses itself and
records every correction, which is honest (the review shows what was changed)
and cheap (no extra request).

What it will fix:
  * typography: curly quotes, en/em dashes, non-breaking hyphens and spaces,
    ellipsis characters -> their ASCII equivalents
  * a quoted name that is a near-match for a real name in the run log
  * a citation path that is a near-match for something actually observed

What it will NOT fix: anything that changes meaning. A missing citation, an
absent-claim without evidence, a wrong number, a missing frontmatter field:
those stay failures, because guessing the author's intent is how a summary
becomes confidently wrong.
"""

import difflib
import re
from typing import Dict, List, Tuple

TYPOGRAPHY = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "…": "...", "×": "x", "→": "->", "≥": ">=", "≤": "<=",
}
NEAR = 0.86            # below this it is a different name, not a typo
NAME_TOKEN = re.compile(r'"([^"\n]{3,60})"|`([^`\n]{3,60})`')
CITE = re.compile(r"\[\[?src:\s*([^\]]+?)\s*\]\]?")


def _normalize_typography(text: str) -> Tuple[str, int]:
    fixed = 0
    for bad, good in TYPOGRAPHY.items():
        if bad in text:
            fixed += text.count(bad)
            text = text.replace(bad, good)
    return text, fixed


def _log_vocabulary(run_log: str) -> List[str]:
    """Names worth matching against: values of "control"/"test"/"file" fields
    and quoted strings in the run output."""
    vocab = set(re.findall(r'"(?:control|test|file|name)"\s*:\s*"([^"]{2,60})"', run_log))
    vocab |= set(re.findall(r'"([^"\n]{3,60})"', run_log))
    vocab |= set(re.findall(r"\b([A-Za-z][\w .\-]{2,40}\.py)\b", run_log))
    return sorted(v.strip() for v in vocab if v.strip())


def _closest(needle: str, hay: List[str]) -> str:
    match = difflib.get_close_matches(needle, hay, n=1, cutoff=NEAR)
    return match[0] if match else ""


def apply(files: Dict[str, str], run_log: str, toolbox) -> Tuple[Dict[str, str], List[str]]:
    """Returns (files, notes). Mutates nothing the caller owns."""
    notes: List[str] = []
    vocab = _log_vocabulary(run_log) if run_log else []
    evidence = list((toolbox.evidence.seen if toolbox else {}) or {})
    display = {}
    for key in evidence:
        try:
            display[toolbox.display(__import__("pathlib").Path(key))] = key
        except Exception:                                    # noqa: BLE001
            continue
    cite_vocab = sorted(set(display) | set(evidence))

    out = {}
    for name, text in files.items():
        text, typo = _normalize_typography(text)
        if typo:
            notes.append(f"{name}: normalized {typo} typographic character(s)")

        squash = re.sub(r"\s+", "", run_log)
        for m in NAME_TOKEN.finditer(text):
            quoted = (m.group(1) or m.group(2) or "").strip()
            if not quoted or quoted in run_log or re.sub(r"\s+", "", quoted) in squash:
                continue
            if re.match(r"^\d+\s+(failed|passed|error)|^\w+:\s", quoted):
                continue
            best = _closest(quoted, vocab)
            if best and best != quoted:
                text = text.replace(quoted, best)
                notes.append(f"{name}: corrected name {quoted!r} -> {best!r}")

        for cited in set(CITE.findall(text)):
            bare = cited.split("#")[0].strip()
            if toolbox and toolbox.evidence_key(bare):
                continue
            best = _closest(bare, cite_vocab)
            if best and best != bare:
                text = text.replace(cited, best)
                notes.append(f"{name}: corrected citation {bare!r} -> {best!r}")
        out[name] = text
    return out, notes
