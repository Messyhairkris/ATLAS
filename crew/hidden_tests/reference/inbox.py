"""Reference for inbox.py: the cards Kris lands on (PA-written)."""

from datetime import datetime

RANKS = {"question": 0, "decide": 1, "reminder": 2, "failed": 3, "stale_campaign": 4,
         "fixer": 5, "try": 6, "finished": 7, "read": 8}


def _after(when: str, seen_at: str) -> bool:
    return bool(when) and when > seen_at


def _title(job: dict) -> str:
    return job.get("title") or job["task_id"]


def _card(kind, title, detail, ref, when) -> dict:
    return {"kind": kind, "title": title, "detail": detail, "ref": ref, "when": when}


def cards(desk: list[dict], jobs: list[dict], campaigns: list[dict], fired: list[dict],
          night: dict | None, now: datetime, seen_at: str, stale_hours: int = 48) -> list[dict]:
    out = []
    for job in jobs:
        status, when = job.get("status"), job.get("finished_at") or ""
        question = job.get("question")
        if status == "review" and question and not job.get("asked"):
            detail = question["question"]
            if isinstance(question.get("options"), list) and question["options"]:
                detail += " | " + " / ".join(question["options"])
            out.append(_card("question", _title(job), detail, job["task_id"], when))
        elif status == "failed" and _after(when, seen_at):
            stop = (job.get("result") or {}).get("stop_reason") or "failed"
            out.append(_card("failed", _title(job), f"{job.get('assigned_to') or '?'}: {stop}",
                             job["task_id"], when))
        elif status in ("review", "completed") and _after(when, seen_at):
            out.append(_card("finished", _title(job),
                             f"{job.get('assigned_to') or '?'} - {status}", job["task_id"], when))
    for item in desk:
        if (item.get("decision") or "") == "" and item.get("state") != "closed":
            kind = item.get("kind") if item.get("kind") in ("decide", "try", "read") else "decide"
            out.append(_card(kind, item.get("title", ""), "", item.get("item_id", ""),
                             item.get("added") or ""))
    for f in fired:
        if f.get("kind") == "reminder" and _after(f.get("fired_at") or "", seen_at):
            out.append(_card("reminder", f.get("title", ""), "at " + f["fired_at"][11:16],
                             f.get("id", ""), f["fired_at"]))
    for c in campaigns:
        if c.get("state") != "active":
            continue
        try:
            updated = datetime.fromisoformat(c.get("updated") or "")
        except ValueError:
            continue
        hours = (now - updated).total_seconds() / 3600
        if hours > stale_hours:
            out.append(_card("stale_campaign", c.get("name", ""), f"no change for {int(hours)} h",
                             c.get("name", ""), c["updated"]))
    if night is not None and _after(night.get("at") or "", seen_at):
        for f in night.get("fixer_candidates") or []:
            out.append(_card("fixer", f.get("signature", ""),
                             f"{f.get('count')} failures, e.g. {f.get('example_job')}",
                             f.get("example_job", ""), night["at"]))
    out.sort(key=lambda c: c["title"])
    out.sort(key=lambda c: c["when"], reverse=True)
    out.sort(key=lambda c: RANKS[c["kind"]])
    return out


def counts(cards: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cards:
        out[c["kind"]] = out.get(c["kind"], 0) + 1
    return out
