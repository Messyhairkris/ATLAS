"""Night shift: sort the day's failed crew jobs into categories and signatures."""

import re

CATEGORIES = ("provider", "stopped", "harness", "ceiling", "mechanical", "gate",
              "stuck", "unknown")
PROVIDER_MARKERS = ("HTTPStatusError", "ReadTimeout", "ConnectTimeout", "ConnectError",
                    "RemoteProtocolError", "504 Gateway", "502 Bad Gateway",
                    "503 Service", "429 Too Many")
CEILING_STOPS = ("budget_requests", "budget_tokens", "output_truncated", "empty_replies",
                 "thinking_cut_off")
STUCK_STOPS = ("no_progress", "no_change", "loop_repeat", "contract_abandoned")
MECHANICAL_RUNGS = ("frontmatter", "ascii", "quirks")
CUT_MARKERS = (": ", ", e.g.", " (")
ADVICE = {
    "provider": "the member's endpoint failed; relay or wait, nothing to fix in the work",
    "stopped": "stopped by a person; nothing to fix",
    "harness": "our harness raised an error; read the traceback in the job",
    "ceiling": "our budget ended the job; check the member's ceilings before blaming them",
    "mechanical": "a format miss a program can repair; candidate for a zero-token fixer",
    "gate": "a gate refused the content; needs a reader (model error or contract wording)",
    "stuck": "the member looped without progress; rescope the task or relay it sooner",
    "unknown": "failed with no recorded reason; read the job",
}


def head(text):
    """A short, stable label for a detail or error text."""
    line = re.sub(r"\d+", "N", str(text).split("\n", 1)[0])
    cuts = [i for i in (line.find(m, 20) for m in CUT_MARKERS) if i != -1]
    if cuts:
        line = line[:min(cuts)]
    return line.strip()[:60].rstrip()


def classify(job):
    """(category, signature) findings for one job; [] unless it failed."""
    if job.get("status") != "failed":
        return []
    task_type = job.get("task_type") or "?"
    member = job.get("assigned_to") or "?"
    result = job.get("result") or {}
    error = str(result.get("error") or "")
    if error:
        if error.startswith("stopped by the PA"):
            return [("stopped", f"{task_type}|stopped")]
        if any(marker in error for marker in PROVIDER_MARKERS):
            return [("provider", f"provider|{member}")]
        return [("harness", f"{task_type}|error|{head(error)}")]
    stop = str(result.get("stop_reason") or "")
    if stop in CEILING_STOPS:
        return [("ceiling", f"{task_type}|ceiling|{stop}|{member}")]
    findings = []
    for step in result.get("steps") or []:
        if step.get("ok"):
            continue
        rung = str(step.get("rung") or "?")
        label = head(step.get("detail") or "")
        mechanical = rung in MECHANICAL_RUNGS or (
            rung == "output" and label.startswith("bad output paths"))
        findings.append(("mechanical" if mechanical else "gate",
                         f"{task_type}|{rung}|{label}"))
    if findings:
        return findings
    if stop in STUCK_STOPS:
        return [("stuck", f"{task_type}|stuck|{stop}|{member}")]
    return [("unknown", f"{task_type}|unknown")]


def group(jobs, threshold=3):
    """One entry per (category, signature), most important first."""
    groups = {}
    for job in jobs:
        for category, signature in classify(job):
            entry = groups.setdefault((category, signature), {
                "category": category, "signature": signature, "count": 0,
                "members": [], "job_ids": []})
            entry["count"] += 1
            member = job.get("assigned_to") or "?"
            if member not in entry["members"]:
                entry["members"].append(member)
            job_id = job.get("task_id") or "?"
            if job_id not in entry["job_ids"]:
                entry["job_ids"].append(job_id)
    out = []
    for entry in groups.values():
        entry["members"] = sorted(entry["members"])
        entry["candidate"] = entry["category"] == "mechanical" and entry["count"] >= threshold
        out.append(entry)
    out.sort(key=lambda e: (CATEGORIES.index(e["category"]), -e["count"], e["signature"]))
    return out


def advice(category):
    """One line on what a category means for the morning review."""
    return ADVICE.get(category, ADVICE["unknown"])
