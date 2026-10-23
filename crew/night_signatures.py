"""night_signatures.py - sorting the day's failed crew jobs for the night shift.

Crew-built: Nemotron, campaign ns-signatures, 2026-10-23, accepted on attempt 1
(1 request) against crew/hidden_tests/test_night_signatures.py (24 tests). Contract:
crew/contracts/ns_signatures.md. Used by crew/runners/night_shift.py. Change it through
the contract and a crew job, not by hand.
"""
import re

CATEGORIES = ("provider", "stopped", "harness", "ceiling", "mechanical", "gate",
              "stuck", "unknown")

def head(text: str) -> str:
    """
    Extract a short, stable label from text following Rule H.
    """
    line = str(text).split('\n', 1)[0]
    line = re.sub(r'\d+', 'N', line)
    markers = [": ", ", e.g.", " ("]
    indices = [line.find(m, 20) for m in markers]
    valid_indices = [i for i in indices if i != -1]
    if valid_indices:
        cut = min(valid_indices)
        line = line[:cut]
    line = line.strip()
    if len(line) > 60:
        line = line[:60]
    line = line.rstrip()
    return line

def classify(job: dict) -> list[tuple[str, str]]:
    """
    Classify a job into findings following Rule C.
    """
    if job.get("status") != "failed":
        return []
    
    result = job.get("result", {})
    if not isinstance(result, dict):
        result = {}
    
    error = result.get("error", "")
    if error is None:
        error = ""
    error_str = str(error)
    
    if error_str:
        if error_str.startswith("stopped by the PA"):
            task_type = job.get("task_type", "?")
            return [("stopped", f"{task_type}|stopped")]
        
        provider_markers = [
            "HTTPStatusError", "ReadTimeout", "ConnectTimeout",
            "ConnectError", "RemoteProtocolError", "504 Gateway",
            "502 Bad Gateway", "503 Service", "429 Too Many"
        ]
        for marker in provider_markers:
            if marker in error_str:
                assigned_to = job.get("assigned_to", "?")
                if assigned_to is None:
                    assigned_to = "?"
                return [("provider", f"provider|{assigned_to}")]
        
        task_type = job.get("task_type", "?")
        return [("harness", f"{task_type}|error|{head(error_str)}")]
    
    stop_reason = result.get("stop_reason", "")
    if stop_reason is None:
        stop_reason = ""
    stop_reason_str = str(stop_reason)
    
    ceiling_stops = {"budget_requests", "budget_tokens", "output_truncated",
                     "empty_replies", "thinking_cut_off"}
    if stop_reason_str in ceiling_stops:
        task_type = job.get("task_type", "?")
        assigned_to = job.get("assigned_to", "?")
        if assigned_to is None:
            assigned_to = "?"
        return [("ceiling", f"{task_type}|ceiling|{stop_reason_str}|{assigned_to}")]
    
    steps = result.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    
    findings = []
    mechanical_rungs = {"frontmatter", "ascii", "quirks"}
    for step in steps:
        if not isinstance(step, dict):
            continue
        ok = step.get("ok")
        if ok:
            continue
        detail = step.get("detail", "")
        if detail is None:
            detail = ""
        label = head(detail)
        rung = step.get("rung", "?")
        if rung is None:
            rung = "?"
        if rung in mechanical_rungs or (rung == "output" and label.startswith("bad output paths")):
            category = "mechanical"
        else:
            category = "gate"
        task_type = job.get("task_type", "?")
        findings.append((category, f"{task_type}|{rung}|{label}"))
    
    if findings:
        return findings
    
    stuck_stops = {"no_progress", "no_change", "loop_repeat", "contract_abandoned"}
    if stop_reason_str in stuck_stops:
        task_type = job.get("task_type", "?")
        assigned_to = job.get("assigned_to", "?")
        if assigned_to is None:
            assigned_to = "?"
        return [("stuck", f"{task_type}|stuck|{stop_reason_str}|{assigned_to}")]
    
    task_type = job.get("task_type", "?")
    return [("unknown", f"{task_type}|unknown")]

def group(jobs: list[dict], threshold: int = 3) -> list[dict]:
    """
    Group findings from jobs following Rule G.
    """
    entries = {}
    for job in jobs:
        job_id = job.get("task_id", "?")
        if job_id is None:
            job_id = "?"
        findings = classify(job)
        for category, signature in findings:
            key = (category, signature)
            if key not in entries:
                entries[key] = {
                    "category": category,
                    "signature": signature,
                    "count": 0,
                    "members": set(),
                    "job_ids": [],
                    "candidate": False
                }
            entry = entries[key]
            entry["count"] += 1
            assigned_to = job.get("assigned_to", "?")
            if assigned_to is None:
                assigned_to = "?"
            entry["members"].add(assigned_to)
            if job_id not in entry["job_ids"]:
                entry["job_ids"].append(job_id)
    
    for entry in entries.values():
        entry["members"] = sorted(entry["members"])
        entry["candidate"] = (entry["category"] == "mechanical" and entry["count"] >= threshold)
    
    sorted_entries = sorted(
        entries.values(),
        key=lambda e: (
            CATEGORIES.index(e["category"]),
            -e["count"],
            e["signature"]
        )
    )
    return sorted_entries

def advice(category: str) -> str:
    """
    Return advice string for a category following Rule A.
    """
    advice_map = {
        "provider": "the member's endpoint failed; relay or wait, nothing to fix in the work",
        "stopped": "stopped by a person; nothing to fix",
        "harness": "our harness raised an error; read the traceback in the job",
        "ceiling": "our budget ended the job; check the member's ceilings before blaming them",
        "mechanical": "a format miss a program can repair; candidate for a zero-token fixer",
        "gate": "a gate refused the content; needs a reader (model error or contract wording)",
        "stuck": "the member looped without progress; rescope the task or relay it sooner",
        "unknown": "failed with no recorded reason; read the job"
    }
    return advice_map.get(category, advice_map["unknown"])
