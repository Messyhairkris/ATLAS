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

2026-10-25 (Gordon, from a PA chat): a job ran twice. The lease was renewed only
when a model call began, and one call may take 15 minutes; a gate run renewed
nothing. Another worker saw the lease run out, reclaimed the job and ran it again
while the first was still working, and the first then renewed and released the
claim it no longer owned. Now `keep()` renews the claim on a heartbeat of its own
for as long as the job runs, renew and release touch only a claim this process
owns, and a lapsed lease whose owner process is still alive (a PC waking from
sleep before the heartbeat has run) is not taken for a dead worker.
"""

import contextlib
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


def _process_started(pid: int) -> Optional[float]:
    """When process `pid` started (epoch seconds), or None if it is gone or we cannot
    tell (psutil missing). The start time tells a live owner from a new process that
    was given a dead owner's pid."""
    try:
        import psutil
        return psutil.Process(int(pid)).create_time()
    except Exception:  # noqa: BLE001 - no such process, no access, no psutil
        return None


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

    def load(self, job_id: str, attempts: int = 20) -> dict:
        """The job. A read can meet another process's write-then-rename of the same
        file (Windows: PermissionError for those milliseconds); retry briefly, as
        _atomic_write does, instead of failing the scan (2026-10-25, two workers)."""
        path = self.job_dir(job_id) / "job.json"
        if not path.exists():
            raise CrewError(f"no such job: {job_id}")
        for i in range(attempts):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except PermissionError:
                if i == attempts - 1:
                    raise
                time.sleep(0.05 * (i + 1))
        raise CrewError(f"cannot read {path}")

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

    def _read_claim(self, job_id: str) -> Optional[dict]:
        """The claim, or None when there is none. One that cannot be read (being
        replaced this instant, or left empty by a crash between creating and filling
        it) is read again, then judged by its age: a lease taken to begin when the
        file was last written, and no owner - it is never mistaken for a dead one
        while it may still be live."""
        path = self._claim_path(job_id)
        for attempt in range(3):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            except (OSError, json.JSONDecodeError):
                time.sleep(0.02 * (attempt + 1))
        try:
            return {"lease_until": path.stat().st_mtime + self.cfg.defaults["lease_seconds"]}
        except OSError:
            return None

    def _held(self, claim: dict) -> bool:
        """Is this claim still somebody's? Its lease runs; or the lease lapsed but
        the process that took it is alive (the same process: it started before the
        claim was taken) and has held it for less than claim_max_hours. A claim with
        no pid (written before 2026-10-25) lives by its lease alone."""
        now = time.time()
        if claim.get("lease_until", 0) > now:
            return True
        pid, since = claim.get("pid"), float(claim.get("since") or 0)
        cap = float(self.cfg.defaults.get("claim_max_hours", 6)) * 3600
        if not pid or now - since > cap:
            return False
        started = _process_started(pid)
        return started is not None and started <= since + 1.0

    def try_claim(self, job_id: str) -> bool:
        path = self._claim_path(job_id)
        lease = self.cfg.defaults["lease_seconds"]
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                held = self._read_claim(job_id) or {"lease_until": 0}
                if self._held(held):
                    return False
                try:
                    path.unlink()          # its worker is gone: reclaim
                except OSError:
                    return False
                continue
            now = time.time()
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"owner": self.owner, "pid": os.getpid(), "since": now,
                           "lease_until": now + lease}, fh)
            return True
        return False

    def renew(self, job_id: str) -> bool:
        """Extend the lease of a claim this process owns; False when it is not
        ours any more (gone, or another worker's). Best-effort: one failed write
        must never kill the job it protects (2026-09-19: it did, under parallel
        runs), and the heartbeat tries again within a third of the lease."""
        held = self._read_claim(job_id)
        if held is None:
            return False
        if "owner" not in held:
            return True                    # unreadable just now: try at the next beat
        if held["owner"] != self.owner:
            return False
        held["lease_until"] = time.time() + self.cfg.defaults["lease_seconds"]
        try:
            _atomic_write(self._claim_path(job_id), json.dumps(held))
        except OSError:
            pass
        return True

    def release(self, job_id: str) -> None:
        """Give up a claim this process owns. Another worker's claim is left alone:
        a worker that lost its claim must not free the job from under the new owner."""
        held = self._read_claim(job_id)
        if held is not None and held.get("owner") != self.owner and self._held(held):
            return
        try:
            self._claim_path(job_id).unlink()
        except OSError:
            pass

    def claim_active(self, job_id: str) -> bool:
        held = self._read_claim(job_id)
        return held is not None and self._held(held)

    @contextlib.contextmanager
    def keep(self, job_id: str):
        """Hold the claim for as long as the work inside runs: renewed every third
        of the lease on a thread of its own, whatever the job is doing (a 15-minute
        model call, a gate's test run). Yields an Event that is set if the claim
        was found to be someone else's. Stops renewing after claim_max_hours, so a
        hung job is reclaimed in the end."""
        lease = float(self.cfg.defaults["lease_seconds"])
        cap = float(self.cfg.defaults.get("claim_max_hours", 6)) * 3600
        every, started = max(0.05, lease / 3), time.time()
        stop, lost = threading.Event(), threading.Event()

        def beat() -> None:
            while not stop.wait(every):
                if time.time() - started > cap:
                    return
                if not self.renew(job_id):
                    lost.set()
                    return

        thread = threading.Thread(target=beat, name=f"claim-{job_id}", daemon=True)
        thread.start()
        try:
            yield lost
        finally:
            stop.set()
            thread.join(timeout=every + 1)
