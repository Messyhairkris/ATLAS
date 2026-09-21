"""Running a whole project through the crew, unattended, for hours.

Kris's brief: teams get tasks inside or slightly beyond their ability, they work
until they succeed or a failure condition calls for senior review, successful
work is tracked and later tasks build on it, and at the end there is a
performance breakdown per team - or, if it failed, why, and what to change.

The pieces that make that safe rather than reckless:

* a crew member's code never reaches a real project. Accepted modules land in
  the crew's own workspace; a human moves them from there.
* a task is judged by tests the member never sees (`crew/hidden_tests/`), so
  "it works" is not the member's opinion.
* three strikes, then escalation. A failing task is retried with the test output
  as the reason; after `max_attempts` it goes to a senior for DIRECTIVES (never
  code), gets one more attempt, then is recorded as failed and the campaign moves
  on rather than burning the budget on it.
* the request budget and a wall-clock deadline both stop new work, and nothing
  is ever left half-applied.
* it says what it is doing, always, to the console and to status.json - Kris's
  rule that no program may look idle.

    python -m crew campaign run crew/campaigns/tts_foundation.json
    python -m crew campaign status tts-foundation
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import REPO_ROOT, Config, CrewError, load_config
from .core import Crew
from .store import COMPLETED, FAILED, REVIEW

ACCEPTED, RUNNING, WAITING, ESCALATED, DEAD = (
    "accepted", "running", "waiting", "escalated", "failed")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


class Campaign:
    def __init__(self, spec: dict, cfg: Optional[Config] = None,
                 crew: Optional[Crew] = None, quiet: bool = False):
        self.spec = spec
        self.cfg = cfg or load_config()
        self.crew = crew or Crew(self.cfg)
        self.quiet = quiet
        self.name = spec["name"]
        self.home = Path(self.cfg.state_home) / "campaigns" / self.name
        self.home.mkdir(parents=True, exist_ok=True)
        # A campaign may keep its output in its own folder, so one campaign's
        # modules cannot be confused with another's while a human is testing.
        self.workspace = Path(self.cfg.state_home) / "outbox" / "workspace"
        if spec.get("workspace_subdir"):
            self.workspace = self.workspace / str(spec["workspace_subdir"])
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.max_requests = int(spec.get("max_requests", 150))
        self.max_attempts = int(spec.get("max_attempts", 3))
        # A senior call is the only expensive request in the campaign (Kimi,
        # not a roster model), so the whole run gets a small fixed allowance.
        self.max_escalations = int(spec.get("max_escalations", 2))
        self.escalations_used = 0
        self.deadline = self._deadline(spec.get("deadline"))
        self.requests_used = 0
        self.events: List[dict] = []
        self.tasks: Dict[str, dict] = {}
        for t in self._expand(spec):
            self.tasks[t["id"]] = t

    # -- planning ------------------------------------------------------------------
    @staticmethod
    def _deadline(raw) -> Optional[float]:
        if not raw:
            return None
        try:
            return datetime.datetime.fromisoformat(str(raw)).timestamp()
        except ValueError:
            raise CrewError(f"deadline {raw!r} is not an ISO timestamp")

    def _expand(self, spec: dict) -> List[dict]:
        """One entry per task, with the tester's task generated from the
        author's: the same team, but a different member, and it cannot start
        until the module it tests has been accepted."""
        teams = spec["teams"]
        out: List[dict] = []
        for t in spec["tasks"]:
            team = teams[t["team"]]
            out.append({"id": t["id"], "team": t["team"], "kind": "module",
                        "member": team["author"], "module": t["module"],
                        "contract": t["contract"], "api": t["api"],
                        "hidden_tests": t.get("hidden_tests", []),
                        "depends": list(t.get("depends", [])),
                        "uses": list(t.get("uses", [])),
                        "instructions": t.get("instructions", ""),
                        "state": WAITING, "attempts": 0, "job_ids": [],
                        "requests": 0, "tokens": 0, "seconds": 0.0,
                        "failed_gates": [], "escalations": 0, "senior": ""})
            if t.get("cross_tests", True):
                out.append({"id": t["id"] + "-tests", "team": t["team"],
                            "kind": "tests", "member": team["tester"],
                            "test_file": f"test_{t['module'][:-3]}.py",
                            "contract": t["contract"],
                            "module": t["module"],
                            "depends": [t["id"]],
                            "uses": list(t.get("uses", [])),
                            "min_tests": int(t.get("min_tests", 6)),
                            "instructions": t.get("test_instructions", ""),
                            "state": WAITING, "attempts": 0, "job_ids": [],
                            "requests": 0, "tokens": 0, "seconds": 0.0,
                            "failed_gates": [], "escalations": 0, "senior": ""})
        return out

    def _ready(self) -> List[dict]:
        done = {i for i, t in self.tasks.items() if t["state"] == ACCEPTED}
        return [t for t in self.tasks.values()
                if t["state"] == WAITING and all(d in done for d in t["depends"])]

    def _budget(self) -> dict:
        """What one attempt may spend.

        Requests are the metered resource and tokens are nearly free, so the
        token ceiling exists only to stop a runaway. Measured 2026-09-20: Qwen
        spent ~78k tokens on a 200-line module and three attempts in a row died
        as budget_tokens at the 60k default, producing no file at all - which
        reads like the model failing when it is our ceiling.
        """
        return {"max_requests": int(self.spec.get("requests_per_attempt", 14)),
                "max_tokens": int(self.spec.get("tokens_per_attempt", 150000))}

    def _module_paths(self, task: dict) -> List[str]:
        """Accepted modules this task may import, TRANSITIVELY.

        The dry run caught this: the tester of speech_queue got speech_queue.py
        but not the verbalize.py that speech_queue imports, so every one of its
        tests failed on the import line. A dependency's dependencies are part of
        the dependency.
        """
        seen: set = set()
        paths: List[str] = []

        def walk(task_id: str) -> None:
            if task_id in seen or task_id not in self.tasks:
                return
            seen.add(task_id)
            other = self.tasks[task_id]
            if other["kind"] == "module":
                paths.append(str(self.workspace / other["module"]))
            for dep in other["depends"]:
                walk(dep)

        for dep in task["depends"]:
            walk(dep)
        if task["kind"] == "tests":
            paths.append(str(self.workspace / task["module"]))
        # Modules accepted in an EARLIER campaign and already in the workspace.
        # `depends` cannot say this - it means "a task here that must finish
        # first" - and a module that is already accepted gates nothing.
        for name in task.get("uses", []):
            path = self.workspace / name
            if not path.is_file():
                raise CrewError(f"task {task['id']} uses {name}, which is not in "
                                f"the workspace at {path}")
            paths.append(str(path))
        return sorted(set(paths))

    # -- reporting -----------------------------------------------------------------
    def say(self, text: str) -> None:
        line = f"[{_now()}] {text}"
        if not self.quiet:
            print(line, flush=True)
        with open(self.home / "progress.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def event(self, kind: str, **fields) -> None:
        self.events.append({"at": _now(), "event": kind, **fields})
        self.write_status()

    def write_status(self) -> None:
        left = None
        if self.deadline:
            left = round((self.deadline - time.time()) / 60, 1)
        status = {
            "campaign": self.name, "goal": self.spec.get("goal", ""),
            "updated": _now(),
            "requests_used": self.requests_used,
            "requests_budget": self.max_requests,
            "senior_calls": f"{self.escalations_used}/{self.max_escalations}",
            "minutes_to_deadline": left,
            "tasks": {i: {k: t[k] for k in
                          ("state", "kind", "team", "member", "attempts",
                           "requests", "tokens", "seconds", "escalations")}
                      for i, t in self.tasks.items()},
            "counts": {s: sum(1 for t in self.tasks.values() if t["state"] == s)
                       for s in (ACCEPTED, RUNNING, WAITING, ESCALATED, DEAD)},
            "events": self.events[-40:],
        }
        (self.home / "status.json").write_text(
            json.dumps(status, indent=2), encoding="utf-8")

    # -- the loop ------------------------------------------------------------------
    def stop_reason(self) -> Optional[str]:
        if self.requests_used >= self.max_requests:
            return f"request budget spent ({self.requests_used}/{self.max_requests})"
        if self.deadline and time.time() >= self.deadline:
            return "deadline reached"
        return None

    def run(self) -> dict:
        self.say(f"campaign {self.name}: {len(self.tasks)} tasks, "
                 f"budget {self.max_requests} requests"
                 + (f", deadline {datetime.datetime.fromtimestamp(self.deadline):%H:%M}"
                    if self.deadline else ""))
        self.event("campaign_started", tasks=sorted(self.tasks))
        while True:
            stop = self.stop_reason()
            if stop:
                self.say(f"stopping: {stop}")
                self.event("campaign_stopped", reason=stop)
                break
            ready = self._ready()
            if not ready:
                blocked = [i for i, t in self.tasks.items() if t["state"] == WAITING]
                if not blocked:
                    self.say("every task is finished")
                    self.event("campaign_complete")
                else:
                    self.say(f"nothing can start: {len(blocked)} task(s) wait on "
                             f"work that failed - {', '.join(sorted(blocked))}")
                    self.event("campaign_blocked", waiting=sorted(blocked))
                break
            task = ready[0]
            self.run_task(task)
        return self.finish()

    def run_task(self, task: dict) -> None:
        task["state"] = RUNNING
        self.write_status()
        while task["attempts"] < self.max_attempts + (1 if task["escalations"] else 0):
            stop = self.stop_reason()
            if stop:
                task["state"] = WAITING
                return
            task["attempts"] += 1
            self.say(f"{task['id']}: attempt {task['attempts']} by "
                     f"{task['member']} (team {task['team']})")
            t0 = time.time()
            try:
                brief = self._attempt(task)
            except CrewError as e:
                self.say(f"{task['id']}: could not run: {e}")
                self.event("task_error", task=task["id"], error=str(e)[:300])
                task["state"] = DEAD
                return
            task["seconds"] += round(time.time() - t0, 1)
            task["requests"] += int(brief.get("requests") or 0)
            task["tokens"] += int(brief.get("tokens") or 0)
            self.requests_used += int(brief.get("requests") or 0)
            job_id = brief["task_id"]
            task["job_ids"].append(job_id)
            if brief.get("passed_gates"):
                self.crew.review(job_id, "approve", reviewer="campaign",
                                 notes=f"{self.name}: every gate passed, "
                                       f"including the hidden tests")
                task["state"] = ACCEPTED
                self.say(f"{task['id']}: ACCEPTED after {task['attempts']} "
                         f"attempt(s), {task['requests']} requests")
                self.event("task_accepted", task=task["id"], team=task["team"],
                           member=task["member"], attempts=task["attempts"],
                           requests=task["requests"])
                return
            gates = brief.get("failed_gates") or [brief.get("stop_reason") or "unknown"]
            task["failed_gates"].append(gates[:3])
            self.say(f"{task['id']}: failed - {gates[0][:160]}")
            self.event("task_failed_attempt", task=task["id"],
                       attempt=task["attempts"], gates=gates[:3])
            last = task["attempts"] >= self.max_attempts + (1 if task["escalations"] else 0)
            if last and not task["escalations"]:
                if self.escalate(task, gates):
                    continue
                task["state"] = DEAD
                return
            if last:
                task["state"] = DEAD
                self.say(f"{task['id']}: FAILED for good after senior review")
                self.event("task_dead", task=task["id"], gates=gates[:3])
                return
        task["state"] = DEAD

    def _attempt(self, task: dict) -> dict:
        """One submission, from a fresh job. A retry is a new job with the
        previous failure quoted in its instructions, which keeps every attempt
        independently reviewable in the store."""
        history = ""
        if task["failed_gates"]:
            last = task["failed_gates"][-1]
            history = ("\n\nTHE PREVIOUS ATTEMPT FAILED THESE CHECKS. This is "
                       "machine output, not an opinion - fix the cause:\n- "
                       + "\n- ".join(last))
        if task.get("directives"):
            history += ("\n\nSENIOR DIRECTIVES (a senior model read the failure; "
                        "follow these):\n- " + "\n- ".join(task["directives"]))
        if task["kind"] == "module":
            spec = {"task_type": "code_task",
                    "title": f"{self.name}: write {task['module']}",
                    "module": task["module"], "contract": task["contract"],
                    "api": task["api"], "hidden_tests": task["hidden_tests"],
                    "depends_modules": self._module_paths(task),
                    "assigned_to": task["member"],
                    "output": {"root": str(self.workspace)},
                    "instructions": (task["instructions"] + history).strip(),
                    "budget": self._budget()}
        else:
            spec = {"task_type": "code_tests",
                    "title": f"{self.name}: test {task['module']}",
                    "test_file": task["test_file"], "contract": task["contract"],
                    "depends_modules": self._module_paths(task),
                    "min_tests": task["min_tests"],
                    "assigned_to": task["member"],
                    "output": {"root": str(self.workspace / "tests")},
                    "instructions": (task["instructions"] + history).strip(),
                    "budget": self._budget()}
        brief = self.crew.submit(spec, submitted_by=f"campaign:{self.name}",
                                 claim=True)
        job_id = brief["task_id"]
        try:
            return self.crew.run_job(job_id)
        finally:
            self.crew.store.release(job_id)

    def escalate(self, task: dict, gates: List[str]) -> bool:
        """Ask a senior model what is going wrong. It returns DIRECTIVES, never
        code, so the crew member still does the work - and we find out whether
        the task was mis-specified rather than blaming the model."""
        if self.escalations_used >= self.max_escalations:
            self.say(f"{task['id']}: senior review is capped at "
                     f"{self.max_escalations} for this campaign and the "
                     f"allowance is spent; recording the failure instead")
            self.event("escalation_capped", task=task["id"],
                       cap=self.max_escalations)
            return False
        self.escalations_used += 1
        task["escalations"] += 1
        task["state"] = ESCALATED
        self.write_status()
        senior = self.spec.get("senior", "Claude")
        self.say(f"{task['id']}: escalating to {senior} after "
                 f"{task['attempts']} failed attempts")
        contract = Path(task["contract"]).read_text(encoding="utf-8")[:6000]
        last_source = ""
        if task["job_ids"]:
            jdir = self.crew.store.job_dir(task["job_ids"][-1])
            for p in (jdir / "output").rglob("*.py"):
                last_source = p.read_text(encoding="utf-8")[:6000]
                break
        prompt = (
            "You are a senior engineer reviewing a junior's repeated failure on a "
            "small, fully specified module. Do NOT write the module. Reply with at "
            "most five numbered DIRECTIVES: what to change, in the order it should "
            "be changed. If the CONTRACT itself is ambiguous or contradicts the "
            "tests, say so as directive 1 and name the exact line - a mis-specified "
            "task is our fault, not the junior's.\n\n"
            f"CONTRACT:\n{contract}\n\nFAILED CHECKS:\n- " + "\n- ".join(gates[:6])
            + (f"\n\nTHE JUNIOR'S LAST SUBMISSION:\n{last_source}" if last_source else ""))
        (self.home / f"escalation-{task['id']}.md").write_text(
            prompt, encoding="utf-8")
        text, used = self._ask_senior(senior, prompt)
        if text is None:
            self.say(f"{task['id']}: no senior was reachable; recording the "
                     f"failure with its evidence instead")
            self.event("escalation_failed", task=task["id"])
            return False
        self.say(f"{task['id']}: senior {used} replied")
        directives = [l.strip(" -*0123456789.") for l in text.splitlines()
                      if l.strip() and l.strip()[0].isdigit()][:5] or [text[:600]]
        task["directives"] = directives
        task["senior"] = used
        (self.home / f"senior-{task['id']}.md").write_text(text, encoding="utf-8")
        self.say(f"{task['id']}: senior gave {len(directives)} directive(s); "
                 f"one more attempt")
        self.event("escalated", task=task["id"], directives=directives)
        task["state"] = RUNNING
        return True

    def _ask_senior(self, senior: str, prompt: str):
        """Reach a senior model. Returns (text, which senior) or (None, None).

        Order: the Claude CLI when it is installed and asked for, then the
        provider layer. A senior returns directives, so a missing senior is a
        degraded campaign, not a broken one - the failure is still recorded with
        its evidence.
        """
        import shutil
        import sys
        system = ("You are a senior engineer. Reply with numbered directives "
                  "only. Never write the module.")
        if senior.lower() in ("claude", "claude-code") and shutil.which("claude"):
            try:
                sys.path.insert(0, str(REPO_ROOT / "experiments"))
                from senior_review import _call_claude_cli
                return _call_claude_cli(system, prompt)["content"], "Claude (CLI)"
            except Exception as e:                              # noqa: BLE001
                self.say(f"  the claude CLI failed ({type(e).__name__}); "
                         f"falling back to the provider")
        model = self.spec.get("senior_fallback", "Kimi")
        if str(senior).lower() == "none" or str(model).lower() == "none":
            return None, None
        try:
            import os
            sys.path.insert(0, str(REPO_ROOT / "v3-service"))
            from providers.telemetry import context as telemetry_context
            from stages.llm_client import chat_completion
            from providers.registry import resolve_alias
            os.environ["ATLAS_CHAT_MODEL"] = resolve_alias(
                os.environ.get("ATLAS_PROVIDER"), model)
            with telemetry_context(run_id=f"campaign:{self.name}",
                                   duty="crew:senior_review", role="senior",
                                   persona=model, attempt=1):
                out = chat_completion("", messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=4096, timeout=600.0)
            self.requests_used += 1
            return (out.get("content") or "").strip() or None, model
        except Exception as e:                                  # noqa: BLE001
            self.say(f"  senior {model} unreachable: {type(e).__name__}: "
                     f"{str(e)[:140]}")
            return None, None

    # -- the end -------------------------------------------------------------------
    def finish(self) -> dict:
        from . import report
        summary = report.campaign_report(self)
        (self.home / "REPORT.md").write_text(summary["markdown"], encoding="utf-8")
        (self.home / "summary.json").write_text(
            json.dumps(summary["data"], indent=2), encoding="utf-8")
        self.write_status()
        self.say(f"report written: {self.home / 'REPORT.md'}")
        return summary["data"]


def load(path: str) -> dict:
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("name", "teams", "tasks"):
        if key not in spec:
            raise CrewError(f"campaign file needs {key!r}")
    return spec
