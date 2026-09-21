"""Do these tests actually test anything? Seed defects and count the survivors.

A passing test suite proves nothing on its own: a suite that asserts
`result != the_input` passes forever while catching nothing. So the grade for a
test file is not "does it pass" but **how many deliberate defects it catches**.

This applies one small, mechanical change at a time to a module - flip a
comparison, swap a boolean, nudge a number, drop a `not` - and runs the tests
against it. A defect that makes the tests fail was *killed*. One that leaves them
green *survived*, and each survivor is a hole in the suite with a line number.

Nothing here involves a model, which is the point: it is the same measurement
every time, for free, and it can be run on any module the crew has had accepted.

    python crew/runners/mutants.py --module profiles.py \\
        --tests tests/test_profiles.py            # the crew's own tests
    python crew/runners/mutants.py --module profiles.py --hidden  # ours
    python crew/runners/mutants.py --all --hidden  # every accepted module

Survivors are printed with the exact line, so a weak test is a specific thing to
fix rather than a vague complaint.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew import codetask                                    # noqa: E402
from crew.config import load_config                          # noqa: E402
from crew.runners.check_accepted import hidden_for           # noqa: E402

# One defect each, all mechanical, all plausible as a real mistake. Each pattern is
# matched on a single line and applied once, so every seeded module differs from
# the original in exactly one place.
OPERATORS = [
    ("comparison >= to >", r"(?<![<>=!])>=(?!=)", ">"),
    ("comparison <= to <", r"(?<![<>=!])<=(?!=)", "<"),
    ("comparison > to >=", r"(?<![<>=!])>(?![>=])", ">="),
    ("comparison < to <=", r"(?<![<>=!])<(?![<=])", "<="),
    ("equality to inequality", r"(?<![<>=!])==(?!=)", "!="),
    ("inequality to equality", r"!=", "=="),
    ("True to False", r"\bTrue\b", "False"),
    ("False to True", r"\bFalse\b", "True"),
    ("and to or", r"\band\b", "or"),
    ("or to and", r"\bor\b", "and"),
    ("drop a not", r"\bnot\b ", ""),
    ("zero to one", r"(?<![\w.])0(?![\w.])", "1"),
    ("one to zero", r"(?<![\w.])1(?![\w.])", "0"),
    ("empty string to a space", r'""(?!")', '" "'),
    ("reverse a sort", r"\bsorted\(", "reversed_sorted("),
]

SKIP_LINE = re.compile(r'^\s*(#|"""|\'\'\')')


def prose_lines(source: str) -> set:
    """Every line inside a docstring.

    Changing a word in prose is not a defect, and counting it as one makes a test
    suite look worse than it is: the first measurement of profiles.py reported two
    survivors that were "and" becoming "or" in the module's own docstring.
    """
    out: set = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def candidates(source: str) -> list:
    """Every (line number, label, mutated source) this module admits.

    A mutation that does not parse is dropped: a syntax error tests nothing. So is
    a mutation inside a docstring, which changes no behaviour at all.
    """
    lines = source.splitlines(keepends=True)
    prose = prose_lines(source)
    out = []
    for number, line in enumerate(lines, 1):
        if number in prose or SKIP_LINE.match(line) or not line.strip():
            continue
        for label, pattern, replacement in OPERATORS:
            if not re.search(pattern, line):
                continue
            mutated_line = re.sub(pattern, replacement, line, count=1)
            if mutated_line == line:
                continue
            mutated = lines[:number - 1] + [mutated_line] + lines[number:]
            text = "".join(mutated)
            try:
                ast.parse(text)
            except SyntaxError:
                continue
            out.append({"line": number, "label": label, "source": text,
                        "before": line.strip(), "after": mutated_line.strip()})
    return out


def run(module: Path, tests: list, deps: list, timeout_s: int = 120,
        limit: int = 0, verbose: bool = False) -> dict:
    """Seed each defect in turn and report which the tests caught."""
    source = module.read_text(encoding="utf-8")
    test_src = {t.name: t.read_text(encoding="utf-8") for t in tests}
    dep_src = {d.name: d.read_text(encoding="utf-8") for d in deps}
    extra = tuple({d.stem for d in deps} | {"pytest"})

    baseline_ok, baseline_out, _ = codetask.run_tests(
        {module.name: source, **dep_src}, test_src, timeout_s=timeout_s,
        extra_imports=extra)
    if not baseline_ok:
        return {"module": module.name, "error": "the tests do not pass before any "
                "defect is seeded, so nothing can be measured",
                "detail": codetask.summarize(baseline_out)}

    seeded = candidates(source)
    if limit:
        step = max(1, len(seeded) // limit)
        seeded = seeded[::step][:limit]
    killed, survived = 0, []
    for index, defect in enumerate(seeded, 1):
        ok, _out, _detail = codetask.run_tests(
            {module.name: defect["source"], **dep_src}, test_src,
            timeout_s=timeout_s, extra_imports=extra)
        if ok:
            survived.append(defect)
        else:
            killed += 1
        if verbose:
            mark = "SURVIVED" if ok else "killed  "
            print(f"  [{index}/{len(seeded)}] {mark} line {defect['line']}: "
                  f"{defect['label']}", flush=True)
    total = len(seeded)
    return {"module": module.name,
            "tests": sorted(test_src),
            "seeded": total,
            "killed": killed,
            "survived": len(survived),
            "score": round(killed / total, 3) if total else None,
            "survivors": [{"line": d["line"], "what": d["label"],
                           "was": d["before"], "became": d["after"]}
                          for d in survived]}


def _pairs(workspace: Path, hidden_dir: Path, module_name: str = "",
           test_paths=()) -> list:
    modules = [p for p in sorted(workspace.glob("*.py")) if p.name != "__init__.py"]
    chosen = [p for p in modules if not module_name or p.name == module_name]
    out = []
    for module in chosen:
        source = module.read_text(encoding="utf-8")
        deps = [m for m in modules if m is not module
                and re.search(r"^[ \t]*(?:import|from)[ \t]+" + m.stem + r"\b",
                              source, re.MULTILINE)]
        if test_paths:
            tests = [Path(t) for t in test_paths]
        else:
            hidden = hidden_for(module.name, hidden_dir)
            tests = [hidden] if hidden else []
        out.append((module, tests, deps))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="")
    ap.add_argument("--hidden-dir", default=str(REPO_ROOT / "crew" / "hidden_tests"))
    ap.add_argument("--module", default="", help="one module, e.g. profiles.py")
    ap.add_argument("--tests", action="append", default=[],
                    help="test file to judge (repeatable); relative to the workspace")
    ap.add_argument("--hidden", action="store_true",
                    help="judge the hidden tests instead of the crew's own")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0,
                    help="sample this many defects instead of every one")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    workspace = Path(args.workspace or
                     Path(load_config().state_home) / "outbox" / "workspace")
    if not args.module and not args.all:
        print("name a --module, or pass --all", file=sys.stderr)
        return 2
    tests = [workspace / t if not Path(t).is_absolute() else Path(t)
             for t in args.tests]
    if not tests and not args.hidden and args.module:
        guess = workspace / "tests" / f"test_{Path(args.module).stem}.py"
        if guess.is_file():
            tests = [guess]
    t0 = time.time()
    failures = 0
    for module, test_files, deps in _pairs(workspace, Path(args.hidden_dir),
                                           args.module, tests):
        print(f"$ mutants {module.name} judged by "
              f"{', '.join(t.name for t in test_files) or '(nothing)'}", flush=True)
        if not test_files:
            print("  no tests to judge it with\n")
            failures += 1
            continue
        result = run(module, test_files, deps, timeout_s=args.timeout,
                     limit=args.limit, verbose=args.verbose)
        if result.get("error"):
            print(f"  REFUSED: {result['error']}\n  {result.get('detail', '')}\n")
            failures += 1
            continue
        print(f"  {result['killed']}/{result['seeded']} defects caught "
              f"({result['score']:.0%})")
        for survivor in result["survivors"]:
            print(f"  SURVIVED line {survivor['line']}: {survivor['what']}")
            print(f"      was: {survivor['was']}")
            print(f"    became: {survivor['became']}")
        print()
    print(f"{failures} failed, done in {time.time() - t0:.1f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
