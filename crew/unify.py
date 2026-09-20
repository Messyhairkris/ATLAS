"""Unify: make crew-written code look like one hand wrote it, with no LLM.

Kris, 2026-09-20: "for mechanical fixes, is there a way to automate this so it
never needs to be addressed by an LLM? As CrossTalk core design principles is to
automate things that can be."

Yes, for everything mechanical. The 64 lint findings in the first campaign broke
down like this:

  * import order, unused imports, unused locals, dated typing (`List` -> `list`,
    `Optional[str]` -> `str | None`), whitespace, line length, comprehension and
    return-statement simplifications -> ALL of it is a deterministic rewrite that
    a formatter and a linter can do, correctly, every time, for free;
  * a fabricated docstring, a duplicated result dict, a wrong type hint, an
    `assert False` where `pytest.raises` belongs, an id consumed by a refused
    enqueue -> these need a reader. A tool can FLAG them; it must not guess.

So this module does the first list and reports the second. It is not a style
opinion engine: it runs `ruff`, which is the same tool a human would run.

**The safety rule, which is the whole design:** a mechanical fix is only kept if
the module still passes its tests afterwards. Each stage is applied, verified,
and reverted on failure - so an "automatic cleanup" can never quietly change
behavior. Anything ruff calls an unsafe fix is held to the same standard as the
safe ones: prove it, or lose it.

    python -m crew unify devices.py --test test_tts_devices.py --dep verbalize.py
    python -m crew unify --workspace            # every accepted module, paired
                                                # with its hidden tests
    python -m crew unify --workspace --check    # report only, change nothing

Deliberately NOT wired into the gate pipeline yet: Kris wants to test the crew's
unaided output first, then the unified version, and only then let this run inside
the crew (his words: "After the successful completion of this test, any
automation, linters, regex passes can be added to the base Crew MCP").
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import codetask
from .config import REPO_ROOT, load_config

# Rules that are mechanical: a machine can apply them and a reader will agree.
# Deliberately excludes anything that renames things, rewrites logic, or edits
# prose - those are a human's call.
MECHANICAL = ("I",      # import order
              "F401",   # unused imports
              "F841",   # unused local variables
              "UP",     # modern typing and syntax for the running Python
              "E",      # pycodestyle errors, including line length
              "W",      # pycodestyle warnings, trailing whitespace
              "C4",     # comprehension shortcuts
              "SIM1",   # trivially simplifiable conditionals
              "RET5",   # unnecessary else/return branches
              "PIE",    # small idiom fixes
              )
# Findings that a tool must NOT touch: each needs someone to read the intent.
# Chosen per file kind, because a report full of noise is a report nobody reads:
# nobody annotates `-> None` on a pytest function, and the first version of this
# tool listed twenty of those on one test file.
NEEDS_A_READER_MODULE = {
    "ANN401": "an argument typed `Any`: the real type is a design decision, not a "
              "transformation",
    "D1": "a missing docstring, or one that restates the filename instead of "
          "saying why - prose is never mechanical",
    "N8": "a name that breaks convention: renaming is an API change",
    "ARG": "an unused argument: it is either dead or part of an interface",
    "PLR09": "too many branches or arguments: the fix is a redesign",
}
NEEDS_A_READER_TEST = {
    "B011": "an `assert False` that vanishes under `python -O`: it must become "
            "pytest.raises, which changes what the test MEANS",
    "PT": "a pytest-style finding: how a test expresses an expectation is the "
          "test's meaning, not its formatting",
    "ARG": "an unused fixture or argument: either the test forgot it or it is "
           "dead weight",
}
LINE_LENGTH = 88


def _ruff(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ruff", *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def findings(path: Path, select: Tuple[str, ...] = MECHANICAL,
             preview: bool = False) -> List[str]:
    """Ruff's concise output, one finding per line."""
    args = ["check", "--no-cache", "--select", ",".join(select),
            "--line-length", str(LINE_LENGTH), "--output-format", "concise"]
    if preview:
        args.append("--preview")
    args.append(path.name)
    out = _ruff(args, path.parent)
    return [ln for ln in (out.stdout or "").splitlines() if ":" in ln and path.name in ln]


def _verify(module: Path, deps: List[Path], tests: List[Path],
            is_test_file: bool = False) -> Tuple[bool, str]:
    """Does it still do what it did, with the file as it now stands?

    This is what makes automatic rewriting safe rather than hopeful, and it cuts
    both ways:
      * a MODULE is correct if its tests still pass;
      * a TEST FILE is correct if it still passes against the module it tests - a
        "cleanup" that quietly made a test stop testing would be worse than the
        lint it fixed.
    The airlock scan runs again either way, so a cleanup can never widen what the
    code is allowed to do.
    """
    names = {d.stem for d in deps} | {"pytest"}
    if is_test_file:
        mods = {d.name: d.read_text(encoding="utf-8") for d in deps}
        test_src = {module.name: module.read_text(encoding="utf-8")}
        blocked = codetask.scan(test_src[module.name], module.name,
                                extra_imports=names)
    else:
        mods = {module.name: module.read_text(encoding="utf-8")}
        for dep in deps:
            mods[dep.name] = dep.read_text(encoding="utf-8")
        blocked = codetask.scan(mods[module.name], module.name,
                                extra_imports=[d.stem for d in deps])
        test_src = {t.name: t.read_text(encoding="utf-8") for t in tests}
    if blocked:
        return False, "the safety scan refused the rewritten file: " + "; ".join(blocked)
    if not test_src:
        return True, "nothing to run it against, so nothing could be verified (weaker)"
    ok, out, _ = codetask.run_tests(mods, test_src, timeout_s=300,
                                    extra_imports=names)
    return ok, ("tests pass" if ok else codetask.summarize(out))


def _stage(label: str, module: Path, deps: List[Path], tests: List[Path],
           run, log: List[dict], is_test_file: bool = False) -> bool:
    """Apply one mechanical stage, keep it only if the tests still pass."""
    before = module.read_text(encoding="utf-8")
    run()
    after = module.read_text(encoding="utf-8")
    if before == after:
        log.append({"stage": label, "result": "nothing to change"})
        return False
    ok, detail = _verify(module, deps, tests, is_test_file)
    if not ok:
        module.write_text(before, encoding="utf-8")
        log.append({"stage": label, "result": "REVERTED", "why": detail})
        return False
    log.append({"stage": label, "result": "kept",
                "lines_before": len(before.splitlines()),
                "lines_after": len(after.splitlines())})
    return True


def unify_file(module: Path, tests: List[Path], deps: Optional[List[Path]] = None,
               check_only: bool = False) -> dict:
    """Clean one file mechanically. Returns what changed and what a human must do."""
    deps = deps or []
    is_test = module.name.startswith("test_")
    before_text = module.read_text(encoding="utf-8")
    before = findings(module)
    report = {"file": module.name, "findings_before": len(before),
              "stages": [], "kept_any": False}

    if check_only:
        report["would_fix"] = before
        report["needs_a_reader"] = _reader_items(module)
        return report

    ok, detail = _verify(module, deps, tests, is_test)
    if not ok:
        report["refused"] = ("the file does not pass its tests BEFORE cleanup, so "
                            "nothing can be verified: " + detail)
        return report

    log: List[dict] = []
    sel = ",".join(MECHANICAL)
    changed = False
    changed |= _stage(
        "safe fixes", module, deps, tests,
        lambda: _ruff(["check", "--no-cache", "--fix", "--select", sel,
                       "--line-length", str(LINE_LENGTH), module.name],
                      module.parent), log, is_test)
    changed |= _stage(
        "unsafe fixes (verified)", module, deps, tests,
        lambda: _ruff(["check", "--no-cache", "--fix", "--unsafe-fixes",
                       "--select", sel, "--line-length", str(LINE_LENGTH),
                       module.name], module.parent), log, is_test)
    changed |= _stage(
        "format", module, deps, tests,
        lambda: _ruff(["format", "--no-cache", "--line-length", str(LINE_LENGTH),
                       module.name], module.parent), log, is_test)

    report["stages"] = log
    report["kept_any"] = changed
    report["findings_after"] = len(findings(module))
    report["needs_a_reader"] = _reader_items(module)
    report["lines_before"] = len(before_text.splitlines())
    report["lines_after"] = len(module.read_text(encoding="utf-8").splitlines())
    return report


def _reader_items(path: Path) -> List[dict]:
    """What the tool refuses to fix, and why a person has to."""
    table = (NEEDS_A_READER_TEST if path.name.startswith("test_")
             else NEEDS_A_READER_MODULE)
    out = []
    for prefix, why in table.items():
        for line in findings(path, select=(prefix,)):
            out.append({"finding": line.strip(), "why": why})
    return out


def workspace_pairs(cfg=None) -> List[Tuple[Path, List[Path], List[Path]]]:
    """Every accepted module in the crew workspace, with its hidden tests and
    the modules it depends on."""
    cfg = cfg or load_config()
    work = Path(cfg.state_home) / "outbox" / "workspace"
    hidden_dir = REPO_ROOT / "crew" / "hidden_tests"
    from .runners.check_accepted import hidden_for
    pairs = []
    modules = [p for p in sorted(work.glob("*.py")) if p.name != "__init__.py"]
    for module in modules:
        hidden = hidden_for(module.name, hidden_dir)
        tests = [hidden] if hidden else []
        deps = [m for m in modules if m != module and f"import {m.stem}" in
                module.read_text(encoding="utf-8")]
        pairs.append((module, deps, tests))
    # The crew's own test files are crew output too, and they held 40 of the
    # first campaign's 64 findings. A test file is verified against the module it
    # tests, plus whatever that module imports.
    for test_file in sorted((work / "tests").glob("test_*.py")):
        under_test = work / test_file.name[len("test_"):]
        if not under_test.is_file():
            continue
        deps = [under_test] + [m for m in modules if m != under_test and
                               f"import {m.stem}" in
                               under_test.read_text(encoding="utf-8")]
        pairs.append((test_file, deps, []))
    return pairs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m crew unify")
    ap.add_argument("files", nargs="*", help="module files to clean")
    ap.add_argument("--test", action="append", default=[],
                    help="test file that must still pass after each stage")
    ap.add_argument("--dep", action="append", default=[],
                    help="module this file imports")
    ap.add_argument("--workspace", action="store_true",
                    help="every accepted module in the crew workspace, paired "
                         "with its hidden tests")
    ap.add_argument("--check", action="store_true",
                    help="report what would change; write nothing")
    args = ap.parse_args(argv)

    jobs: List[Tuple[Path, List[Path], List[Path]]] = []
    if args.workspace:
        jobs = workspace_pairs()
    for f in args.files:
        jobs.append((Path(f).resolve(),
                     [Path(d).resolve() for d in args.dep],
                     [Path(t).resolve() for t in args.test]))
    if not jobs:
        ap.error("give files, or --workspace")

    reports = []
    for module, deps, tests in jobs:
        # A test file is verified by running it against the module it tests, so
        # it is never "unverified" just because the tests list is empty.
        if module.name.startswith("test_"):
            against = ", ".join(d.name for d in deps) or "nothing"
            label = f"  (verified against {against})"
        elif tests:
            label = f"  (tests: {', '.join(t.name for t in tests)})"
        else:
            label = "  (NO TESTS - nothing can be verified)"
        print(f"\n=== {module.name}{label}", flush=True)
        r = unify_file(module, tests, deps, check_only=args.check)
        reports.append(r)
        if r.get("refused"):
            print(f"  refused: {r['refused']}")
            continue
        if args.check:
            print(f"  {r['findings_before']} mechanical finding(s) a tool can fix:")
            for line in r["would_fix"][:12]:
                print("    " + line.strip())
        else:
            for stage in r["stages"]:
                extra = ""
                if stage["result"] == "kept":
                    extra = f" ({stage['lines_before']} -> {stage['lines_after']} lines)"
                elif stage["result"] == "REVERTED":
                    extra = f" - {stage['why'][:120]}"
                print(f"  {stage['stage']:24s} {stage['result']}{extra}")
            print(f"  mechanical findings: {r['findings_before']} -> "
                  f"{r['findings_after']}")
        if r["needs_a_reader"]:
            print(f"  {len(r['needs_a_reader'])} finding(s) a TOOL MUST NOT FIX:")
            for item in r["needs_a_reader"][:8]:
                print(f"    {item['finding'].strip()}")
                print(f"      why a person: {item['why']}")
    print("\n" + json.dumps({"files": len(reports),
                             "cleaned": sum(1 for r in reports if r.get("kept_any")),
                             "left_for_a_reader": sum(len(r.get("needs_a_reader", []))
                                                      for r in reports)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
