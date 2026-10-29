"""compactlib.py - pure logic for chat compact."""

from __future__ import annotations

import json
from typing import Any, Mapping

STAGE_ORDER = ("none", "light", "medium", "heavy", "critical")
DEFAULT_STAGES = {"light": 0.60, "medium": 0.75, "heavy": 0.85, "critical": 0.95}
REASONING_KEEP = 500
TOOL_RESULT_KEEP = 2000
MESSAGE_KEEP = 10000


def _is_number(val: Any) -> bool:
    """Return True for int/float that is not a bool."""
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def stages_from(config: object) -> dict:
    """Return stage thresholds, overriding defaults with valid numbers."""
    result: dict[str, float] = dict(DEFAULT_STAGES)
    if isinstance(config, Mapping):
        stages = config.get("stages")
        if isinstance(stages, Mapping):
            for key in DEFAULT_STAGES:
                val = stages.get(key)
                if _is_number(val):
                    result[key] = float(val)
    return result


def stage_of(fraction: float, stages: dict) -> str:
    """Highest stage whose threshold is reached (>=)."""
    best = "none"
    for stage in STAGE_ORDER[1:]:
        thr = stages.get(stage)
        if _is_number(thr) and fraction >= float(thr):
            best = stage
    return best


def context_used(message: object) -> int:
    """Calculate tokens.input + tokens.cache.read, handling missing data."""
    if not isinstance(message, Mapping):
        return 0
    tokens = message.get("tokens")
    if not isinstance(tokens, Mapping):
        return 0
    inp = tokens.get("input")
    if not _is_number(inp):
        inp_val = 0
    else:
        inp_val = int(inp)
    cache = tokens.get("cache")
    if isinstance(cache, Mapping):
        read = cache.get("read")
        if not _is_number(read):
            read_val = 0
        else:
            read_val = int(read)
    else:
        read_val = 0
    return inp_val + read_val


def newest_fill(messages: object) -> int:
    """Context used by the newest finished assistant message with non-zero usage."""
    if not isinstance(messages, list):
        return 0
    for msg in reversed(messages):
        if (
            isinstance(msg, Mapping)
            and msg.get("role") == "assistant"
            and isinstance(msg.get("time"), Mapping)
            and "completed" in msg["time"]
        ):
            used = context_used(msg)
            if used > 0:
                return used
    return 0


def truncate(text: object, keep: int) -> str:
    """Cut text to keep characters, adding a trimmed marker when shortened."""
    if not isinstance(text, str):
        return ""
    if len(text) <= keep:
        return text
    marker = f"\n...[trimmed: {len(text)} chars, kept {keep}]"
    return text[:keep] + marker


def summary_input(messages: object, template: object) -> str:
    """Render a compact summary of messages, optionally prefixed by a template."""
    # Prepare template
    tmpl = template if isinstance(template, str) else ""
    tmpl = tmpl.strip()
    # Prepare message blocks
    blocks: list[str] = []
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, Mapping):
                continue
            role = str(msg.get("role", "assistant"))
            lines: list[str] = [f"## {role}"]
            # Text
            txt = msg.get("text")
            txt_cut = truncate(txt, MESSAGE_KEEP) if isinstance(txt, str) else ""
            if txt_cut:
                lines.append(txt_cut)
            # Reasoning
            reasoning = msg.get("reasoning")
            if isinstance(reasoning, str):
                reasoning_cut = truncate(reasoning, REASONING_KEEP)
                if reasoning_cut:
                    lines.append(f"reasoning: {reasoning_cut}")
            # Tools
            tools = msg.get("tools")
            if isinstance(tools, list):
                for tool in tools:
                    if not isinstance(tool, Mapping):
                        continue
                    name = tool.get("name")
                    inp = tool.get("input")
                    if name is None:
                        continue
                    inp_json = json.dumps(inp, sort_keys=True)
                    lines.append(f"tool {name}({inp_json})")
            # Results
            results = msg.get("results")
            if isinstance(results, list):
                for res in results:
                    if not isinstance(res, Mapping):
                        continue
                    name = res.get("name")
                    out = res.get("output")
                    if name is None:
                        continue
                    out_cut = truncate(out, TOOL_RESULT_KEEP) if isinstance(out, str) else ""
                    lines.append(f"result {name}: {out_cut}")
            # Drop empty lines inside block
            block = "\n".join(line for line in lines if line != "")
            blocks.append(block)
    # Assemble final output
    if not tmpl and not blocks:
        return ""
    if tmpl and blocks:
        return tmpl + "\n\n" + "\n\n".join(blocks)
    if tmpl:
        return tmpl
    return "\n\n".join(blocks)
