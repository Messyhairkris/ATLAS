"""Roster organ: Performance Profile + Autonomy Stage per (persona, task_type).

Stages (vault: Autonomy Stages): Observe -> Checkpoint -> Supervised ->
Autonomous. Observe and Checkpoint need a reviewer to approve every output;
Supervised and Autonomous auto-apply outputs that pass the gates (Supervised
jobs still land in the review inbox as notices).

Hard rules, enforced in promote(): stages are never skipped, and autonomy is
never raised after a failure. Promotion happens ONLY through the CLI
(`python -m crew promote ...`), which Kris runs. No MCP tool can promote, so
an AI teammate can never raise its own autonomy. The roster only SUGGESTS.
"""

import json
import statistics
import threading
from pathlib import Path
from typing import Optional

from .config import Config, CrewError
from .store import now_iso

STAGES = ["Observe", "Checkpoint", "Supervised", "Autonomous"]
AUTO_APPLY = {"Supervised", "Autonomous"}
HISTORY = 20
PROMOTE_AFTER = 5          # consecutive clean outcomes to suggest promotion

_lock = threading.Lock()


class Roster:
    def __init__(self, cfg: Config):
        self.path = Path(cfg.state_home) / "roster.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _blank() -> dict:
        return {"stage": STAGES[0], "samples": 0, "gate_passes": 0,
                "first_try_passes": 0, "approved": 0, "revised": 0,
                "rejected": 0, "requests": [], "tokens": [], "history": [],
                "stage_changed": now_iso()}

    def profile(self, persona: str, task_type: str) -> dict:
        return self._read().get(persona, {}).get(task_type) or self._blank()

    def stage(self, persona: str, task_type: str) -> str:
        return self.profile(persona, task_type)["stage"]

    def _update(self, persona: str, task_type: str, fn) -> dict:
        with _lock:
            data = self._read()
            prof = data.setdefault(persona, {}).setdefault(task_type, self._blank())
            fn(prof)
            prof["history"] = prof["history"][-HISTORY:]
            prof["requests"] = prof["requests"][-HISTORY:]
            prof["tokens"] = prof["tokens"][-HISTORY:]
            self._write(data)
            return prof

    def record_run(self, persona: str, task_type: str, job_id: str,
                   passed: bool, first_try: bool, requests: int, tokens: int) -> dict:
        def fn(p):
            p["samples"] += 1
            p["gate_passes"] += int(passed)
            p["first_try_passes"] += int(passed and first_try)
            p["requests"].append(requests)
            p["tokens"].append(tokens)
            p["history"].append({"job": job_id, "outcome": "gates_passed" if passed
                                 else "gates_failed", "ts": now_iso()})
        return self._update(persona, task_type, fn)

    def record_review(self, persona: str, task_type: str, job_id: str,
                      decision: str) -> dict:
        key = {"approve": "approved", "revise": "revised", "reject": "rejected"}[decision]

        def fn(p):
            p[key] += 1
            p["history"].append({"job": job_id, "outcome": key, "ts": now_iso()})
        return self._update(persona, task_type, fn)

    def suggestion(self, persona: str, task_type: str) -> Optional[str]:
        p = self.profile(persona, task_type)
        i = STAGES.index(p["stage"])
        if i == len(STAGES) - 1:
            return None
        recent = [h["outcome"] for h in p["history"]][-PROMOTE_AFTER * 2:]
        clean = 0
        for outcome in reversed(recent):
            if outcome in ("gates_failed", "revised", "rejected") \
                    or outcome.startswith("stage:"):
                break
            if outcome == "approved" or (outcome == "gates_passed"
                                         and p["stage"] in AUTO_APPLY):
                clean += 1
        if clean >= PROMOTE_AFTER:
            return (f"eligible: {clean} clean outcomes in a row at {p['stage']}; "
                    f"Kris may run `python -m crew promote {persona} {task_type} "
                    f"{STAGES[i + 1]}`")
        return None

    def summary(self) -> dict:
        out = {}
        for persona, types in self._read().items():
            for tt, p in types.items():
                out.setdefault(persona, {})[tt] = {
                    "stage": p["stage"], "samples": p["samples"],
                    "gate_pass_rate": round(p["gate_passes"] / p["samples"], 2)
                    if p["samples"] else None,
                    "first_try_pass_rate": round(p["first_try_passes"] / p["samples"], 2)
                    if p["samples"] else None,
                    "approved": p["approved"], "revised": p["revised"],
                    "rejected": p["rejected"],
                    "median_requests": statistics.median(p["requests"]) if p["requests"] else None,
                    "median_tokens": statistics.median(p["tokens"]) if p["tokens"] else None,
                    "suggestion": self.suggestion(persona, tt)}
        return out

    def promote(self, persona: str, task_type: str, to_stage: str,
                by: str, force_demote: bool = False) -> dict:
        if to_stage not in STAGES:
            raise CrewError(f"stage must be one of {STAGES}")
        p = self.profile(persona, task_type)
        cur, new = STAGES.index(p["stage"]), STAGES.index(to_stage)
        if new > cur + 1:
            raise CrewError(f"stages are never skipped: {p['stage']} -> {to_stage}")
        if new > cur and p["history"] and p["history"][-1]["outcome"] in (
                "gates_failed", "revised", "rejected"):
            raise CrewError("autonomy is never raised right after a failure; "
                            "wait for a clean outcome")
        if new < cur and not force_demote:
            raise CrewError("demotion needs --demote")

        def fn(q):
            q["stage"] = to_stage
            q["stage_changed"] = now_iso()
            q["history"].append({"job": "-", "outcome": f"stage:{to_stage} by {by}",
                                 "ts": now_iso()})
        return self._update(persona, task_type, fn)
