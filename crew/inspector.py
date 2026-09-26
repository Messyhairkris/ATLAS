"""The Inspector: a recursive quality pass over every crew job.

Kris, 2026-09-25: "a recursive role or function that helps improve the
quality of every pass by an agent in a crew role." Modelled on Continual
Harness (Karten et al., arXiv 2605.09998): an outer loop reads the inner
loop's trajectory for FAILURE SIGNATURES and edits separate stores - not one
prompt blob - and keeps what measurably helps.

After every job (zero tokens - it reads the transcript, it asks no model):

1. detect signatures (budget ran out, submitted on the last request, token
   ceiling, repeated calls, re-reading what trimming took away, the same gate
   failing on every submission, empty/invalid replies);
2. map each to a refinement of ONE store:
   - budget / context / tokens  -> a TRIAL, started automatically, bounded;
   - house notes, playbook, posts, reply ceiling -> a PROPOSAL for the PA;
   - a gate that failed every submission -> a PROPOSAL flagged gate_suspect
     (2026-09-25: three of my new gates failed Gordon's correct scout);
3. score running trials: after TRIAL_WINDOW jobs of that member on that task
   type, KEEP if the pass rate did not drop and got better or cheaper,
   else REVERT. Kept trials stay applied (personnel.budget_for layers them).

What it may never touch: gates, hidden tests, contracts, deny globs, autonomy
stages. Those are how the work is judged; an improver that can edit its own
judge is the reward-hacking failure the paper and AIDE warn about.
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

TRIAL_WINDOW = 3
LIMITS = {"extra_requests": (0, 8), "token_factor": (1.0, 3.0),
          "context_ceiling": (0.5, 0.75)}
STEPS = {"extra_requests": 4, "token_factor": 1.5, "context_ceiling": 0.125}


def _home(cfg) -> Path:
    d = Path(cfg.state_home) / "inspector"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_trials(cfg) -> List[dict]:
    p = _home(cfg) / "trials.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_trials(cfg, trials: List[dict]) -> None:
    (_home(cfg) / "trials.json").write_text(json.dumps(trials, indent=1), encoding="utf-8")


def active_trial(cfg, member: str, task_type: str) -> Optional[dict]:
    """Overrides to apply to a new job: every KEPT trial for this pair, plus
    the running one (at most one runs at a time), merged in order."""
    mine = [t for t in _load_trials(cfg)
            if t["member"] == member and t["task_type"] == task_type
            and t["status"] in ("kept", "running")]
    if not mine:
        return None
    merged: Dict[str, object] = {}
    for t in mine:
        merged.update(t["overrides"])
    running = next((t for t in mine if t["status"] == "running"), None)
    return {"id": (running or mine[-1])["id"], "overrides": merged}


# -- signatures -------------------------------------------------------------------------

def signatures(job: dict, transcript: List[dict]) -> List[dict]:
    r = job.get("result") or {}
    budget = job.get("budget") or {}
    sig: List[dict] = []
    stop = r.get("stop_reason")
    reqs, max_req = int(r.get("requests") or 0), int(budget.get("max_requests") or 0)

    def add(name, detail, **kw):
        sig.append({"signature": name, "detail": detail, **kw})

    if stop == "budget_requests":
        add("budget_exhausted", f"used all {max_req} requests without passing")
    elif r.get("passed") and max_req and reqs >= max_req:
        add("last_request_pass", f"passed on request {reqs} of {max_req}: no margin")
    if stop == "budget_tokens":
        add("token_ceiling", f"stopped by the job token ceiling ({budget.get('max_tokens')})")
    kinds = Counter(e.get("kind") for e in transcript if e.get("event") == "reply")
    if kinds.get("thinking_cut_off") or stop == "output_truncated":
        add("reply_ceiling", f"{kinds.get('thinking_cut_off', 0)} replies cut off while thinking")
    if kinds.get("empty"):
        add("empty_replies", f"{kinds['empty']} empty replies")
    if kinds.get("invalid", 0) >= 2 or stop == "contract_abandoned":
        add("protocol_misfit", f"{kinds.get('invalid', 0)} invalid replies ({stop})")
    repeats = sum(1 for e in transcript if e.get("event") == "repeat")
    if repeats >= 2 or stop == "loop_repeat":
        add("repeat_calls", f"{repeats} repeated identical tool calls")
    reads = Counter(json.dumps([e.get("args", {}).get("path")])
                    for e in transcript if e.get("event") == "tool"
                    and e.get("tool") == "read_file")
    reread = [json.loads(k)[0] for k, n in reads.items() if n >= 3]
    if reread:
        add("rereading", f"read the same file 3+ times: {', '.join(map(str, reread[:3]))}")
    subs = [e for e in transcript if e.get("event") == "submission"]
    failed_by_sub = [{s["rung"] for s in e.get("steps", []) if not s["ok"]} for e in subs]
    if len(subs) >= 2 and not r.get("passed"):
        stuck = set.intersection(*failed_by_sub) if failed_by_sub else set()
        for rung in sorted(stuck):
            add("gate_stuck", f"rung '{rung}' failed on all {len(subs)} submissions",
                rung=rung)
    taught = [rung for a, b in zip(failed_by_sub, failed_by_sub[1:]) for rung in a - b]
    if taught:
        add("gate_taught", f"fixed after feedback: {', '.join(sorted(set(taught)))}",
            info=True)
    return sig


# -- refinements ------------------------------------------------------------------------

TRIAL_FOR = {"budget_exhausted": ("extra_requests",), "last_request_pass": ("extra_requests",),
             "token_ceiling": ("token_factor",), "rereading": ("context_ceiling",)}
PROPOSAL_FOR = {
    "reply_ceiling": ("config", "raise max_tokens_by_member for this member (its thinking is cut off before it answers)"),
    "empty_replies": ("house_note", "add a 'think briefly; the answer channel must hold the tool call or SUBMIT' note"),
    "protocol_misfit": ("post", "this member does not follow the text tool protocol for this task: move it off this post, or give it native tool calling (special teams)"),
    "repeat_calls": ("house_note", "add a note to check existing results before calling a tool again; or lower leash.max_repeats"),
    "gate_stuck": ("gate_suspect", "the same gate failed every submission: read the best output - either the contract/playbook wording is unclear, or the gate is wrong (PA only; the Inspector never edits gates)"),
}


def _baseline(cfg, member: str, task_type: str, before: str) -> dict:
    from .personnel import history
    runs = history(Path(cfg.state_home) / "jobs").get((member, task_type), [])
    n = len(runs)
    return {"n": n, "pass_rate": round(sum(r["passed"] for r in runs) / n, 3) if n else 0.0,
            "requests_mean": round(sum(r["requests"] for r in runs) / n, 2) if n else 0.0}


def _start_trial(cfg, trials, member, task_type, knob, because, job_id) -> Optional[dict]:
    if any(t["member"] == member and t["task_type"] == task_type and t["status"] == "running"
           for t in trials):
        return None                        # one change at a time, or nothing is measurable
    current = {}
    for t in trials:
        if t["member"] == member and t["task_type"] == task_type and t["status"] == "kept":
            current.update(t["overrides"])
    lo, hi = LIMITS[knob]
    now = float(current.get(knob, lo if knob != "context_ceiling" else 0.5))
    new = round(min(hi, now + STEPS[knob]) if knob != "token_factor"
                else min(hi, max(now, 1.0) * STEPS[knob]), 3)
    if new <= now:
        return None                        # at the bound: a proposal, not another trial
    trial = {"id": f"trial-{int(time.time())}-{member}-{task_type}-{knob}",
             "member": member, "task_type": task_type,
             "overrides": {knob: new}, "because": because, "from_job": job_id,
             "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "baseline": _baseline(cfg, member, task_type, job_id),
             "jobs": [], "status": "running"}
    trials.append(trial)
    return trial


def _score(trial: dict) -> None:
    jobs = trial["jobs"][:TRIAL_WINDOW]
    passed = sum(j["passed"] for j in jobs)
    rate = passed / len(jobs)
    reqs = sum(j["requests"] for j in jobs) / len(jobs)
    base = trial["baseline"]
    better = rate > base["pass_rate"] or (rate >= base["pass_rate"] and passed
                                          and reqs <= base["requests_mean"] * 1.25)
    trial["result"] = {"pass_rate": round(rate, 3), "requests_mean": round(reqs, 2)}
    trial["status"] = "kept" if rate >= base["pass_rate"] and better else "reverted"
    trial["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")


def inspect_job(cfg, job: dict, transcript_path: Path) -> dict:
    """Run after every finished job. Returns what it found and did."""
    try:
        transcript = [json.loads(l) for l in
                      Path(transcript_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        transcript = []
    member, tt, jid = job["assigned_to"], job["task_type"], job["task_id"]
    r = job.get("result") or {}
    trials = _load_trials(cfg)
    # 1. this job is evidence for the trial it ran under
    tid = (job.get("budget") or {}).get("trial")
    for t in trials:
        if t["id"] == tid and t["status"] == "running":
            t["jobs"].append({"job": jid, "passed": bool(r.get("passed")),
                              "requests": int(r.get("requests") or 0)})
            if len(t["jobs"]) >= TRIAL_WINDOW:
                _score(t)
    # 2. signatures -> trials (bounded, automatic) and proposals (PA)
    sigs = signatures(job, transcript)
    started, proposed = [], []
    for s in sigs:
        if s.get("info"):
            continue
        for knob in TRIAL_FOR.get(s["signature"], ()):
            t = _start_trial(cfg, trials, member, tt, knob, s["detail"], jid)
            if t:
                started.append(t["id"])
        if s["signature"] in PROPOSAL_FOR:
            store, text = PROPOSAL_FOR[s["signature"]]
            proposed.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "job": jid,
                             "member": member, "task_type": tt, "store": store,
                             "signature": s["signature"], "detail": s["detail"],
                             "proposal": text, "status": "open"})
    _save_trials(cfg, trials)
    if proposed:
        with open(_home(cfg) / "proposals.jsonl", "a", encoding="utf-8") as fh:
            for p in proposed:
                fh.write(json.dumps(p) + "\n")
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "job": jid, "member": member,
              "task_type": tt, "passed": bool(r.get("passed")),
              "signatures": sigs, "trials_started": started,
              "proposals": len(proposed)}
    with open(_home(cfg) / "inspections.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def start_manual_trial(cfg, member: str, task_type: str, overrides: dict,
                       because: str) -> dict:
    """A PA-started trial (e.g. lsp: true for scouts) measured the same way.
    LSP stays in testing (Kris, 2026-09-25): this is how it gets measured."""
    trials = _load_trials(cfg)
    if any(t["member"] == member and t["task_type"] == task_type and t["status"] == "running"
           for t in trials):
        raise ValueError(f"a trial is already running for {member}/{task_type}")
    trial = {"id": f"trial-{int(time.time())}-{member}-{task_type}-manual",
             "member": member, "task_type": task_type, "overrides": overrides,
             "because": because, "from_job": None,
             "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "baseline": _baseline(cfg, member, task_type, ""), "jobs": [],
             "status": "running"}
    trials.append(trial)
    _save_trials(cfg, trials)
    return trial
