"""The end-of-campaign scorecard.

Kris: "I would like to see the performances of each team after the successful
completion of the project, or if failure prevents completion a breakdown why and
steps to improve our chances for future tasks."

So this reports both, from evidence the campaign could not fudge: the job store's
own records, the request and token counts from the ledger, and which gate failed.
Where it recommends something, it says which number the recommendation came from.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path
from typing import Dict, List

ACCEPTED, DEAD, ESCALATED = "accepted", "failed", "escalated"


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.0f}%" if whole else "n/a"


def _gate_counts(tasks: Dict[str, dict]) -> collections.Counter:
    c = collections.Counter()
    for t in tasks.values():
        for attempt in t.get("failed_gates", []):
            for line in attempt:
                c[str(line).split(":")[0].strip()] += 1
    return c


def _team_rows(tasks: Dict[str, dict]) -> List[dict]:
    by_team: Dict[str, dict] = {}
    for t in tasks.values():
        row = by_team.setdefault(t["team"], {
            "team": t["team"], "members": set(), "tasks": 0, "accepted": 0,
            "failed": 0, "attempts": 0, "first_try": 0, "requests": 0,
            "tokens": 0, "seconds": 0.0, "escalations": 0})
        row["members"].add(t["member"])
        row["tasks"] += 1
        row["attempts"] += t["attempts"]
        row["requests"] += t["requests"]
        row["tokens"] += t["tokens"]
        row["seconds"] += t["seconds"]
        row["escalations"] += t["escalations"]
        if t["state"] == ACCEPTED:
            row["accepted"] += 1
            if t["attempts"] == 1:
                row["first_try"] += 1
        elif t["state"] == DEAD:
            row["failed"] += 1
    return sorted(by_team.values(), key=lambda r: (-r["accepted"], r["requests"]))


def campaign_report(campaign) -> dict:
    tasks = campaign.tasks
    total = len(tasks)
    accepted = [t for t in tasks.values() if t["state"] == ACCEPTED]
    dead = [t for t in tasks.values() if t["state"] == DEAD]
    unstarted = [t for t in tasks.values() if t["state"] not in (ACCEPTED, DEAD)]
    rows = _team_rows(tasks)
    gates = _gate_counts(tasks)
    requests = sum(t["requests"] for t in tasks.values())
    tokens = sum(t["tokens"] for t in tasks.values())
    seconds = sum(t["seconds"] for t in tasks.values())
    first_try = sum(1 for t in accepted if t["attempts"] == 1)

    data = {
        "campaign": campaign.name,
        "goal": campaign.spec.get("goal", ""),
        "outcome": ("complete" if len(accepted) == total else
                    "partial" if accepted else "failed"),
        "tasks": total, "accepted": len(accepted), "failed": len(dead),
        "not_started": len(unstarted),
        "first_try_accepts": first_try,
        "requests": requests, "tokens": tokens, "wall_seconds": round(seconds, 1),
        "requests_per_accepted": round(requests / len(accepted), 1) if accepted else None,
        "teams": [{**r, "members": sorted(r["members"])} for r in rows],
        "failed_gate_counts": dict(gates.most_common()),
        "tasks_detail": {i: {k: t[k] for k in
                            ("state", "kind", "team", "member", "attempts",
                             "requests", "tokens", "seconds", "escalations",
                             "failed_gates", "job_ids")}
                         for i, t in tasks.items()},
    }

    lines = [f"# Campaign report: {campaign.name}", ""]
    if data["goal"]:
        lines += [f"**Goal:** {data['goal']}", ""]
    lines += [f"**Outcome: {data['outcome']}** - {len(accepted)} of {total} tasks "
              f"accepted, {len(dead)} failed, {len(unstarted)} never started.",
              f"{requests} requests, {tokens} tokens, "
              f"{seconds / 60:.1f} minutes of member time.", ""]
    if accepted:
        lines += [f"First-attempt acceptance: {first_try}/{len(accepted)} "
                  f"({_pct(first_try, len(accepted))}). "
                  f"{data['requests_per_accepted']} requests per accepted task.", ""]

    lines += ["## Teams", "",
              "| Team | Members | Tasks | Accepted | First try | Failed | "
              "Attempts | Requests | Tokens | Escalations | Minutes |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['team']} | {', '.join(sorted(r['members']))} | {r['tasks']} | "
            f"{r['accepted']} | {r['first_try']} | {r['failed']} | {r['attempts']} | "
            f"{r['requests']} | {r['tokens']} | {r['escalations']} | "
            f"{r['seconds'] / 60:.1f} |")
    lines.append("")

    lines += ["## Tasks", "",
              "| Task | Kind | Team | Member | State | Attempts | Requests | Minutes |",
              "|---|---|---|---|---|---|---|---|"]
    for tid, t in tasks.items():
        lines.append(f"| {tid} | {t['kind']} | {t['team']} | {t['member']} | "
                     f"{t['state']} | {t['attempts']} | {t['requests']} | "
                     f"{t['seconds'] / 60:.1f} |")
    lines.append("")

    if gates:
        lines += ["## What actually went wrong", "",
                  "Every failed attempt, grouped by what stopped it. A GATE name "
                  "(safety, api, hidden tests, tests green, no stubs) means the "
                  "work was judged and found wanting. A STOP REASON "
                  "(empty_replies, output_truncated, no_progress) means the "
                  "member never reached judgement at all - that is a budget or "
                  "task-size problem, not a quality one.", "",
                  "| Check | Times it stopped an attempt |", "|---|---|"]
        for gate, n in gates.most_common():
            lines.append(f"| {gate} | {n} |")
        lines.append("")

    if dead:
        lines += ["## Tasks that did not finish", ""]
        for t in dead:
            last = "; ".join(t["failed_gates"][-1]) if t["failed_gates"] else "unknown"
            lines += [f"### {t['team']} - {t['member']}: {t['kind']} "
                      f"({t['attempts']} attempts, {t['escalations']} escalations)",
                      f"Last failure: {last}", ""]

    lines += ["## What to change next time", ""] + _recommendations(data, gates)
    lines += ["", "## Evidence", "",
              f"- job store: `{campaign.crew.store.jobs_dir}`",
              f"- progress log: `{campaign.home / 'progress.log'}`",
              f"- live status: `{campaign.home / 'status.json'}`",
              f"- accepted modules: `{campaign.workspace}`", ""]
    return {"data": data, "markdown": "\n".join(lines)}


def _recommendations(data: dict, gates: collections.Counter) -> List[str]:
    """Concrete next steps, each tied to a number in this report."""
    out = []
    if data["outcome"] == "complete":
        out.append(f"- The campaign finished. Cost to beat next time: "
                   f"{data['requests']} requests for {data['accepted']} accepted "
                   f"tasks ({data['requests_per_accepted']} each).")
    if data["accepted"] and data["first_try_accepts"] == 0:
        out.append("- Nothing was accepted on the first attempt, so the contracts "
                   "are not yet self-sufficient. Add a worked example for each rule "
                   "a member got wrong; that is cheaper than a retry.")
    for gate, n in gates.most_common(3):
        if gate.startswith("hidden tests"):
            out.append(f"- The hidden tests caught {n} bad submission(s): the loop "
                       f"is working. Keep the tests; consider showing one example "
                       f"assertion in the contract for the rule most often missed.")
        elif gate.startswith("safety"):
            out.append(f"- {n} submission(s) tried to import or call something "
                       f"outside the allowlist. State the allowlist in the contract "
                       f"header, in one line, before the API.")
        elif gate.startswith("api"):
            out.append(f"- {n} submission(s) renamed part of the API. Put the exact "
                       f"signature block at the very top of the contract.")
        elif gate.startswith("no stubs"):
            out.append(f"- {n} submission(s) left a stub. Say plainly that a "
                       f"`pass` body is a failed task.")
        elif gate.startswith("tests green"):
            out.append(f"- {n} tester submission(s) disagreed with an accepted "
                       f"module. Read those: one of the two misread the contract, "
                       f"and that sentence needs rewriting.")
        elif gate == "empty_replies":
            out.append(f"- {n} attempt(s) ended in EMPTY replies: the member spent "
                       f"its whole output budget reasoning and never wrote an "
                       f"answer. That is a ceiling problem, not a contract "
                       f"problem. Raise `defaults.max_tokens_by_member` for that "
                       f"model (GLM-4.7-Flash needed 32768) rather than editing "
                       f"the contract.")
        elif gate == "output_truncated":
            out.append(f"- {n} attempt(s) were cut off mid-file. Raise that "
                       f"member's output ceiling, or split the module in two.")
        elif gate in ("no_change", "no_progress", "loop", "invalid_replies"):
            out.append(f"- {n} attempt(s) ended on a loop guard ('{gate}'): the "
                       f"member stopped making progress. Shrink the task before "
                       f"retrying it; another attempt at the same size usually "
                       f"repeats the same stall.")
        elif gate:
            out.append(f"- '{gate}' stopped {n} attempt(s). If it names a gate, "
                       f"check that the contract states the requirement "
                       f"explicitly; if it names a stop reason, the member never "
                       f"reached judgement and the budget or the task size is the "
                       f"thing to change.")
    slow = [t for t in data["tasks_detail"].values() if t["attempts"] >= 3]
    if slow:
        out.append(f"- {len(slow)} task(s) needed three or more attempts. Those are "
                   f"the ones to split into two smaller tasks next time.")
    if data["not_started"]:
        out.append(f"- {data['not_started']} task(s) never started, so the budget or "
                   f"the deadline bound the run before the roster did. Raise the "
                   f"budget or reduce the task count, not the quality bar.")
    return out or ["- Nothing to change: no failures were recorded."]


def load_report(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
