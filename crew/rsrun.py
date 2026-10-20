"""Compile and test crew-written Rust in a fixed crate, behind the static scan.

The static checks live in crew/rsharness/ (lexer, allowlist scan, API and stub
reader, cargo output reader). This file adds what needs the real machine:

- a PROFILE: a template crate (Cargo.toml + Cargo.lock, rsharness/profiles/<name>/)
  whose dependencies the member cannot change. src/lib.rs is generated as one
  `pub mod` line per module in play; there is no build.rs; cargo runs --offline
  --locked, and doc tests are off, so nothing in a comment is ever executed.
- SLOTS: a few fixed work folders per profile sharing one target directory, so
  dependencies compile once (about 3 minutes cold on the 8 GB workstation) and a
  module rebuilds in seconds. Cargo's own lock serialises compiles.
- a JOB OBJECT around everything that runs: the compile is capped at 4 GB for the
  whole cargo + rustc tree, and each test binary at 2 GB, one process (no
  children) and a timeout. Crash dialogs are suppressed so a stack overflow
  cannot pop a window on the desktop.

Native code has no permission sandbox like Node's, so the allowlist scan
(rs_scan.py) is the wall and the job object only caps resources. That trade-off
is written down in crew/rsharness/README.md.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

HARNESS = Path(__file__).resolve().parent / "rsharness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import cargo_out  # noqa: E402  (crew/rsharness)
import rs_api  # noqa: E402
import rs_scan  # noqa: E402

PROFILES = HARNESS / "profiles"
STATE = Path(__file__).resolve().parent.parent / "runs" / "crew"
SLOTS = 3
COMPILE_TIMEOUT_S = 900
COMPILE_MEMORY_MB = 4096
TEST_MEMORY_MB = 2048
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


# -- profiles ---------------------------------------------------------------------------

def load_profile(name: str) -> dict:
    folder = PROFILES / name
    data = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
    data["name"] = name
    data["folder"] = str(folder)
    return data


# -- Windows job objects ------------------------------------------------------------------

class _Job:
    """A kill-on-close job object with memory caps; a no-op off Windows."""

    def __init__(self, process_mb: int = 0, job_mb: int = 0, one_process: bool = False):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.SetErrorMode(0x0001 | 0x0002)       # no critical-error or crash dialogs

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = Extended()
        flags = 0x2000 | 0x0400                  # KILL_ON_JOB_CLOSE | DIE_ON_UNHANDLED
        if process_mb:
            flags |= 0x0100
            info.ProcessMemoryLimit = process_mb * 1024 * 1024
        if job_mb:
            flags |= 0x0200
            info.JobMemoryLimit = job_mb * 1024 * 1024
        if one_process:
            flags |= 0x0008
            info.BasicLimitInformation.ActiveProcessLimit = 1
        info.BasicLimitInformation.LimitFlags = flags
        self.k32, self.ctypes = k32, ctypes
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle or not k32.SetInformationJobObject(
                self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(f"could not set up a job object ({ctypes.get_last_error()})")

    def adopt(self, proc: subprocess.Popen) -> None:
        if self.handle and not self.k32.AssignProcessToJobObject(
                self.handle, self.ctypes.c_void_p(int(proc._handle))):
            proc.kill()
            raise OSError("could not put the process in its job object")

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None


def _run_contained(argv: List[str], cwd: str, env: dict, timeout_s: int,
                   job: _Job) -> tuple:
    """(returncode, stdout, stderr, timed_out) with the process inside `job`."""
    for attempt in range(20):
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            break
        except PermissionError as e:
            # WinError 32: a freshly linked .exe is still held (the virus scanner reads
            # it first). 2026-10-20 this failed Hoss's dither attempt as "unknown".
            if getattr(e, "winerror", None) != 32 or attempt == 19:
                job.close()
                raise
            time.sleep(0.5)
    try:
        job.adopt(proc)
        out, err = proc.communicate(timeout=timeout_s)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        job.close()                              # kill-on-close takes the whole tree
        proc.kill()
        out, err = proc.communicate()
        return -9, out, err, True
    finally:
        job.close()


# -- slots ------------------------------------------------------------------------------

@contextmanager
def _slot(profile: str, wait_s: int = 1800):
    """One of SLOTS fixed work folders, held by an OS file lock while in use."""
    import msvcrt
    base = STATE / "rs_work" / profile
    base.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait_s
    while True:
        for n in range(SLOTS):
            fh = open(base / f"slot{n}.lock", "a+")
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                fh.close()
                continue
            try:
                yield base / f"slot{n}"
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                fh.close()
            return
        if time.time() > deadline:
            raise TimeoutError("every Rust work slot stayed busy")
        time.sleep(3)


def _cargo_env(profile: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not any(m in k.upper() for m in SECRET_MARKERS)}
    env.update({"CARGO_TARGET_DIR": str(STATE / "rs_target" / profile),
                "CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0",
                "CARGO_TERM_COLOR": "never", "CARGO_NET_OFFLINE": "true",
                "RUSTFLAGS": "", "RUSTDOCFLAGS": ""})
    return env


def _test_env() -> dict:
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATH")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update({"RUST_BACKTRACE": "0", "RUST_TEST_THREADS": "2"})
    return env


def _remove_quietly(exe: Path) -> None:
    """Delete a test binary after its run so the next link writes a fresh file
    rather than overwriting one the virus scanner may still hold."""
    for _ in range(10):
        try:
            exe.unlink(missing_ok=True)
            exe.with_suffix(".pdb").unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.5)


def _write_crate(slot: Path, profile: dict, modules: Dict[str, str],
                 tests: Dict[str, str]) -> None:
    folder = Path(profile["folder"])
    slot.mkdir(parents=True, exist_ok=True)
    for sub in ("src", "tests"):
        shutil.rmtree(slot / sub, ignore_errors=True)
        (slot / sub).mkdir()
    # Each slot is its own PACKAGE (<crate>_slotN) whose library keeps the crate's name,
    # so tests still say `use <crate>::...`. Cargo's output names do not depend on the
    # folder, so with one package name every slot wrote the same test binaries into the
    # shared target directory: on 2026-10-20 parallel campaigns relinked each other's
    # .exe mid-run (LNK1104), deleted it (WinError 2), and linked a test against another
    # slot's library. Dependencies are still compiled once for all slots.
    crate = profile["crate_name"]
    package = f"{crate}_{slot.name}"
    toml = (folder / "Cargo.toml").read_text(encoding="utf-8")
    toml = re.sub(r'(\[package\]\s*\r?\nname\s*=\s*)"[^"]*"', rf'\1"{package}"', toml, count=1)
    toml = re.sub(r"(\[lib\]\s*\r?\n)", rf'\1name = "{crate}"\n', toml, count=1)
    lock = (folder / "Cargo.lock").read_text(encoding="utf-8")
    lock = re.sub(rf'(\[\[package\]\]\s*\r?\nname\s*=\s*)"{re.escape(crate)}"(\s*\r?\nversion)',
                  rf'\1"{package}"\2', lock, count=1)
    if f'"{package}"' not in toml or f'"{package}"' not in lock:
        raise RuntimeError(f"profile {profile['name']}: could not give {slot.name} its own "
                           f"package name (expected [package] name and [lib] in Cargo.toml)")
    (slot / "Cargo.toml").write_text(toml, encoding="utf-8")
    (slot / "Cargo.lock").write_text(lock, encoding="utf-8")
    names = sorted(Path(n).stem for n in modules)
    (slot / "src" / "lib.rs").write_text(
        "".join(f"pub mod {n};\n" for n in names), encoding="utf-8")
    for name, src in modules.items():
        (slot / "src" / name).write_text(src, encoding="utf-8")
    for name, src in tests.items():
        (slot / "tests" / name).write_text(src, encoding="utf-8")


# -- compile and run ----------------------------------------------------------------------

def run_cargo_tests(profile_name: str, modules: Dict[str, str], tests: Dict[str, str],
                    timeout_s: int = 180, hide_tests: bool = True) -> dict:
    """Build `modules` + `tests` in a slot and run every test binary.

    Returns {ok, stage, errors, result, summary, warnings, leftovers, output}.
    stage is 'compile', 'run' or 'done'.
    """
    profile = load_profile(profile_name)
    with _slot(profile_name) as slot:
        _write_crate(slot, profile, modules, tests)
        argv = ["cargo", "test", "--no-run", "--offline", "--locked", "--tests",
                "--message-format=json-render-diagnostics",
                "--manifest-path", str(slot / "Cargo.toml")]
        for tries in range(5):
            code, out, err, late = _run_contained(
                argv, str(slot), _cargo_env(profile_name), COMPILE_TIMEOUT_S,
                _Job(job_mb=COMPILE_MEMORY_MB))
            stdout = out.decode("utf-8", "replace")
            stderr = err.decode("utf-8", "replace")
            # LNK1104: the linker could not replace a test .exe still held by the virus
            # scanner. Ours, not the member's (2026-10-20, Qwen's dither tests).
            if code == 0 or late or "exit code: 1104" not in stderr:
                break
            time.sleep(3 * (tries + 1))
        warnings = cargo_out.warning_count(stderr)
        if late or code != 0:
            errors = cargo_out.compile_errors(
                stderr, ("tests/", "tests\\") if hide_tests else ())
            if late:
                errors = [f"the build did not finish in {COMPILE_TIMEOUT_S}s"]
            if not errors:
                errors = [stderr.strip()[-1500:] or "the build failed with no message"]
            return {"ok": False, "stage": "compile", "errors": errors, "result": None,
                    "summary": "does not compile:\n" + "\n\n".join(errors),
                    "warnings": warnings, "leftovers": [], "output": stderr[-6000:]}
        exes = []
        for line in stdout.splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if (msg.get("reason") == "compiler-artifact" and msg.get("executable")
                    and (msg.get("profile") or {}).get("test")):
                exes.append(msg["executable"])
        texts, ok, leftovers = [], True, []
        for exe in sorted(set(exes)):
            with tempfile.TemporaryDirectory(prefix="crew-rs-") as cwd:
                code, out, err, late = _run_contained(
                    [exe, "--color", "never"], cwd, _test_env(), timeout_s,
                    _Job(process_mb=TEST_MEMORY_MB, one_process=True))
                leftovers += sorted(p.name for p in Path(cwd).iterdir())
            text = out.decode("utf-8", "replace") + err.decode("utf-8", "replace")
            running = [l[len("test "):].split(" ...")[0] for l in text.splitlines()
                       if l.startswith("test ") and " ... " not in l]
            if late:
                text += (f"\nTIMEOUT: {Path(exe).stem} did not finish in {timeout_s}s (an "
                         f"endless loop, or memory use that made the machine page)"
                         + (f"; unfinished: {', '.join(running[:5])}" if running else "")
                         + ".\n")
            elif code not in (0, 101):
                why = [l.strip() for l in text.splitlines()
                       if l.startswith(("memory allocation of", "thread '"))
                       and ("failed" in l or "overflowed" in l)][:2]
                text += (f"\nCRASH: {Path(exe).stem} stopped with code {code}: "
                         + ("; ".join(why) if why else "a stack overflow or the "
                            f"{TEST_MEMORY_MB // 1024} GB memory cap") + ".\n")
            ok = ok and code == 0 and not late
            texts.append(text)
            _remove_quietly(Path(exe))
    output = "\n".join(texts)
    result = cargo_out.parse_libtest(output)
    ok = ok and bool(exes) and result["counts"]["passed"] > 0 \
        and not result["counts"]["failed"] and not leftovers
    summary = cargo_out.summarize(result)
    for marker in ("TIMEOUT:", "CRASH:"):
        summary += "".join(f"\n{l}" for l in output.splitlines() if l.startswith(marker))
    if leftovers:
        summary += "\nthe tests left files behind: " + ", ".join(leftovers)
    return {"ok": ok, "stage": "done", "errors": [], "result": result,
            "summary": summary, "warnings": warnings, "leftovers": leftovers,
            "output": output[-8000:]}


# -- verdicts -----------------------------------------------------------------------------

def judge_module(source: str, api: List[str], deps: Dict[str, str],
                 hidden: Dict[str, str], module_name: str, profile_name: str,
                 timeout_s: int = 180) -> dict:
    """Static rules first, in order; the tests never run after a static rejection."""
    profile = load_profile(profile_name)
    problems = rs_scan.scan(source, profile)
    if problems:
        return {"verdict": "unsafe", "problems": problems}
    missing = rs_api.missing_api(source, api)
    if missing:
        return {"verdict": "missing_api",
                "problems": [f"the contract's API block requires `{m}`, which is not "
                             f"defined as `pub`" for m in missing]}
    stubbed = rs_api.stubs(source)
    if stubbed:
        return {"verdict": "stubbed",
                "problems": [f"{s} is a placeholder, not code" if "!()" in s
                             else f"`{s}` has an empty or placeholder body" for s in stubbed]}
    run = run_cargo_tests(profile_name, {module_name: source, **deps}, hidden, timeout_s)
    if run["stage"] == "compile":
        return {"verdict": "compile_failed", "problems": run["errors"], "run": run}
    if not run["ok"]:
        return {"verdict": "tests_failed", "problems": [run["summary"]], "run": run}
    return {"verdict": "accepted", "problems": [], "run": run}


def judge_tests(source: str, test_name: str, modules: Dict[str, str],
                profile_name: str, min_tests: int, timeout_s: int = 180) -> dict:
    profile = load_profile(profile_name)
    problems = rs_scan.scan(source, profile)
    if problems:
        return {"verdict": "unsafe", "problems": problems}
    count = rs_api.count_tests(source)
    if count < min_tests:
        return {"verdict": "too_few_tests",
                "problems": [f"{count} #[test] functions; the contract asks for at "
                             f"least {min_tests}"]}
    run = run_cargo_tests(profile_name, modules, {test_name: source}, timeout_s,
                          hide_tests=False)
    if run["stage"] == "compile":
        return {"verdict": "compile_failed", "problems": run["errors"], "run": run}
    if not run["ok"]:
        return {"verdict": "tests_failed",
                "problems": ["the tests fail against the real module:\n" + run["summary"]],
                "run": run}
    return {"verdict": "accepted", "problems": [], "run": run}


def static_problems(files: Dict[str, str], profile_name: str) -> List[str]:
    return rs_scan.scan_many(files, load_profile(profile_name))


def module_names(names) -> List[str]:
    return sorted(Path(n).stem for n in names if n.endswith(".rs"))


if __name__ == "__main__":                       # python crew/rsrun.py PROFILE src.rs [tests.rs..]
    prof, mod_path, *test_paths = sys.argv[1:]
    mods = {Path(mod_path).name: Path(mod_path).read_text(encoding="utf-8")}
    tst = {Path(p).name: Path(p).read_text(encoding="utf-8") for p in test_paths}
    res = run_cargo_tests(prof, mods, tst)
    print(res["summary"])
    sys.exit(0 if res["ok"] else 1)
