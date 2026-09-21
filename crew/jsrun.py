"""Run crew-written JavaScript under Node, judged by the crew-built JS harness.

The static checks (lexer, import allowlist, forbidden globals, API, stubs) and the
TAP parsing live in crew/jsharness/ - modules the crew wrote in the js-harness
campaign (2026-09-21) and that passed hidden tests before they were moved here.
This file only adds what needs the real machine: a throwaway directory and Node.

Node runs with its permission model on (`--permission`): it may read the throwaway
directory and nothing else, may not write, spawn processes, or load addons. That
is a second wall behind the static scan, not a replacement for it.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent / "jsharness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import js_gate  # noqa: E402  (crew-built, lives in crew/jsharness)
import js_imports  # noqa: E402
import node_tap  # noqa: E402

TEST_IMPORTS = {"node:test", "node:assert", "node:assert/strict"}


def node_exe() -> str:
    return shutil.which("node") or "node"


def run_node_tests(modules: dict, test_files: dict, timeout_s: int = 180) -> tuple:
    """(passed, TAP text, details). modules/test_files are {filename: source}."""
    with tempfile.TemporaryDirectory(prefix="crew-js-") as tmp:
        work = Path(tmp)
        (work / "package.json").write_text('{"type": "module"}', encoding="utf-8")
        for name, src in {**modules, **test_files}.items():
            (work / name).write_text(src, encoding="utf-8")
        argv = [node_exe(), "--permission", f"--allow-fs-read={work}", "--test",
                "--test-isolation=none", "--test-reporter=tap", *sorted(test_files)]
        env = {k: v for k, v in os.environ.items()
               if k in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "PATHEXT",
                        "WINDIR", "NUMBER_OF_PROCESSORS")}
        try:
            proc = subprocess.run(argv, cwd=str(work), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=timeout_s, env=env)
            out = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
        except subprocess.TimeoutExpired:
            out = (f"TIMEOUT: the tests did not finish in {timeout_s}s. An infinite "
                   f"loop counts as a failure.\n# fail 1\n")
            code = -9
        leftovers = sorted(p.name for p in work.iterdir()
                           if p.name not in modules and p.name not in test_files
                           and p.name != "package.json")
    counts = node_tap.parse_tap(out)["counts"]
    passed = (code == 0 and counts.get("pass", 0) > 0
              and not counts.get("fail", 0) and not counts.get("cancelled", 0))
    return passed, out[-8000:], {"returncode": code, "unexpected_files": leftovers,
                                 "counts": counts}


def summarize(tap: str) -> str:
    """The failing lines and the totals, small enough to feed back to a member."""
    result = node_tap.parse_tap(tap)
    failing = [t["name"] for t in result["tests"] if not t["ok"] and not t["skip"]]
    lines = [f"not ok - {n}" for n in failing[:20]]
    detail = [ln for ln in tap.splitlines()
              if ln.strip().startswith(("error:", "expected:", "actual:", "Error",
                                        "SyntaxError", "TypeError", "TIMEOUT"))]
    return "\n".join(lines + detail[:20] + [node_tap.summary_line(result)])


def judge_module(source: str, api: list, deps: dict, hidden: dict,
                 module_name: str, timeout_s: int = 180) -> dict:
    """The crew-built gate decides; run_tests is the only part that touches Node."""
    allowed = {f"./{name}" for name in deps}

    def run_tests(src: str) -> str:
        return run_node_tests({module_name: src, **deps}, hidden, timeout_s)[1]

    return js_gate.judge(source, list(api), allowed, run_tests)


def scan_test_file(source: str, module_names) -> list:
    """Problems that stop a crew test file from being executed."""
    allowed = TEST_IMPORTS | {f"./{n}" for n in module_names}
    return ([f"forbidden global: {n}" for n in js_imports.forbidden_uses(source)]
            + [f"import not allowed: {s}"
               for s in js_imports.check_imports(source, allowed)])
