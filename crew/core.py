"""Crew service layer: submit, run, review, inbox, worker.

Transport-free, so the MCP server (crew/server.py), the CLI (python -m crew)
and the tests all drive the same code.
"""

import json
import os
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import autofix, inspector, personnel, playbook, quirklint, task_types
from .agent import run_member
from .config import REPO_ROOT, Config, CrewError, load_config
from .ratelimit import RateWindow
from .roster import AUTO_APPLY, Roster
from .store import (BLOCKED, COMPLETED, FAILED, IN_PROGRESS, READY, REJECTED,
                    REVIEW, Store, now_iso)
from .tools import Evidence, Toolbox

sys.path.insert(0, str(REPO_ROOT / "v3-service"))

RESULT_CHARS = 20000
DECISIONS = ("approve", "revise", "reject", "acknowledge")


def _env_setup(cfg: Config) -> None:
    os.environ.setdefault("ATLAS_PROVIDER", "synthetic")
    if cfg.telemetry_file:
        os.environ.setdefault("ATLAS_TELEMETRY_FILE", cfg.telemetry_file)
    if cfg.deny_models:
        os.environ.setdefault("ATLAS_DENY_MODELS", ",".join(cfg.deny_models))


# Output ceiling per member, from crew/config.json. A reasoning model needs room
# for the thinking AND the answer: at 16384 Barry spent 18-20k tokens reasoning
# and returned three EMPTY replies in a row (2026-09-20).
DEFAULT_REPLY_TOKENS = 16384


def _reply_tokens(cfg: Config, persona: str) -> int:
    table = (cfg.defaults.get("max_tokens_by_member") or {})
    try:
        return int(table.get(persona, DEFAULT_REPLY_TOKENS))
    except (TypeError, ValueError):
        return DEFAULT_REPLY_TOKENS


def _default_chat(model: str, job_id: str, task_type: str, persona: str,
                  renew: Callable[[], None], reply_tokens: int = DEFAULT_REPLY_TOKENS):
    from . import claude_chat
    if claude_chat.is_claude(model):
        # Claude is reached through Anthropic's own SDK, never an OpenAI shim,
        # and it does not draw on the Synthetic request pool.
        return claude_chat.claude_chat(model, reply_tokens=reply_tokens,
                                       renew=renew)
    from providers.telemetry import context as telemetry_context
    from stages.llm_client import chat_completion

    def chat(messages: List[dict], n: int) -> dict:
        renew()
        os.environ["ATLAS_CHAT_MODEL"] = model
        with telemetry_context(run_id=job_id, duty=f"crew:{task_type}",
                               task_id=job_id, role="junior",
                               persona=persona, attempt=n):
            return chat_completion("", messages=messages, temperature=0.2,
                                   max_tokens=reply_tokens, timeout=900.0)
    return chat


class Crew:
    def __init__(self, cfg: Optional[Config] = None, chat_factory=None):
        self.cfg = cfg or load_config()
        _env_setup(self.cfg)
        self.store = Store(self.cfg)
        self.roster = Roster(self.cfg)
        self.rate = RateWindow(self.cfg)
        self._hold_logged = 0.0
        self._hold = 0.0
        self.chat_factory = chat_factory or _default_chat
        self._stop = threading.Event()

    # -- submit ------------------------------------------------------------------
    def submit(self, spec: dict, submitted_by: str = "unknown",
               claim: bool = False) -> dict:
        """Queue a task. claim=True takes the job's claim BEFORE it becomes
        visible, so this caller runs it and no other worker (e.g. a server
        process started with an older config) can grab it first."""
        if not isinstance(spec, dict):
            raise CrewError("spec must be an object")
        tt = spec.get("task_type")
        ttdef = task_types.get(tt)
        if not (spec.get("title") or "").strip():
            raise CrewError("spec.title is required")
        spec = ttdef["normalize"](dict(spec), self.cfg)
        staff = personnel.load() if self.cfg.defaults.get("budget_from_personnel") else None
        persona = spec.get("assigned_to") or self.cfg.defaults["assigned_to"]
        if persona.startswith("@"):
            persona = personnel.resolve(persona, staff or personnel.load(),
                                        self.cfg.deny_models)
        model = self._model_for(persona)
        job_id = self.store.new_job_id()
        if tt == "organize_plan":
            spec["output"]["root"] = str(Path(spec["output"]["root"]) / job_id)
        deps = list(spec.get("dependencies") or [])
        for d in deps:
            self.store.load(d)  # raises if unknown
        budget = dict(spec.get("budget") or {})
        if staff is not None:
            # The member's measured need for this kind of job, not one number
            # for everyone. An explicit spec budget still wins, key by key.
            trial = inspector.active_trial(self.cfg, persona, tt)
            fitted = personnel.budget_for(staff, persona, tt,
                                          personnel.history(self.store.jobs_dir),
                                          (trial or {}).get("overrides"))
            if trial:
                fitted["trial"] = trial["id"]
                if "lsp" in trial["overrides"] and "lsp" not in spec:
                    spec["lsp"] = bool(trial["overrides"]["lsp"])
            budget = {**fitted, **budget}
        job = {
            "task_id": job_id, "project": self.cfg.project,
            "title": spec["title"].strip(), "task_type": tt,
            "description": (spec.get("instructions") or "").strip(),
            "assigned_to": persona, "model": model,
            "status": BLOCKED if deps else READY, "dependencies": deps,
            "context_files": spec.get("context_files") or [],
            "milestone_id": spec.get("milestone_id"),
            "submitted_by": submitted_by, "created_at": now_iso(),
            "budget": {**{k: v for k, v in budget.items()
                          if k in ("context_tokens", "observation_chars", "source",
                                   "trial")},
                       "max_requests": int(budget.get("max_requests",
                                                      self.cfg.defaults["max_requests"])),
                       "max_tokens": int(budget.get("max_tokens",
                                                    self.cfg.defaults["max_tokens"]))},
            "constraints": [], "revisions": 0, "runs": [], "result": None,
            "notice": False, "spec": spec,
        }
        if claim and not self.store.try_claim(job_id):
            raise CrewError(f"could not pre-claim {job_id}")
        self.store.save(job)
        self.store.log("task_submitted", submitted_by, job_id,
                       task_type=tt, assigned_to=persona, title=job["title"])
        return self._brief(job)

    def _model_for(self, persona: str) -> str:
        from providers.registry import denied_models, resolve_alias
        # Claude members live in crew/config.json, not providers.json: they are
        # not Synthetic models, and listing them there would put them in the
        # wrong provider's pool, quotas and deny list.
        claude = (self.cfg.defaults.get("claude_members") or {}).get(persona)
        if claude:
            return claude
        provider = os.environ.get("ATLAS_PROVIDER")
        model = resolve_alias(provider, persona)
        if model == persona and not persona.startswith("hf:"):
            raise CrewError(f"unknown crew member {persona!r}; use a nickname "
                            f"from providers.json (Hoss, Barry, Qwen, Nemotron, Gordon) "
                            f"or crew/config.json claude_members (Haiku)")
        if model.lower() in denied_models(provider):
            raise CrewError(f"{persona} is on the deny list for this round")
        return model

    # -- run -------------------------------------------------------------------------
    def run_job(self, job_id: str) -> dict:
        """Run one job; the caller must hold its claim."""
        job = self.store.load(job_id)
        if job["status"] != READY:
            raise CrewError(f"{job_id} is {job['status']}, not ready")
        job["status"] = IN_PROGRESS
        job["started_at"] = now_iso()
        self.store.save(job)
        claim_node = self.store.log("task_claimed", job["assigned_to"], job_id,
                                    owner=self.store.owner)
        ttdef = task_types.get(job["task_type"])
        spec = job["spec"]
        jdir = self.store.job_dir(job_id)
        transcript = jdir / "transcript.jsonl"

        def log_event(e: dict) -> None:
            with open(transcript, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": now_iso(), **e}, ensure_ascii=False) + "\n")

        # every job says it is running and when it is likely done (crew/eta.py)
        from . import eta as _eta
        (jdir / "status.json").write_text(json.dumps({
            "state": "running", "job": job_id, "member": job["assigned_to"],
            "task_type": job["task_type"], "started": now_iso(),
            "eta": _eta.estimate(job["assigned_to"], f"crew:{job['task_type']}")},
            indent=1), encoding="utf-8")
        lsp_pool = None
        if spec.get("lsp") and self.cfg.data.get("lsp"):
            from .lsp import LspPool
            lsp_pool = LspPool(self.cfg.data["lsp"], Path(spec["read_roots"][0]))
        try:
            evidence = Evidence()
            toolbox = Toolbox(self.cfg, [Path(r) for r in spec["read_roots"]],
                              evidence,
                              int(job["budget"].get("observation_chars")
                                  or self.cfg.defaults["observation_chars"]),
                              lsp=lsp_pool)
            staff = personnel.load() if self.cfg.defaults.get("budget_from_personnel") else {}
            spec["_job_dir"] = str(jdir)
            preload = ttdef["preload"](spec, self.cfg, toolbox)
            constraints = "".join(f"\nREVIEWER CONSTRAINT {i + 1}: {c}"
                                  for i, c in enumerate(job["constraints"]))
            task_text = (f"TASK {job_id}: {job['title']}\n"
                         f"{job['description'] or ''}{constraints}\n\n{preload}")
            try:
                chat = self.chat_factory(
                    job["model"], job_id, job["task_type"], job["assigned_to"],
                    lambda: self.store.renew(job_id),
                    _reply_tokens(self.cfg, job["assigned_to"]))
            except TypeError:
                # a test double with the older five-argument signature
                chat = self.chat_factory(job["model"], job_id, job["task_type"],
                                         job["assigned_to"],
                                         lambda: self.store.renew(job_id))
            fixes: List[str] = []

            def grade(files: Dict[str, str]) -> List[dict]:
                """Lint near-misses for free, then gate. Corrections are
                recorded and shown to the reviewer, never silent."""
                fixed, notes = autofix.apply(files, spec.get("_run_log", ""), toolbox)
                fixed, quirk_notes = quirklint.repair(fixed, spec, job["task_type"])
                notes += quirk_notes
                if notes:
                    files.clear()
                    files.update(fixed)      # the kept submission is the fixed one
                    fixes.extend(notes)
                    log_event({"event": "autofix", "notes": notes})
                steps = ttdef["gates_fn"](files, spec, self.cfg, toolbox)
                return steps + quirklint.gate_steps(files, job["task_type"])

            out = run_member(
                persona=job["assigned_to"], task_type=job["task_type"],
                playbook=playbook.load(job["task_type"]), task_text=task_text,
                expected_files=spec["output"]["files"], toolbox=toolbox,
                grade=grade,
                chat=chat, max_requests=job["budget"]["max_requests"],
                max_tokens=job["budget"]["max_tokens"],
                fetch_enabled=bool(self.cfg.fetch_allowlist), log=log_event,
                context_tokens=job["budget"].get("context_tokens"),
                addenda=personnel.system_addenda(staff, job["assigned_to"]) if staff else "",
                leash=personnel.leash(staff, job["assigned_to"]) if staff else None)
        except Exception as e:  # noqa: BLE001 - a job failure, not a crash
            log_event({"event": "error", "error": traceback.format_exc()[-2000:]})
            job = self.store.load(job_id)
            job["status"] = FAILED
            job["result"] = {"error": f"{type(e).__name__}: {e}", "passed": False}
            self.store.save(job)
            self.store.log("task_failed", "system", job_id, parent=claim_node,
                           error=str(e)[:300])
            return self._brief(job)
        finally:
            if lsp_pool:
                lsp_pool.close()

        staged = jdir / "output"
        if staged.exists():
            shutil.rmtree(staged)
        for rel, text in out["files"].items():
            dest = staged / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")

        job = self.store.load(job_id)
        first_try = out["submissions"] == 1 and job["revisions"] == 0
        job["result"] = {k: out[k] for k in ("passed", "stop_reason", "requests",
                                             "tokens", "submissions", "repeats",
                                             "empty_replies", "native_tool_calls",
                                             "steps", "notes", "evidence")}
        job["result"]["files"] = sorted(out["files"])
        job["result"]["autofixes"] = fixes
        job["runs"].append({"at": now_iso(), "passed": out["passed"],
                            "requests": out["requests"], "tokens": out["tokens"],
                            "stop_reason": out["stop_reason"]})
        self.roster.record_run(job["assigned_to"], job["task_type"], job_id,
                               out["passed"], first_try, out["requests"], out["tokens"])
        graded = self.store.log("output_staged", job["assigned_to"], job_id,
                                parent=claim_node, passed=out["passed"],
                                stop_reason=out["stop_reason"],
                                requests=out["requests"], tokens=out["tokens"],
                                failed_gates=[s["rung"] for s in out["steps"] if not s["ok"]])
        if not out["passed"]:
            job["status"] = FAILED
        elif self.roster.stage(job["assigned_to"], job["task_type"]) in AUTO_APPLY:
            self._apply(job, actor="system:auto", parent=graded)
            job["status"] = COMPLETED
            job["notice"] = True
        else:
            job["status"] = REVIEW
        job["finished_at"] = now_iso()
        self.store.save(job)
        (jdir / "status.json").write_text(json.dumps({
            "state": "finished", "job": job_id, "status": job["status"],
            "passed": out["passed"], "finished": job["finished_at"]}, indent=1),
            encoding="utf-8")
        if self.cfg.defaults.get("budget_from_personnel"):
            try:
                inspector.inspect_job(self.cfg, job, transcript)
            except Exception as e:  # noqa: BLE001 - the Inspector must never fail a job
                log_event({"event": "inspector_error", "error": str(e)[:300]})
        return self._brief(job)

    def _apply(self, job: dict, actor: str, parent: Optional[str] = None) -> List[str]:
        jdir = self.store.job_dir(job["task_id"])
        root = Path(job["spec"]["output"]["root"])
        written = []
        for rel in job["result"]["files"]:
            src = jdir / "output" / rel
            dest = (root / rel).resolve()
            if not self.cfg.writable(dest):
                raise CrewError(f"refusing to write {dest}: outside write roots")
            if dest.exists():
                backup = jdir / "backup" / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            written.append(str(dest))
        job["applied"] = {"at": now_iso(), "by": actor, "paths": written}
        self.store.log("output_applied", actor, job["task_id"], parent=parent,
                       paths=written)
        return written

    # -- review ------------------------------------------------------------------------
    def review(self, job_id: str, decision: str, reviewer: str, notes: str = "",
               retry_constraint: str = "", playbook_add: Optional[List[str]] = None,
               accept_member_notes: bool = False,
               must_read: Optional[List[str]] = None,
               ascii_only: bool = False) -> dict:
        if decision not in DECISIONS:
            raise CrewError(f"decision must be one of {DECISIONS}")
        job = self.store.load(job_id)
        st = job["status"]
        if (must_read or ascii_only) and decision != "revise":
            raise CrewError("must_read/ascii_only are gates for the NEXT run; use them with revise")
        if decision == "revise":
            # Turn the reviewer's "do X" into checks the member cannot skip.
            acc = job["spec"].setdefault("acceptance", {})
            if must_read:
                acc["must_read"] = sorted(set(acc.get("must_read", []) + list(must_read)))
            if ascii_only:
                acc["ascii_only"] = True
        node = self.store.log("review_submitted", reviewer, job_id,
                              decision=decision, notes=notes[:1000],
                              retry_constraint=retry_constraint[:1000])
        if decision == "approve":
            if st != REVIEW:
                raise CrewError(f"only jobs in review can be approved ({job_id} is {st})")
            self._apply(job, actor=reviewer, parent=node)
            job["status"] = COMPLETED
        elif decision == "revise":
            if st not in (REVIEW, FAILED):
                raise CrewError(f"only review/failed jobs can be revised ({job_id} is {st})")
            constraint = (retry_constraint or notes).strip()
            if not constraint:
                raise CrewError("revise needs a retry_constraint (what to do differently)")
            if job["revisions"] >= self.cfg.defaults["max_revisions"]:
                raise CrewError(f"{job_id} hit max revisions; reject it or submit a new task")
            job["constraints"].append(constraint)
            job["revisions"] += 1
            job["status"] = READY
            job["notice"] = False
        elif decision == "reject":
            if st in (IN_PROGRESS, COMPLETED, REJECTED):
                raise CrewError(f"{job_id} is {st}; cannot reject")
            job["status"] = REJECTED
        else:  # acknowledge an auto-applied notice
            job["notice"] = False
        if decision in ("approve", "revise", "reject") and job["runs"]:
            self.roster.record_review(job["assigned_to"], job["task_type"], job_id, decision)
        added = []
        for text in playbook_add or []:
            pid = playbook.add(job["task_type"], text, f"review {reviewer} {job_id}")
            added.append(pid or f"duplicate, not added: {text[:50]}")
        if accept_member_notes:
            for text in (job.get("result") or {}).get("notes", []):
                pid = playbook.add(job["task_type"], text,
                                   f"{job['assigned_to']} via {reviewer}")
                added.append(pid or f"duplicate, not added: {text[:50]}")
        if added:
            self.store.log("playbook_updated", reviewer, job_id, parent=node, entries=added)
        job.setdefault("reviews", []).append({"at": now_iso(), "by": reviewer,
                                              "decision": decision, "notes": notes,
                                              "retry_constraint": retry_constraint,
                                              "playbook": added})
        self.store.save(job)
        return {**self._brief(job), "playbook_entries": added}

    # -- views -------------------------------------------------------------------------
    @staticmethod
    def _brief(job: dict) -> dict:
        r = job.get("result") or {}
        return {"task_id": job["task_id"], "title": job["title"],
                "task_type": job["task_type"], "assigned_to": job["assigned_to"],
                "status": job["status"], "revisions": job["revisions"],
                "passed_gates": r.get("passed"), "stop_reason": r.get("stop_reason"),
                "requests": r.get("requests"), "tokens": r.get("tokens"),
                "failed_gates": [f"{s['rung']}: {s['detail']}" for s in r.get("steps", [])
                                 if not s["ok"]][:6],
                "error": r.get("error"),
                "notice": job.get("notice", False)}

    def status(self, job_id: Optional[str] = None, wait_seconds: float = 0) -> object:
        if not job_id:
            return [self._brief(j) for j in self.store.all_jobs()
                    if j["status"] in (BLOCKED, READY, IN_PROGRESS, REVIEW, FAILED)
                    or j.get("notice")]
        deadline = time.time() + max(0.0, min(float(wait_seconds or 0), 50.0))
        while True:
            job = self.store.load(job_id)
            if job["status"] not in (BLOCKED, READY, IN_PROGRESS) or time.time() >= deadline:
                return self._brief(job)
            time.sleep(1.0)

    def result(self, job_id: str) -> dict:
        job = self.store.load(job_id)
        jdir = self.store.job_dir(job_id)
        outputs = {}
        for rel in (job.get("result") or {}).get("files", []):
            p = jdir / "output" / rel
            if p.exists():
                text = p.read_text(encoding="utf-8")
                outputs[rel] = text if len(text) <= RESULT_CHARS else \
                    text[:RESULT_CHARS] + "\n...[truncated]"
        r = job.get("result") or {}
        return {**self._brief(job), "description": job["description"],
                "constraints": job["constraints"], "outputs": outputs,
                "output_target": job["spec"]["output"],
                "gates": r.get("steps", []), "member_notes": r.get("notes", []),
                "files_read": r.get("evidence", []), "runs": job["runs"],
                "harness_autofixes": r.get("autofixes", []),
                "applied": job.get("applied"), "reviews": job.get("reviews", []),
                "error": r.get("error"), "transcript": str(jdir / "transcript.jsonl"),
                "roster_stage": self.roster.stage(job["assigned_to"], job["task_type"])}

    def inbox(self) -> dict:
        jobs = list(self.store.all_jobs())
        return {"needs_review": [self._brief(j) for j in jobs if j["status"] == REVIEW],
                "failed": [self._brief(j) for j in jobs if j["status"] == FAILED],
                "auto_applied_notices": [self._brief(j) for j in jobs if j.get("notice")]}

    # -- worker ------------------------------------------------------------------------
    def tick(self) -> Optional[str]:
        """One scheduling pass. Returns the job id it ran, if any."""
        jobs = {j["task_id"]: j for j in self.store.all_jobs()}
        for j in jobs.values():
            if j["status"] == BLOCKED and all(
                    jobs.get(d, {}).get("status") == COMPLETED for d in j["dependencies"]):
                self._transition(j["task_id"], BLOCKED, READY, "task_unblocked")
            elif j["status"] == IN_PROGRESS and not self.store.claim_active(j["task_id"]):
                # Worker died mid-job and its lease expired. The snapshot above
                # may be stale (the worker may have just FINISHED and released
                # its claim), so _transition re-reads before writing.
                self._transition(j["task_id"], IN_PROGRESS, READY, "task_reclaimed")
        jobs = {j["task_id"]: j for j in self.store.all_jobs()}   # post-transition view
        for j in sorted(jobs.values(), key=lambda x: x["created_at"]):
            if j["status"] != READY:
                continue
            ok, wait, detail = self.rate.gate(j["budget"]["max_requests"])
            if not ok:
                self._hold = wait
                if time.time() - self._hold_logged > 300:
                    self._hold_logged = time.time()
                    self.store.log("rate_hold", "system", j["task_id"], detail=detail)
                return None      # the window is full; nothing may start
            if self.store.try_claim(j["task_id"]):
                try:
                    self.run_job(j["task_id"])
                except CrewError:
                    continue   # another process ran it between scan and claim
                finally:
                    self.store.release(j["task_id"])
                return j["task_id"]
        return None

    def _transition(self, job_id: str, expect: str, to: str, node: str) -> bool:
        """Compare-and-set on a job's status from a FRESH read, so a scan
        snapshot can never overwrite a newer state (2026-09-19: a stale
        snapshot reset a finished job to ready and it ran twice). The
        in-progress -> ready reclaim additionally needs the claim, so two
        workers cannot both reclaim."""
        if expect == IN_PROGRESS:
            if not self.store.try_claim(job_id):
                return False
            try:
                job = self.store.load(job_id)
                if job["status"] != expect:
                    return False
                job["status"] = to
                self.store.save(job)
            finally:
                self.store.release(job_id)
        else:
            job = self.store.load(job_id)
            if job["status"] != expect:
                return False
            job["status"] = to
            self.store.save(job)
        self.store.log(node, "system", job_id)
        return True

    def work_forever(self, poll_seconds: float = 3.0) -> None:
        while not self._stop.is_set():
            self._hold = 0.0
            try:
                ran = self.tick()
            except Exception:  # noqa: BLE001 - keep the worker alive
                traceback.print_exc(file=sys.stderr)
                ran = None
            if not ran:
                # When the request window is full, sleep until it has room
                # (capped so a new job or a config change is still noticed).
                self._stop.wait(min(max(poll_seconds, self._hold), 600.0))

    def start_worker(self) -> threading.Thread:
        t = threading.Thread(target=self.work_forever, name="crew-worker", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()
