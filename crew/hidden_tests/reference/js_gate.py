"""Decide whether a crew-written JavaScript module is accepted."""

from collections.abc import Callable

from js_api import missing_api, stub_functions
from js_imports import check_imports, forbidden_uses
from node_tap import parse_tap

VERDICTS = ("accepted", "unsafe", "missing_api", "stubs", "tests_failed")


def _verdict(name: str, problems: list[str], counts: dict | None = None) -> dict:
    return {"verdict": name, "problems": problems, "counts": counts}


def judge(source: str, api: list[str], allowed_imports: set[str],
          run_tests: Callable[[str], str]) -> dict:
    """Rules in order; tests run only when every static check passed."""
    unsafe = ([f"forbidden global: {n}" for n in forbidden_uses(source)]
              + [f"import not allowed: {s}"
                 for s in check_imports(source, allowed_imports)])
    if unsafe:
        return _verdict("unsafe", unsafe)
    missing = missing_api(source, api)
    if missing:
        return _verdict("missing_api", [f"not exported: {n}" for n in missing])
    stubs = stub_functions(source)
    if stubs:
        return _verdict("stubs", [f"stub: {n}" for n in stubs])
    counts = parse_tap(run_tests(source))["counts"]
    failed = counts.get("fail", 0) + counts.get("cancelled", 0)
    if failed or not counts.get("pass", 0):
        problems = [f"{failed} failed"] if failed else ["no test passed"]
        return _verdict("tests_failed", problems, counts)
    return _verdict("accepted", [], counts)
