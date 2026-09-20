"""Attempt bookkeeping shared by the duty runners.

Three rules the runners used to get wrong (SIGNAL LOST P6: a repair round
emitted a partial file set and replaced a better attempt):

1. BEST, not last — an attempt is kept only if it scores at least as well as
   every earlier one; a pass is never replaced. Revision rounds degrade
   correct code often enough (arXiv 2607.24604: 82% -> 67% after a forced
   second revision) that "latest" is the wrong default.
2. Carry forward — a repair that re-emits only some files is merged OVER the
   best attempt's files instead of replacing the whole set.
3. Stop useless loops — identical output to an earlier attempt, or two
   repairs in a row that do not beat the best score, end the loop instead of
   spending more requests.
"""

import hashlib
import json
from typing import Dict, Iterable, List, Optional, Tuple

NO_PROGRESS_LIMIT = 2


def files_hash(files: Dict[str, str]) -> str:
    """Order-independent fingerprint of an emitted file set."""
    blob = json.dumps(sorted(files.items()), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def score(steps: Iterable[dict]) -> Tuple[int, int]:
    """(gates passed, -gates failed). Higher is better; tuples compare in
    order, so fewer failures break ties between equal pass counts."""
    steps = list(steps)
    ok = sum(1 for s in steps if s.get("ok"))
    return ok, -(len(steps) - ok)


def failing_files(steps: Iterable[dict]) -> List[str]:
    return sorted({s["file"] for s in steps
                   if not s.get("ok") and s.get("file")})


def merge_carry(base: Dict[str, str], new: Dict[str, str]) -> Dict[str, str]:
    """New emissions win; files the repair did not re-emit are carried."""
    return {**base, **new}


class AttemptTracker:
    """Feed each graded attempt to ``add``; read ``best`` and ``stop_reason``.

    ``add`` returns True when the loop should continue (not passed, not
    stopped by a guard)."""

    def __init__(self, no_progress_limit: int = NO_PROGRESS_LIMIT):
        self.no_progress_limit = no_progress_limit
        self.best: Optional[dict] = None
        self.history: List[dict] = []
        self.stop_reason: Optional[str] = None
        self._seen = set()
        self._stale = 0

    def add(self, attempt: int, files: Dict[str, str], steps: List[dict],
            passed: bool, **extra) -> bool:
        fp = files_hash(files)
        rec = {"attempt": attempt, "files": files, "steps": steps,
               "passed": bool(passed), "score": score(steps),
               "hash": fp, **extra}
        self.history.append(rec)
        duplicate = fp in self._seen
        self._seen.add(fp)

        improved = self.best is None or (
            not self.best["passed"]
            and (rec["passed"] or rec["score"] > self.best["score"]))
        if improved:
            self.best = rec
            self._stale = 0
        else:
            self._stale += 1

        if rec["passed"]:
            self.stop_reason = "passed"
            return False
        if duplicate:
            self.stop_reason = "no_change"      # identical to an earlier try
            return False
        if self._stale >= self.no_progress_limit:
            self.stop_reason = "no_progress"
            return False
        return True

    def summary(self) -> dict:
        return {"best_attempt": self.best["attempt"] if self.best else None,
                "stop_reason": self.stop_reason,
                "scores": [list(r["score"]) for r in self.history],
                "hashes": [r["hash"] for r in self.history]}
