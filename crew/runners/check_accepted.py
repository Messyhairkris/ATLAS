"""Independent verification of every module the crew has had accepted.

The campaign already gates each module on its hidden tests, but it does that
inside the job that produced it. This runner is the audit: it takes whatever is
sitting in the crew workspace now, pairs each module with its hidden tests, runs
them all together in one throwaway directory, and prints pytest-shaped totals.

Why it matters: it proves the accepted set still works TOGETHER (a later module
can break an earlier one), and it is the job a human or a load test can run at
any time without trusting the campaign's own word.

    python crew/runners/check_accepted.py [--workspace DIR] [--verbose]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew import codetask                                    # noqa: E402
from crew.config import load_config                          # noqa: E402

def hidden_for(module_name: str, hidden_dir: Path):
    """The hidden tests that judge this module, by name.

    Convention, not a list: `devices.py` is judged by `test_devices.py` or
    `test_tts_devices.py`. The vendor step looks for the same two names, so a
    module accepted today is audited tomorrow without anybody editing this file -
    which is how the Review Desk modules came to be loaded but never judged.
    """
    stem = Path(module_name).stem
    for candidate in (f"test_{stem}.py", f"test_tts_{stem}.py"):
        path = hidden_dir / candidate
        if path.is_file():
            return path
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="")
    ap.add_argument("--hidden-dir", default=str(REPO_ROOT / "crew" / "hidden_tests"))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    workspace = Path(args.workspace or
                     Path(load_config().state_home) / "outbox" / "workspace")
    hidden_dir = Path(args.hidden_dir)
    t0 = time.time()
    print(f"$ check_accepted {workspace}", flush=True)
    if not workspace.is_dir():
        print(f"no workspace at {workspace}\n\n1 failed, 0 passed in 0.00s")
        return 1

    modules = {p.name: p.read_text(encoding="utf-8")
               for p in sorted(workspace.glob("*.py"))
               if p.name != "__init__.py"}
    if not modules:
        print(f"no accepted modules in {workspace}\n\n1 failed, 0 passed in 0.00s")
        return 1
    tests = {}
    missing = []
    for name in modules:
        path = hidden_for(name, hidden_dir)
        if path:
            tests[path.name] = path.read_text(encoding="utf-8")
        else:
            missing.append(name)

    print(f"modules: {', '.join(sorted(modules))}", flush=True)
    print(f"hidden test files: {', '.join(sorted(tests)) or '(none)'}", flush=True)
    for name in missing:
        print(f"NOTE {name} has no hidden tests registered; it is loaded but not "
              f"judged here", flush=True)
    if not tests:
        print(f"\n1 failed, 0 passed in {time.time() - t0:.2f}s")
        return 1

    ok, out, detail = codetask.run_tests(modules, tests, timeout_s=args.timeout)
    if args.verbose or not ok:
        print(out, flush=True)
    else:
        print(codetask.summarize(out), flush=True)
    if detail.get("unexpected_files"):
        print(f"FAIL the run left files behind: {detail['unexpected_files']}")
        ok = False
    # pytest-shaped totals, so the crew's "quote the totals" gate works on this
    counted = [line for line in out.splitlines()
               if " passed" in line or " failed" in line]
    if counted:
        print(f"\n{counted[-1].strip()}")
    else:
        print(f"\n{0 if ok else 1} failed, {len(tests)} passed in "
              f"{time.time() - t0:.2f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
