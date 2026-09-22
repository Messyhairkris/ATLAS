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


def run_ahk_tests(modules: dict, tests: dict, title: str = "",
                  per_test_timeout_s: int = 30, boot_timeout_s: int = 600,
                  idle_timeout_s: int = 240, keep: bool = False, grants=()) -> dict:
    """{"ok", "summary", "log", "problems", "run_dir"} for one batch of tests.
    `grants` names permissions from GRANTABLE, e.g. ("clipboard",)."""
    problems = static_problems(modules, tests, grants)
    if problems:
        return {"ok": False, "summary": "refused before running",
                "log": "", "problems": problems, "run_dir": ""}

    import verify
    if not _take_lock(boot_timeout_s):
        return {"ok": False, "summary": "another sandbox run held the lock",
                "log": "", "problems": [], "run_dir": ""}
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
                if stage.exists():
                    mark = (stage.stat().st_mtime, stage.read_bytes())
                    if mark != seen:
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
        if ok and not keep:
            shutil.rmtree(run_dir, ignore_errors=True)
        return {"ok": ok, "summary": verdict, "log": log, "problems": [],
                "run_dir": "" if ok and not keep else str(run_dir)}
    finally:
        LOCK.unlink(missing_ok=True)


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    files = {Path(a).name: Path(a).read_text(encoding="utf-8-sig") for a in args}
    tests = {n: s for n, s in files.items() if n.lower().startswith("test")}
    modules = {n: s for n, s in files.items() if n not in tests}
    result = run_ahk_tests(modules, tests)
    print(json.dumps({k: v for k, v in result.items() if k != "log"}, indent=2))
    print(result["log"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
