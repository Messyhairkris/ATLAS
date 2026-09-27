"""Run crew-written AutoHotkey v1 tests - only inside Windows Sandbox.

Kris, 2026-09-21: "Even though sandbox competes for system resources, it is the
safest way to let our agents work without breaking. AHK can be dangerous to let an
agent loose with, so lets use sandbox for AHK tests especially."

AutoHotkey can press keys in whatever window has focus, launch programs, and show
error dialogs on the real desktop. So there are two walls, and neither is skipped:

1. **Static**, on the host, before anything runs: the crew-built `ahk_scan`
   (banned commands, directives, hotkeys, labels, dynamic references) over every
   module and test file. A refusal here never boots a sandbox.
2. **Runtime**, inside a disposable Windows Sandbox with networking, clipboard,
   audio and printers disabled, AutoHotkey mapped read-only. The in-sandbox
   runner (`experiments/sandbox/runner.ps1`, kind "ahk") shows the status window
   Kris asked for, runs each test file in its own process with a timeout, and
   writes TAP back through the one writable folder.

The run folder is deleted on a pass and kept on a failure. Windows 10 allows one
sandbox at a time, so runs take a lock and queue.

    python -m crew.ahkrun module.ahk test_module.ahk
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "experiments"))
sys.path.insert(0, str(REPO_ROOT / "runs" / "crew" / "outbox" / "workspace" / "ahk"))

AHK_DIR = Path(os.environ.get("ATLAS_AHK_DIR", r"C:\Program Files\AutoHotkey"))
AHK_EXE = "AutoHotkeyU64.exe"
TAP_LIB = Path(__file__).resolve().parent / "ahk" / "tap.ahk"
LOCK = Path(os.environ.get("ATLAS_WSB_SHARE", r"C:\ATLAS-wsb")) / "sandbox.lock"
# Warm sandbox (Kris, 2026-09-26): one sandbox serves many runs; a fresh boot only
# when there is none, it went idle or dirty, served WARM_MAX_JOBS, or fresh=True.
WARM = Path(os.environ.get("ATLAS_WSB_SHARE", r"C:\ATLAS-wsb")) / "warm"
WARM_ENABLED = os.environ.get("ATLAS_WSB_WARM", "1") != "0"
WARM_IDLE_S = int(os.environ.get("ATLAS_WSB_WARM_IDLE_S", "900"))
WARM_MAX_JOBS = int(os.environ.get("ATLAS_WSB_WARM_MAX_JOBS", "25"))
WARM_TEMPLATE = """<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <PrinterRedirection>Disable</PrinterRedirection>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MemoryInMB>{memory_mb}</MemoryInMB>
  <MappedFolders>
    <MappedFolder><HostFolder>{warm}</HostFolder><ReadOnly>false</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{ahk}</HostFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>{tools}</HostFolder><ReadOnly>true</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{desktop}\\{tools_name}\\warm_runner.ps1" -WarmDir "{desktop}\\{warm_name}" -ToolsDir "{desktop}\\{tools_name}"</Command>
  </LogonCommand>
</Configuration>
"""


# Words a task may be granted. Kris, 2026-09-21: "Clipboard is a tool that will be
# used often... many ahk tools use it to deliver information." Inside the sandbox
# the clipboard is the sandbox's own (host clipboard redirection is off), so a
# clipboard tool can be tested without touching Kris's real clipboard. The
# permission is per task, named in the contract, never a blanket change to BANNED.
GRANTABLE = {
    "clipboard": {"clipboard", "clipboardall", "onclipboardchange"},
}


def _permitted(problem: str, words: set) -> bool:
    quoted = re.search(r"'([^']+)' is not allowed", problem)
    return bool(quoted) and quoted.group(1).lower() in words


def static_problems(modules: dict, tests: dict, grants=()) -> list:
    """Wall one: the crew-built scanner over every file, before any sandbox."""
    import ahk_scan
    words = set().union(*(GRANTABLE[g] for g in grants)) if grants else set()
    unknown = [g for g in grants if g not in GRANTABLE]
    if unknown:
        return [f"unknown grant(s): {', '.join(unknown)}; grantable: {sorted(GRANTABLE)}"]
    out = []
    for name, source in modules.items():
        out += [f"{name}: {p}" for p in ahk_scan.problems(source)]
    includes = list(modules) + ["tap.ahk"]
    for name, source in tests.items():
        out += [f"{name}: {p}" for p in ahk_scan.problems(source, includes)]
    return [p for p in out if not _permitted(p, words)]


def _take_lock(wait_s: int) -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            LOCK.touch(exist_ok=False)
            return True
        except FileExistsError:
            if time.time() - LOCK.stat().st_mtime > 1800:
                LOCK.unlink(missing_ok=True)      # a crashed run's stale lock
            time.sleep(5)
    return False


_CHECK_NAME = re.compile(r'^\s*(?:Is|Ok)\(.*,\s*"((?:[^"]|"")*)"\s*\)\s*$')


def check_names(test_source: str) -> list:
    """The name of every Is/Ok check, in file order (its last string argument)."""
    out = []
    for line in test_source.splitlines():
        m = _CHECK_NAME.match(line)
        if m:
            out.append(m.group(1).replace('""', '"'))
    return out


def explain_timeouts(verdict: str, run_dir: Path, tests: dict) -> str:
    """A bare "timed out after 30s" told Nemotron nothing twice (2026-09-26). The
    TAP file is written check by check, so it shows how far the tests got; the
    next check's name says where the module hangs."""
    notes = []
    for name, source in tests.items():
        if f"{name}: timed out" not in verdict:
            continue
        tap = run_dir / f"{name}.tap"
        lines = tap.read_text(encoding="utf-8-sig", errors="replace").splitlines() \
            if tap.exists() else []
        done = sum(1 for ln in lines if re.match(r"(not )?ok \d+", ln))
        names = check_names(source)
        if done < len(names):
            notes.append(f"{name}: {done} check(s) finished, then it hung during check "
                         f"{done + 1} ('{names[done]}') - look for a loop that never ends "
                         f"there")
        else:
            notes.append(f"{name}: all {done} checks finished, but the file never reached "
                         f"Done() - something after the last check (or a check's value "
                         f"being built) never returned")
    return verdict + ("\n" + "\n".join(notes) if notes else "")


def _heartbeat_age() -> float:
    try:
        return time.time() - (WARM / "heartbeat.txt").stat().st_mtime
    except OSError:
        return 1e9


def warm_alive() -> bool:
    """A warm sandbox that is up, serving, clean, and saying so every second."""
    return (WARM_ENABLED and (WARM / "ready_for_jobs.txt").exists()
            and not (WARM / "stopped.txt").exists() and not (WARM / "dirty.txt").exists()
            and _heartbeat_age() < 15)


def _boot_warm(boot_timeout_s: int) -> bool:
    import verify
    verify._kill_sandbox()                        # Windows 10: one sandbox at a time
    time.sleep(2)
    shutil.rmtree(WARM, ignore_errors=True)
    (WARM / "inbox").mkdir(parents=True, exist_ok=True)
    (WARM / "warm.json").write_text(json.dumps({
        "exe_dir": f"{verify.WSB_DESKTOP}\\{AHK_DIR.name}", "exe": AHK_EXE,
        "idle_s": WARM_IDLE_S, "max_jobs": WARM_MAX_JOBS, "debloat": True}, indent=2),
        encoding="utf-8")
    wsb = WARM / "warm.wsb"
    wsb.write_text(WARM_TEMPLATE.format(
        memory_mb=verify.WSB_MEMORY_MB, warm=str(WARM), ahk=str(AHK_DIR),
        tools=str(verify.SANDBOX_TOOLS), desktop=verify.WSB_DESKTOP,
        tools_name=verify.SANDBOX_TOOLS.name, warm_name=WARM.name), encoding="utf-8")
    for attempt in (1, 2):                        # one warm retry for a cold boot
        subprocess.Popen(["cmd", "/c", "start", "", str(wsb)],
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        deadline = time.time() + boot_timeout_s
        while time.time() < deadline:
            if warm_alive():
                return True
            if (WARM / "heartbeat.txt").exists():
                deadline = max(deadline, time.time() + 120)   # booted, still trimming
            time.sleep(2)
        verify._kill_sandbox()
        if (WARM / "heartbeat.txt").exists():
            break
    return False


def _run_warm(modules: dict, tests: dict, title: str, per_test_timeout_s: int,
              boot_timeout_s: int, keep: bool):
    """Run one batch in the warm sandbox; None means "use a fresh one instead"."""
    booted = False
    if not warm_alive():
        if not _boot_warm(boot_timeout_s):
            return None
        booted = True
    run_id = f"ahk-{int(time.time() * 1000)}"
    job_dir = (WARM / "inbox" / run_id).resolve()
    job_dir.mkdir(parents=True)
    for name, source in {**modules, **tests}.items():
        (job_dir / name).write_text(source, encoding="utf-8-sig")
    shutil.copy(TAP_LIB, job_dir / "tap.ahk")
    (job_dir / "job.json").write_text(json.dumps({
        "run_id": run_id, "title": title or f"AutoHotkey tests: {', '.join(tests)}",
        "tests": sorted(tests), "per_test_timeout_s": per_test_timeout_s}, indent=2),
        encoding="utf-8")
    (job_dir / "ready.txt").write_text("ready", encoding="ascii")    # written LAST
    done = job_dir / "runner_done.txt"
    deadline = time.time() + per_test_timeout_s * max(1, len(tests)) + 90
    while time.time() < deadline and not done.exists():
        if _heartbeat_age() > 30 or (WARM / "stopped.txt").exists():
            break                                 # the box died or left mid-run
        time.sleep(1)
    if not done.exists():
        import verify
        verify._kill_sandbox()
        return None
    time.sleep(0.3)
    verdict = done.read_text(encoding="ascii", errors="replace").strip()
    log = (job_dir / "run.log").read_text(encoding="utf-8-sig", errors="replace") \
        if (job_dir / "run.log").exists() else ""
    ok = verdict.startswith("PASS")
    if not ok:
        verdict = explain_timeouts(verdict, job_dir, tests)
    if ok and not keep:
        shutil.rmtree(job_dir, ignore_errors=True)
    return {"ok": ok, "summary": verdict, "log": log, "problems": [],
            "run_dir": "" if ok and not keep else str(job_dir),
            "sandbox": "warm (booted now)" if booted else "warm (reused)"}


def run_ahk_tests(modules: dict, tests: dict, title: str = "",
                  per_test_timeout_s: int = 30, boot_timeout_s: int = 600,
                  idle_timeout_s: int = 240, keep: bool = False, grants=(),
                  fresh: bool = False) -> dict:
    """{"ok", "summary", "log", "problems", "run_dir", "sandbox"} for one batch.
    `grants` names permissions from GRANTABLE, e.g. ("clipboard",). The warm
    sandbox is used unless fresh=True (or ATLAS_WSB_WARM=0); if it cannot serve
    the run, a fresh single-run sandbox does."""
    problems = static_problems(modules, tests, grants)
    if problems:
        return {"ok": False, "summary": "refused before running",
                "log": "", "problems": problems, "run_dir": ""}
    if not _take_lock(boot_timeout_s):
        return {"ok": False, "summary": "another sandbox run held the lock",
                "log": "", "problems": [], "run_dir": ""}
    try:
        if WARM_ENABLED and not fresh:
            r = _run_warm(modules, tests, title, per_test_timeout_s, boot_timeout_s, keep)
            if r is not None:
                return r
        elif warm_alive():                         # a fresh run needs the one sandbox slot
            (WARM / "stop.txt").write_text("fresh run requested", encoding="ascii")
            import verify
            verify._kill_sandbox()
        r = _run_cold(modules, tests, title, per_test_timeout_s, boot_timeout_s,
                      idle_timeout_s, keep)
        r["sandbox"] = "fresh"
        return r
    finally:
        LOCK.unlink(missing_ok=True)


def _run_cold(modules: dict, tests: dict, title: str, per_test_timeout_s: int,
              boot_timeout_s: int, idle_timeout_s: int, keep: bool) -> dict:
    """The original single-run sandbox: boot, run this batch, shut down."""
    import verify
    run_id = f"ahk-{int(time.time())}"
    run_dir = (verify.WSB_SHARE_ROOT / run_id).resolve()
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        for name, source in {**modules, **tests}.items():
            (run_dir / name).write_text(source, encoding="utf-8-sig")
        shutil.copy(TAP_LIB, run_dir / "tap.ahk")
        job = {
            "run_id": run_id, "kind": "ahk",
            "title": title or f"AutoHotkey tests: {', '.join(tests)}",
            "stages": ["Sandbox booted", "Trimming Windows", "Running AutoHotkey tests",
                       "Checking results", "Done"],
            "exe_dir": f"{verify.WSB_DESKTOP}\\{AHK_DIR.name}", "exe": AHK_EXE,
            "godot_dir": f"{verify.WSB_DESKTOP}\\{AHK_DIR.name}",
            "tests": sorted(tests), "per_test_timeout_s": per_test_timeout_s,
            "timeout_s": per_test_timeout_s * max(1, len(tests)) + 60, "debloat": True,
            "linger_s": verify.WSB_LINGER_S,
        }
        (run_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
        wsb = run_dir / f"{run_id}.wsb"
        wsb.write_text(verify.build_wsb_config(run_dir, AHK_DIR), encoding="utf-8")

        done = run_dir / "runner_done.txt"
        stage = run_dir / "stage.txt"
        finished = False
        for attempt in (1, 2):            # one warm retry for a cold boot (Kris's rule)
            subprocess.Popen(["cmd", "/c", "start", "", str(wsb)],
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            # Kris's box took more than 4 minutes to boot a sandbox, and the first
            # version killed a runner that was working. Now: boot_timeout_s to
            # show a first stage, then any further progress resets an idle clock.
            deadline = time.time() + boot_timeout_s
            seen = None
            while time.time() < deadline and not done.exists():
                try:                      # the runner may be writing it right now
                    mark = (stage.stat().st_mtime, stage.read_bytes()) \
                        if stage.exists() else None
                except OSError:           # (2026-09-26: a locked stage.txt crashed a job)
                    mark = seen
                if mark is not None and mark != seen:
                    seen = mark
                    deadline = time.time() + idle_timeout_s
                time.sleep(2)
            if done.exists():
                finished = True
                time.sleep(verify.WSB_LINGER_S)
                break
            verify._kill_sandbox()
            if stage.exists():
                break                     # the runner started: a real failure
        verify._kill_sandbox()

        log = (run_dir / "run.log").read_text(encoding="utf-8-sig", errors="replace") \
            if (run_dir / "run.log").exists() else ""
        verdict = done.read_text(encoding="ascii", errors="replace").strip() \
            if finished else "FAIL sandbox runner never finished"
        ok = verdict.startswith("PASS")
        if not ok:
            verdict = explain_timeouts(verdict, run_dir, tests)
        if ok and not keep:
            shutil.rmtree(run_dir, ignore_errors=True)
        return {"ok": ok, "summary": verdict, "log": log, "problems": [],
                "run_dir": "" if ok and not keep else str(run_dir)}
    finally:
        pass


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    fresh = "--fresh" in args           # confirm on a clean boot (Kris, 2026-09-26)
    args = [a for a in args if a != "--fresh"]
    files = {Path(a).name: Path(a).read_text(encoding="utf-8-sig") for a in args}
    tests = {n: s for n, s in files.items() if n.lower().startswith("test")}
    modules = {n: s for n, s in files.items() if n not in tests}
    result = run_ahk_tests(modules, tests, fresh=fresh)
    print(json.dumps({k: v for k, v in result.items() if k != "log"}, indent=2))
    print(result["log"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
