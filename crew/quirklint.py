"""Run the crew-built quirk linter (crew/quirks/) on every code submission.

Zero-token checks for mistakes a model is known to make. Two kinds of action:

  * repair: text a contract gives verbatim, re-indented by the member (Nemotron: 29
    lines in one real packer attempt), is put back to the contract's indentation
    before the gates run. Meaning-preserving and recorded, like autofix.
  * report: a forced failure (`assert False`, `assert.fail(`) inside a try block in a
    test file becomes a failing gate step naming the lines, because such a test can
    pass when nothing is raised. Reported, never rewritten - the fix is the member's.

The modules themselves were written by Gordon and Barry in the quirk-linter campaign
(2026-09-21) and judged by hidden tests; this file is only the wiring.
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

QUIRKS = Path(__file__).resolve().parent / "quirks"
if str(QUIRKS) not in sys.path:
    sys.path.insert(0, str(QUIRKS))

import quirk_indent  # noqa: E402  (crew-built, lives in crew/quirks)
import quirk_tests  # noqa: E402

CODE_TYPES = ("code_task", "js_code_task")
TEST_TYPES = ("code_tests", "js_code_tests")
LANGUAGE = {".py": "python", ".js": "javascript", ".mjs": "javascript"}


def _contract(spec: dict) -> str:
    try:
        return Path(spec["contract"]).read_text(encoding="utf-8")
    except (KeyError, OSError):
        return ""


def repair(files: Dict[str, str], spec: dict, task_type: str) -> Tuple[Dict[str, str], List[str]]:
    """Re-indent drifted verbatim text in code submissions. Returns (files, notes)."""
    if task_type not in CODE_TYPES:
        return files, []
    lines = quirk_indent.verbatim_lines(_contract(spec))
    if not lines:
        return files, []
    out, notes = {}, []
    for name, text in files.items():
        if Path(name).suffix not in LANGUAGE:
            out[name] = text
            continue
        fixed, count = quirk_indent.fix_indent_drift(text, lines)
        if count:
            notes.append(f"{name}: restored the contract's indentation on {count} "
                         f"verbatim line(s) (quirk linter)")
        out[name] = fixed
    return out, notes


def gate_steps(files: Dict[str, str], task_type: str) -> List[dict]:
    """Failing steps for test files that hide a forced failure inside try."""
    if task_type not in TEST_TYPES:
        return []
    steps = []
    for name, text in files.items():
        language = LANGUAGE.get(Path(name).suffix)
        if not language:
            continue
        hits = quirk_tests.fail_in_try(text, language)
        if hits:
            how = ("pytest.raises(...)" if language == "python"
                   else "assert.throws(() => ..., /message/)")
            steps.append({"rung": "quirks", "file": name, "ok": False,
                          "detail": f"a forced failure sits inside a try block on line(s) "
                                    f"{', '.join(map(str, hits))}; a broad except/catch can "
                                    f"swallow it, so the test can pass when nothing is "
                                    f"raised. Use {how} instead."})
    return steps
