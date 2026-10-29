"""Reference for contracts/compactlib.md. The pure logic of the chat compact."""

from __future__ import annotations

import json
from typing import Any, Dict, List

STAGE_ORDER = ("none", "light", "medium", "heavy", "critical")
DEFAULT_STAGES = {"light": 0.60, "medium": 0.75, "heavy": 0.85, "critical": 0.95}
REASONING_KEEP = 500
TOOL_RESULT_KEEP = 2000
MESSAGE_KEEP = 10000


def _number(value: Any) -> float:
    """A real number (bool excluded), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def stages_from(config: Any) -> Dict[str, float]:
    """The four thresholds from crew/context.json's `stages`; the defaults for anything missing."""
    out = dict(DEFAULT_STAGES)
    block = config.get("stages") if isinstance(config, dict) else None
    if isinstance(block, dict):
        for name in DEFAULT_STAGES:
            value = _number(block.get(name))
            if value is not None:
                out[name] = float(value)
    return out


def stage_of(fraction: float, stages: Dict[str, float]) -> str:
    """The highest stage reached (>= counts); "none" below the light threshold."""
    reached = "none"
    given = stages if isinstance(stages, dict) else {}
    for name in STAGE_ORDER[1:]:
        value = _number(given.get(name))
        if value is not None and fraction >= value:
            reached = name
    return reached


def _int(value: Any) -> int:
    number = _number(value)
    return int(number) if number is not None else 0


def context_used(message: Any) -> int:
    """tokens.input + tokens.cache.read for one message (the same the meter reads)."""
    if not isinstance(message, dict):
        return 0
    tokens = message.get("tokens")
    if not isinstance(tokens, dict):
        return 0
    cache = tokens.get("cache")
    read = cache.get("read") if isinstance(cache, dict) else 0
    return _int(tokens.get("input")) + _int(read)


def _finished(message: Any) -> bool:
    """An assistant message that stopped: its `time` carries a `completed`."""
    time = message.get("time")
    return isinstance(time, dict) and "completed" in time


def newest_fill(messages: Any) -> int:
    """The newest finished assistant message's context_used; 0 when there is none."""
    if not isinstance(messages, list):
        return 0
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if not _finished(message):
            continue
        used = context_used(message)
        if used > 0:
            return used
    return 0


def truncate(text: Any, keep: int) -> str:
    """`text` unchanged when short enough; otherwise its first `keep` characters and a marker."""
    if not isinstance(text, str):
        return ""
    if len(text) <= keep:
        return text
    return text[:keep] + f"\n...[trimmed: {len(text)} chars, kept {keep}]"


def summary_input(messages: Any, template: Any) -> str:
    """The template, then one trimmed block per message (tool names and inputs kept)."""
    blocks: List[str] = []
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role") if isinstance(message.get("role"), str) else "assistant"
            lines = [f"## {role}"]
            lines.append(truncate(message.get("text", ""), MESSAGE_KEEP))
            reasoning = truncate(message.get("reasoning", ""), REASONING_KEEP)
            if reasoning:
                lines.append(f"reasoning: {reasoning}")
            for tool in message.get("tools") or []:
                if not isinstance(tool, dict):
                    continue
                name = tool.get("name", "")
                inp = json.dumps(tool.get("input"), sort_keys=True)
                lines.append(f"tool {name}({inp})")
            for result in message.get("results") or []:
                if not isinstance(result, dict):
                    continue
                name = result.get("name", "")
                out = truncate(result.get("output", ""), TOOL_RESULT_KEEP)
                lines.append(f"result {name}: {out}")
            blocks.append("\n".join(line for line in lines if line))
    head = template.strip() if isinstance(template, str) and template.strip() else ""
    body = "\n".join(blocks)
    if head and body:
        return f"{head}\n\n{body}"
    return head or body
