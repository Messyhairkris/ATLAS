"""End-to-end check of the quirk linter wiring through Crew.run_job, no model involved.

A fake chat returns (1) a correct single-file.js whose verbatim template lines were
re-indented the way Nemotron does it - the linter must repair them and the gates accept;
(2) a JS test file with assert.fail inside try - the quirks step must fail it.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from crew.core import Crew  # noqa: E402

REF = (ROOT / "crew/hidden_tests/reference/single-file.js").read_text(encoding="utf-8")
FENCE = "`" * 3


def drift(source: str) -> str:
    """Add two spaces inside every string literal that starts with '<' or two spaces."""
    def shift(m):
        rest = source[m.end():source.index(chr(10), m.end())]
        return m.group(0) if len(rest.strip(' ",;')) < 6 else m.group(1) + '"  ' + m.group(2)
    return re.sub(r'(?m)^(\s*)"(  |<)', shift, source)


def fake_chat_factory(reply_text):
    def factory(*_args, **_kwargs):
        def chat(messages, n):
            return {"content": reply_text, "raw": {"choices": [{"message": {}}], "usage": {}}}
        return chat
    return factory


def run(spec, reply):
    crew = Crew(chat_factory=fake_chat_factory(reply))
    brief = crew.submit(spec, submitted_by="quirklint-e2e", claim=True)
    try:
        return crew.run_job(brief["task_id"]), crew
    finally:
        crew.store.release(brief["task_id"])


drifted = drift(REF)
assert drifted != REF
module_spec = {
    "task_type": "js_code_task", "title": "quirklint e2e: drifted packer",
    "module": "single-file.js",
    "contract": str(ROOT / "crew/contracts/splat_single_file.md"),
    "hidden_tests": [str(ROOT / "crew/hidden_tests/single-file.test.mjs")],
    "api": ["PACKED_GLOBAL", "rewriteSpecifiers", "bytesToBase64", "scriptSafe", "packedPage"],
    "assigned_to": "Hoss",
    "output": {"root": str(ROOT / "runs/crew/outbox/quirklint-e2e")},
    "budget": {"max_requests": 2, "max_tokens": 50000},
}
brief, crew = run(module_spec, "SUBMIT\n" + FENCE + "single-file.js\n" + drifted + FENCE + "\n")
job = crew.store.load(brief["task_id"])
fixes = [e for e in (job.get("result") or {}).get("autofix", []) or []]
print("module: passed_gates =", brief["passed_gates"], "| failed =", brief["failed_gates"])
transcript = (crew.store.job_dir(brief["task_id"]) / "transcript.jsonl").read_text(encoding="utf-8")
print("  autofix note present:", "quirk linter" in transcript)

bad_tests = ('import test from "node:test";\nimport assert from "node:assert/strict";\n'
             'import * as m from "./single-file.js";\n'
             + "".join(f'test("t{i}", () => {{ assert.equal(m.PACKED_GLOBAL, "SPLAT_PACKED"); }});\n'
                       for i in range(6))
             + 'test("throws", () => {\n  try {\n    m.packedPage({ modules: {}, entry: "x" });\n'
               '    assert.fail("no throw");\n  } catch (e) {\n    assert.ok(e);\n  }\n});\n')
tests_spec = {
    "task_type": "js_code_tests", "title": "quirklint e2e: try/fail tests",
    "test_file": "single-file.test.mjs",
    "contract": str(ROOT / "crew/contracts/splat_single_file.md"),
    "depends_modules": [str(ROOT / "runs/crew/outbox/workspace/single-file.js")],
    "min_tests": 6, "assigned_to": "Hoss",
    "output": {"root": str(ROOT / "runs/crew/outbox/quirklint-e2e/tests")},
    "budget": {"max_requests": 2, "max_tokens": 50000},
}
brief2, _ = run(tests_spec, "SUBMIT\n" + FENCE + "single-file.test.mjs\n" + bad_tests + FENCE + "\n")
print("tests : passed_gates =", brief2["passed_gates"])
for g in brief2["failed_gates"]:
    print("  ", g[:220])
