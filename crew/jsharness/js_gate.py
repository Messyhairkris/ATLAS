from collections.abc import Callable

from js_api import missing_api, stub_functions
from js_imports import check_imports, forbidden_uses
from node_tap import parse_tap

VERDICTS = ("accepted", "unsafe", "missing_api", "stubs", "tests_failed")


def _build_result(verdict: str, problems: list[str], counts: dict | None) -> dict:
    """Build the result dictionary for the judge function."""
    return {"verdict": verdict, "problems": problems, "counts": counts}


def judge(
    source: str,
    api: list[str],
    allowed_imports: set[str],
    run_tests: Callable[[str], str],
) -> dict:
    """Determine the verdict for a JavaScript module source."""
    # Rule 1: unsafe
    forbidden = forbidden_uses(source)
    import_problems = check_imports(source, allowed_imports)
    unsafe_problems = [f"forbidden global: {name}" for name in forbidden] + [
        f"import not allowed: {spec}" for spec in import_problems
    ]
    if unsafe_problems:
        return _build_result("unsafe", unsafe_problems, None)

    # Rule 2: missing_api
    missing = missing_api(source, api)
    if missing:
        problems = [f"not exported: {name}" for name in missing]
        return _build_result("missing_api", problems, None)

    # Rule 3: stubs
    stubs = stub_functions(source)
    if stubs:
        problems = [f"stub: {name}" for name in stubs]
        return _build_result("stubs", problems, None)

    # Rule 4: run tests (only if passed static checks)
    tap_text = run_tests(source)
    parsed = parse_tap(tap_text)
    counts = parsed["counts"]
    failed = counts.get("fail", 0) + counts.get("cancelled", 0)
    if failed > 0:
        return _build_result("tests_failed", [f"{failed} failed"], counts)
    if counts.get("pass", 0) == 0:
        return _build_result("tests_failed", ["no test passed"], counts)
    return _build_result("accepted", [], counts)
