"""Crew state: jobs, claims, and the action log. Plain files so Kris can read
everything, and so two server processes (Claude Code's and Crush's) can share
one queue on the same machine.

    <state_home>/jobs/<job_id>/job.json     the AtomicTask + its lifecycle
    <state_home>/jobs/<job_id>/transcript.jsonl, output/, backup/
    <state_home>/claims/<job_id>.lock      exclusive claim with a lease
    <state_home>/action_log.jsonl          ActionNode per state change
    <state_home>/outbox/                   default home for shared results

Claims are the proto of CrossTalk's MAIN-arbitrated task_claim: O_EXCL file
creation is the arbiter, and a lease (renewed while working) lets another
process reclaim a job whose worker died.
"""

import datetime
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Iterator, List, Optional

from .config import Config, CrewError

# CrossTalk AtomicTask status vocabulary.
BLOCKED, READY, IN_PROGRESS = "blocked", "ready", "in_progress"
REVIEW, COMPLETED, FAILED, REJECTED = "review", "completed", "failed", "rejected"
OPEN_STATES = (BLOCKED, READY, IN_PROGRESS)
TERMINAL_STATES = (COMPLETED, REJECTED)

_write_lock = threading.Lock()


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _atomic_write(path: Path, text: str, attempts: int = 20) -> None:
    """Write-then-rename. On Windows, os.replace fails with a sharing
    violation (PermissionError) while ANOTHER process has the target open,
    e.g. a second crew server scanning job.json or a lock file. Those
    windows are milliseconds long, so retry briefly instead of failing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == attempts - 1:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            time.sleep(0.05 * (i + 1))


class Store:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.home = cfg.state_home
        self.jobs_dir = self.home / "jobs"
        self.claims_dir = self.home / "claims"
        self.outbox = self.home / "outbox"
        for d in (self.jobs_dir, self.claims_dir, self.outbox):
            d.mkdir(parents=True, exist_ok=True)
        self.action_log = self.home / "action_log.jsonl"
        self.owner = f"{os.environ.get('CREW_CLIENT', 'crew')}-{os.getpid()}"

    # -- jobs ----------------------------------------------------------------
    def new_job_id(self) -> str:
        return (datetime.datetime.now().strftime("job-%Y%m%d-%H%M%S-")
                + secrets.token_hex(2))

    def job_dir(self, job_id: str) -> Path:
        if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise CrewError(f"bad job id: {job_id!r}")
        return self.jobs_dir / job_id

    def load(self, job_id: str) -> dict:
        path = self.job_dir(job_id) / "job.json"
        if not path.exists():
            raise CrewError(f"no such job: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, job: dict) -> None:
        job["updated_at"] = now_iso()
        with _write_lock:
            _atomic_write(self.job_dir(job["task_id"]) / "job.json",
                          json.dumps(job, indent=2, ensure_ascii=False))

    def all_jobs(self) -> Iterator[dict]:
        for d in sorted(self.jobs_dir.iterdir()):
            f = d / "job.json"
            if f.exists():
                try:
                    yield json.loads(f.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue

    # -- action log (ActionNode) -------------------------------------------
    def log(self, type_: str, actor: str, task: str, parent: Optional[str] = None,
            **refs) -> str:
        node_id = "an-" + secrets.token_hex(6)
        node = {"id": node_id, "type": type_, "actor": actor,
                "ts": int(time.time()), "project": self.cfg.project,
                "task": task, "parent": parent, "refs": refs}
        with _write_lock:
            with open(self.action_log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(node, ensure_ascii=False) + "\n")
        return node_id

    def nodes_for(self, task: str) -> List[dict]:
        if not self.action_log.exists():
            return []
        out = []
        for line in self.action_log.read_text(encoding="utf-8").splitlines():
            try:
                n = json.loads(line)
            except json.JSONDecodeError:
                continue
            if n.get("task") == task:
                out.append(n)
        return out

    # -- claims ----------------------------------------------------------------
    def _claim_path(self, job_id: str) -> Path:
        return self.claims_dir / f"{job_id}.lock"

    def try_claim(self, job_id: str) -> bool:
        path = self._claim_path(job_id)
        lease = self.cfg.defaults["lease_seconds"]
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    held = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    held = {"lease_until": 0}
                if held.get("lease_until", 0) > time.time():
                    return False
                try:
                    path.unlink()          # expired lease: reclaim
                except OSError:
                    return False
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"owner": self.owner,
                           "lease_until": time.time() + lease}, fh)
            return True
        return False

    def renew(self, job_id: str) -> None:
        """Extend the lease. Best-effort: the lease is minutes long and
        renewed every model call, so one failed renewal must never kill the
        job it protects (2026-09-19: it did, under parallel runs)."""
        path = self._claim_path(job_id)
        try:
            _atomic_write(path, json.dumps({
                "owner": self.owner,
                "lease_until": time.time() + self.cfg.defaults["lease_seconds"]}))
        except OSError:
            pass

    def release(self, job_id: str) -> None:
        try:
            self._claim_path(job_id).unlink()
        except OSError:
            pass

    def claim_active(self, job_id: str) -> bool:
        path = self._claim_path(job_id)
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return held.get("lease_until", 0) > time.time()
