"""Run several test jobs at once, on purpose, and measure what it costs the box.

Kris: "I would like to have multiple tests running at once to test system drain
as well. We dont mind stressing the system to test, but dont overload it and
crash it."

So this is a governor, not a fork bomb. Before each new worker starts it checks
CPU load and free memory; if either is past its limit it waits instead of piling
on, and it says so. Every 0.5s it samples CPU percent, memory in use and per-job
RSS, and at the end it reports the peak, the mean, how long each job took, and
whether anything had to be held back.

    python -m crew loadlab crew/campaigns/load_lab.json

The json is {"name", "max_parallel", "cpu_ceiling", "min_free_mb", "jobs": [
  {"id": "...", "argv": ["{python}", "-m", "pytest", "..."], "cwd": "..."} ]}.
Nothing here runs member-written code directly: the jobs are the project's own
suites and the crew's own runners.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List

SAMPLE_SECONDS = 0.5


def _psutil():
    try:
        import psutil
        return psutil
    except ImportError:                                   # pragma: no cover
        return None


class Monitor(threading.Thread):
    """Samples the machine while the jobs run, so 'drain' is a number."""

    def __init__(self):
        super().__init__(daemon=True)
        self.ps = _psutil()
        self.stop = threading.Event()
        self.samples: List[dict] = []
        self.procs: Dict[str, object] = {}
        self.peak_rss: Dict[str, float] = {}

    def add(self, job_id: str, pid: int) -> None:
        if not self.ps:
            return
        try:
            self.procs[job_id] = self.ps.Process(pid)
        except Exception:                                 # noqa: BLE001
            pass

    def run(self) -> None:
        if not self.ps:
            return
        while not self.stop.is_set():
            try:
                cpu = self.ps.cpu_percent(interval=None)
                vm = self.ps.virtual_memory()
                row = {"t": round(time.time(), 2), "cpu_percent": cpu,
                       "mem_percent": vm.percent,
                       "free_mb": round(vm.available / 1e6)}
                for jid, proc in list(self.procs.items()):
                    try:
                        rss = proc.memory_info().rss / 1e6
                        tree = sum(c.memory_info().rss / 1e6
                                   for c in proc.children(recursive=True))
                        total = round(rss + tree, 1)
                        self.peak_rss[jid] = max(self.peak_rss.get(jid, 0), total)
                    except Exception:                     # noqa: BLE001
                        self.procs.pop(jid, None)
                self.samples.append(row)
            except Exception:                             # noqa: BLE001
                pass
            self.stop.wait(SAMPLE_SECONDS)

    def summary(self) -> dict:
        if not self.samples:
            return {"note": "psutil unavailable; no machine samples"}
        cpu = [s["cpu_percent"] for s in self.samples]
        free = [s["free_mb"] for s in self.samples]
        mem = [s["mem_percent"] for s in self.samples]
        return {"samples": len(self.samples),
                "cpu_percent_peak": round(max(cpu), 1),
                "cpu_percent_mean": round(sum(cpu) / len(cpu), 1),
                "mem_percent_peak": round(max(mem), 1),
                "free_mb_low": min(free),
                "peak_rss_mb_per_job": {k: round(v, 1)
                                        for k, v in sorted(self.peak_rss.items())}}


def _headroom(ps, cpu_ceiling: float, min_free_mb: int) -> str:
    """Empty string means there is room for another worker."""
    if not ps:
        return ""
    vm = ps.virtual_memory()
    free_mb = vm.available / 1e6
    if free_mb < min_free_mb:
        return f"only {free_mb:.0f}MB free, floor is {min_free_mb}MB"
    load = ps.cpu_percent(interval=0.3)
    if load > cpu_ceiling:
        return f"cpu at {load:.0f}%, ceiling is {cpu_ceiling:.0f}%"
    return ""


def run_lab(spec: dict) -> dict:
    ps = _psutil()
    name = spec.get("name", "load-lab")
    jobs = spec["jobs"]
    max_parallel = int(spec.get("max_parallel", 3))
    cpu_ceiling = float(spec.get("cpu_ceiling", 85))
    min_free_mb = int(spec.get("min_free_mb", 1500))
    timeout_s = int(spec.get("timeout_s", 1800))
    out_dir = Path(spec.get("out_dir") or ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[lab] {name}: {len(jobs)} jobs, up to {max_parallel} at once, "
          f"cpu ceiling {cpu_ceiling:.0f}%, memory floor {min_free_mb}MB",
          flush=True)
    if not ps:
        print("[lab] psutil is missing, so the governor cannot measure the "
              "machine; running strictly one job at a time instead", flush=True)
        max_parallel = 1

    mon = Monitor()
    mon.start()
    queue = list(jobs)
    running: List[dict] = []
    done: List[dict] = []
    holds: List[dict] = []
    started_at = time.time()

    while queue or running:
        # reap
        for job in list(running):
            proc = job["proc"]
            if proc.poll() is None:
                if time.time() - job["started"] > timeout_s:
                    proc.kill()
                    job["timed_out"] = True
                continue
            job["seconds"] = round(time.time() - job["started"], 1)
            job["returncode"] = proc.returncode
            try:
                job["output"] = proc.stdout.read()[-4000:] if proc.stdout else ""
            except Exception:                             # noqa: BLE001
                job["output"] = ""
            job["peak_rss_mb"] = round(mon.peak_rss.get(job["id"], 0), 1)
            running.remove(job)
            done.append(job)
            state = "ok" if job["returncode"] == 0 else f"exit {job['returncode']}"
            print(f"[lab] finished {job['id']}: {state} in {job['seconds']}s, "
                  f"peak {job['peak_rss_mb']}MB", flush=True)

        # launch
        while queue and len(running) < max_parallel:
            reason = _headroom(ps, cpu_ceiling, min_free_mb)
            if reason:
                holds.append({"at": round(time.time() - started_at, 1),
                              "reason": reason, "waiting": len(queue)})
                print(f"[lab] holding back: {reason} ({len(queue)} job(s) "
                      f"still queued, {len(running)} running)", flush=True)
                break
            spec_job = queue.pop(0)
            argv = [a.replace("{python}", sys.executable) for a in spec_job["argv"]]
            print(f"[lab] starting {spec_job['id']} ({len(running) + 1} running): "
                  f"{' '.join(argv[:6])}", flush=True)
            proc = subprocess.Popen(argv, cwd=spec_job.get("cwd") or None,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace")
            job = {"id": spec_job["id"], "argv": argv, "proc": proc,
                   "started": time.time()}
            running.append(job)
            mon.add(job["id"], proc.pid)
        time.sleep(0.4)

    mon.stop.set()
    mon.join(timeout=2.0)
    machine = mon.summary()
    failed = [j["id"] for j in done if j.get("returncode") != 0]
    result = {
        "name": name, "jobs": len(jobs), "failed": failed,
        "wall_seconds": round(time.time() - started_at, 1),
        "max_parallel_requested": max_parallel,
        "held_back": holds, "machine": machine,
        "per_job": [{k: j.get(k) for k in
                     ("id", "returncode", "seconds", "peak_rss_mb", "timed_out")}
                    for j in done],
    }
    (out_dir / f"{name}-load.json").write_text(
        json.dumps({**result, "outputs": {j["id"]: j.get("output", "")
                                          for j in done}}, indent=2),
        encoding="utf-8")
    print(f"\n[lab] {len(done) - len(failed)} of {len(done)} jobs passed in "
          f"{result['wall_seconds']}s", flush=True)
    if machine.get("samples"):
        print(f"[lab] cpu peak {machine['cpu_percent_peak']}% "
              f"(mean {machine['cpu_percent_mean']}%), memory peak "
              f"{machine['mem_percent_peak']}%, least free "
              f"{machine['free_mb_low']}MB", flush=True)
    if holds:
        print(f"[lab] the governor held work back {len(holds)} time(s); the box "
              f"was the limit, not the crew", flush=True)
    # pytest-shaped totals so the crew's existing gate can quote them
    print(f"\n{len(failed)} failed, {len(done) - len(failed)} passed in "
          f"{result['wall_seconds']:.2f}s", flush=True)
    return result


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m crew loadlab <spec.json>", file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    result = run_lab(spec)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
