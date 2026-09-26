"""Rescue: after a crew code job fails, an OpenCode session tries to fix it.

Kris, 2026-09-26: "if a crew fails, they can launch as opencode to sort out the
issues and see if the failure can be changed into a success". Same member first
("to see if the errors are detectable by the same member who introduced them"),
then a capable member ("to save us time and effort"); both are recorded, because
"we are still evaluating the whole methodology".

Only CHECKABLE failures are rescued: the attempt exists and it failed a gate a
fix can change (hidden tests, API, stubs, ascii, safety). Budget, protocol or
no-output failures are our harness's problem, not the module's - not rescued.

The rescue is graded by exactly the same gates as the crew job. A rescued module
goes to the Review Desk; it is never applied automatically. Every attempt is one
line in runs/crew/rescue/records.jsonl (the data for the methodology question).

  python C:/Users/user/ATLAS-api-harness/crew/runners/rescue.py JOB_ID [--member M] [--no-escalate]
"""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def jobs_dir() -> Path:
    from crew.config import load_config
    return Path(load_config().state_home) / "jobs"

RECORDS = REPO / "runs" / "crew" / "rescue" / "records.jsonl"
RESCUABLE = {"hidden tests", "api", "no stubs", "ascii", "safety", "lsp"}


def _job(job_id: str) -> dict:
    return json.loads((jobs_dir() / job_id / "job.json").read_text(encoding="utf-8"))


def attempt_file(job_id: str, module: str, jobs: Path = None):
    jobs = jobs or jobs_dir()
    for p in (jobs / job_id / "output" / module, jobs / job_id / module):
        if p.is_file():
            return p
    return None


def rescuable(job: dict, jobs: Path = None) -> tuple:
    """(yes/no, why). jobs: the crew's jobs folder (default: from the config)."""
    if job.get("task_type") != "code_task":
        return False, f"task type {job.get('task_type')} is not rescued (code_task only)"
    res = job.get("result") or {}
    if res.get("passed"):
        return False, "the job passed"
    module = (job.get("spec") or {}).get("module", "")
    if not attempt_file(job["task_id"], module, jobs):
        return False, f"no attempt to fix ({res.get('stop_reason') or 'no output'})"
    failed = {s["rung"] for s in res.get("steps", []) if not s.get("ok")}
    if not failed:
        return False, "no gate failure recorded"
    if not failed <= RESCUABLE:
        return False, f"failed {sorted(failed)}: not a checkable module failure"
    return True, f"failed {sorted(failed)}"


def capable_member(same: str) -> str:
    from crew import personnel
    staff = personnel.load()
    for m in (staff.get("posts") or {}).get("module_author_py", []):
        if m != same:
            return m
    return ""


def rescue_once(job: dict, member: str, timeout_s: int = 1800) -> dict:
    from crew.runners import opencode_trial
    spec = dict(job["spec"])
    spec.setdefault("id", Path(spec["module"]).stem)
    module = spec["module"]
    src = attempt_file(job["task_id"], module).read_text(encoding="utf-8")
    failures = "\n".join(f"- [{s['rung']}] {s['detail'][:1500]}"
                         for s in job["result"]["steps"] if not s.get("ok"))
    label = f"rescue-{job['task_id']}-{member}"
    r = opencode_trial.run(member, spec, label, timeout_s,
                           seed={"files": {module: src}, "failures": failures},
                           duty="crew:rescue")
    record = {"at": dt.datetime.now().isoformat(timespec="seconds"), "job": job["task_id"],
              "module": module, "original_member": job.get("assigned_to"),
              "rescuer": member, "same_member": member == job.get("assigned_to"),
              "failed_rungs": sorted({s["rung"] for s in job["result"]["steps"]
                                      if not s.get("ok")}),
              "passed": r["passed"], "rounds": r["rounds"], "seconds": r["seconds"],
              "usage": r["usage"], "folder": str(Path(opencode_trial.load_config().state_home)
                                                 / "opencode" / label)}
    RECORDS.parent.mkdir(parents=True, exist_ok=True)
    with open(RECORDS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    if r["passed"]:
        from crew.runners import pm_queue
        fixed = Path(record["folder"]) / "ws" / module
        pm_queue.add(str(fixed), f"RESCUED: {module} by {member} (OpenCode) - crew job "
                     f"{job['task_id']} by {job.get('assigned_to')} had failed "
                     f"{', '.join(record['failed_rungs'])}", item_id=f"rescue:{label}")
    return record


def rescue(job_id: str, member: str = "", escalate: bool = True) -> list:
    job = _job(job_id)
    ok, why = rescuable(job)
    if not ok:
        raise SystemExit(f"not rescued: {why}")
    same = member or job.get("assigned_to")
    out = [rescue_once(job, same)]
    if not out[-1]["passed"] and escalate and not member:
        other = capable_member(same)
        if other:
            out.append(rescue_once(job, other))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--member", default="", help="rescue with this member only")
    ap.add_argument("--no-escalate", action="store_true")
    a = ap.parse_args()
    for rec in rescue(a.job_id, a.member, not a.no_escalate):
        print(json.dumps({k: rec[k] for k in ("rescuer", "same_member", "passed", "rounds",
                                              "seconds", "usage")}))
