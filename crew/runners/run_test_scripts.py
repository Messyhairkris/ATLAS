"""Run a project's test files that are standalone SCRIPTS, not pytest cases.

VtoT's suite is written this way: `tests/test_x.py` runs its checks at import
and exits non-zero on failure, so `pytest -q` collects nothing (and its stream
handling breaks pytest's capture). This runner executes each file in its own
process, prints its output, and ends with a pytest-shaped summary line so the
crew's existing gates ("quote the totals verbatim") work unchanged.

    python run_test_scripts.py <project_root> [tests_subdir] [timeout_s]
"""

import subprocess
import sys
import time
from pathlib import Path

SKIP_PREFIXES = ("test_pass",)          # human docs, not executable checks
PER_FILE_DEFAULT = 180


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    tests = root / (sys.argv[2] if len(sys.argv) > 2 else "tests")
    per_file = int(sys.argv[3]) if len(sys.argv) > 3 else PER_FILE_DEFAULT
    files = sorted(p for p in tests.glob("test_*.py")
                   if not p.name.startswith(SKIP_PREFIXES))
    passed, failed, timed_out = [], [], []
    t0 = time.time()
    for f in files:
        print(f"\n===== {f.relative_to(root).as_posix()} " + "=" * 20, flush=True)
        try:
            proc = subprocess.run([sys.executable, str(f)], cwd=str(root),
                                  capture_output=True, text=True, timeout=per_file,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            timed_out.append(f.name)
            print(f"TIMEOUT after {per_file}s")
            continue
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        # Keep the head and tail: failures print at the end, context at the top.
        if len(out) > 4000:
            out = out[:1500] + "\n...[middle trimmed]...\n" + out[-2500:]
        print(out)
        print(f"[exit {proc.returncode}] {f.name}")
        (passed if proc.returncode == 0 else failed).append(f.name)
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    if failed:
        print("FAILED: " + ", ".join(failed))
    if timed_out:
        print("TIMED OUT: " + ", ".join(timed_out))
    print(f"{len(failed) + len(timed_out)} failed, {len(passed)} passed "
          f"in {elapsed:.2f}s")
    return 1 if (failed or timed_out) else 0


if __name__ == "__main__":
    raise SystemExit(main())
