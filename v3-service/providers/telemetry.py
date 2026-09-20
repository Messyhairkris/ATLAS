"""Per-call token/latency telemetry for the API harness.

Every provider-model chat call appends one JSONL record. The experiment
runner points ATLAS_TELEMETRY_FILE at the Obsidian lab notebook
(wiki/experiments/atlas-api-harness/runs/) so credit usage is reviewable
alongside the plan; the default is repo-local runs/telemetry.jsonl.

Ledger v2: runners tag calls with who/what they were for (run_id, duty,
task_id, attempt, role junior|senior) via ``context(...)``; every record
written inside the block carries those fields, so cost per accepted task
— all roles included — is a query over the log, not a reconstruction.
"""

import contextlib
import contextvars
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

_CONTEXT: contextvars.ContextVar = contextvars.ContextVar(
    "atlas_telemetry_context", default={})


def _telemetry_path() -> Path:
    override = os.environ.get("ATLAS_TELEMETRY_FILE")
    if override:
        return Path(override)
    return _REPO_ROOT / "runs" / "telemetry.jsonl"


@contextlib.contextmanager
def context(**fields: Any):
    """Tag every record written inside the block with ``fields``. Nests:
    inner blocks add to (and override) outer ones."""
    token = _CONTEXT.set({**_CONTEXT.get(), **fields})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def current_context() -> Dict[str, Any]:
    return dict(_CONTEXT.get())


def record(event: Dict[str, Any]) -> None:
    """Append event as one JSONL line. Never raises: telemetry must not be
    load-bearing for the pipeline it observes."""
    try:
        path = _telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {**_CONTEXT.get(), **event}
        event.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def summarize_usage(data: Dict[str, Any]) -> Dict[str, int]:
    """Flatten a chat-completions response usage block into the fields the
    experiment tracks."""
    usage = (data or {}).get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
        "completion_tokens": usage.get("completion_tokens", 0) or 0,
        "total_tokens": usage.get("total_tokens", 0) or 0,
    }


def cost_usd(pricing: Optional[Dict[str, Any]], prompt_tokens: int,
             completion_tokens: int) -> Optional[float]:
    """USD for one call from a providers.json pricing entry
    ({"in_per_mtok": x, "out_per_mtok": y}); None when unpriced, so an
    unknown price never masquerades as free."""
    if not pricing:
        return None
    p_in, p_out = pricing.get("in_per_mtok"), pricing.get("out_per_mtok")
    if p_in is None or p_out is None:
        return None
    return round((prompt_tokens * p_in + completion_tokens * p_out) / 1e6, 8)
