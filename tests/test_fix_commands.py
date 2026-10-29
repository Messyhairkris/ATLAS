"""The refused-command plugin, and the file OpenCode actually loads (build C gate).

Two separate things are checked here, because getting one right without the other broke every PA
build on 2026-10-29:

1. the pure rewrite (`rewriteCommand`), judged by node through `crew/jsrun` - a throwaway
   directory, a `package.json` with `"type": "module"`, node's permission model on. It lives in
   `crew/opencode_config/fix_commands_lib.js`;
2. the plugin file itself, imported the way OpenCode imports it. **OpenCode calls EVERY export of
   a file in `plugins/` as a plugin function at start-up.** A second export - even a plain array -
   crashed the engine before its first tool call ("fn3 is not a function ... 'fn3' is an instance
   of Array") and took down every build, because `pa_build` points `OPENCODE_CONFIG_DIR` at this
   directory. So every export of every file under `plugins/` must be a function.

THIS FILE IS THE GATE. Changing it to make an implementation pass is the one thing a build may not
do.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import jsrun  # noqa: E402

CONFIG_DIR = REPO / "crew" / "opencode_config"
LIB = CONFIG_DIR / "fix_commands_lib.js"
PLUGINS = CONFIG_DIR / "plugins"
PLUGIN = PLUGINS / "fix_commands.js"


def _active_plugin_entries() -> list:
    data = json.loads((REPO / "crew" / "fixes.json").read_text(encoding="utf-8"))
    return [e for e in data["entries"]
            if e.get("kind") == "plugin" and e.get("status") == "active"]


def _run_lib(js_test: str):
    """Run one node test file against the library's pure rewrite, on its own."""
    if not LIB.is_file():
        pytest.fail(f"the rewrite library is missing: {LIB}")
    if not shutil.which("node"):
        pytest.skip("node is not on PATH; this is JavaScript and cannot be judged without it")
    passed, tap, _ = jsrun.run_node_tests({"fix_commands_lib.js": LIB.read_text(encoding="utf-8")},
                                          {"lib.test.js": js_test})
    return passed, tap


# ---- 1. the pure rewrite ----------------------------------------------------------------------

def test_a_refused_shape_is_rewritten_and_an_allowed_one_is_untouched():
    entries = json.dumps([{"name": e["name"], "pattern": e["pattern"]}
                          for e in _active_plugin_entries()])
    js = """
import test from "node:test";
import assert from "node:assert/strict";
import { rewriteCommand } from "./fix_commands_lib.js";

const ENTRIES = %s;

// [input, the command that must run, the entry that must be credited]
const REWRITTEN = [
  ["python crew/runners/status_overlay.py 2>&1",
   "python crew/runners/status_overlay.py", "drop_stderr_redirect"],
  ["Get-ChildItem -Recurse 2>$null", "Get-ChildItem -Recurse", "drop_stderr_redirect"],
  ["git status 2>NUL", "git status", "drop_stderr_redirect"],
  ["git status --short | Select-Object -First 20", "git status --short", "display_pipe"],
  ["Get-ChildItem | Format-Table Name", "Get-ChildItem", "display_pipe"],
];

test("a refused shape is rewritten, and credited to the right entry", () => {
  for (const [input, expected, entry] of REWRITTEN) {
    const r = rewriteCommand(input, ENTRIES);
    assert.equal(r.command, expected, "the command for: " + input);
    assert.equal(r.entry, entry, "the entry for: " + input);
  }
});

test("a command that is already allowed is left completely alone", () => {
  for (const input of ["python -m pytest -q tests/test_guard.py",
                       "python -m pytest tests/test_fixers.py -q",
                       "git log --oneline -3", "git status --short",
                       "Get-ChildItem & echo done"]) {
    const r = rewriteCommand(input, ENTRIES);
    assert.equal(r.command, input, "must not change: " + input);
    assert.equal(r.entry, null, "must not claim an entry for: " + input);
  }
});

test("a rewrite never adds a redirect - it only ever drops", () => {
  const r = rewriteCommand("python crew/runners/status_overlay.py 2>&1", ENTRIES);
  assert.ok(!r.command.includes(">"), "no '>' may survive or be added: " + r.command);
});
""" % entries
    passed, tap = _run_lib(js)
    assert passed, f"node said:\n{tap}"


def test_every_active_plugin_entry_has_a_rewrite():
    names = [e["name"] for e in _active_plugin_entries()]
    assert names, "the catalogue has no active 'plugin' entry to cover"
    js = """
import test from "node:test";
import assert from "node:assert/strict";
import { STRATEGY } from "./fix_commands_lib.js";

const NAMES = %s;

test("STRATEGY covers every active plugin entry in the catalogue", () => {
  for (const name of NAMES) {
    assert.ok(STRATEGY && typeof STRATEGY[name] === "function",
              "no rewrite registered for the catalogue entry: " + name);
  }
});
""" % json.dumps(names)
    passed, tap = _run_lib(js)
    assert passed, f"node said:\n{tap}"


# ---- 2. the file OpenCode loads ---------------------------------------------------------------

def test_every_export_of_a_plugin_file_is_declared_as_the_single_plugin_function():
    # A cheap static guard for the same rule, so it fails even where node is absent.
    assert PLUGIN.is_file(), PLUGIN
    for path in sorted(PLUGINS.glob("*.js")):
        src = path.read_text(encoding="utf-8")
        named = re.findall(
            r"^export\s+(?:async\s+function|function|const|let|var|class)\s+([A-Za-z_$][\w$]*)",
            src, re.M)
        assert "export {" not in src, f"{path.name} uses an export list; the engine would call it"
        assert named == ["FixCommands"], (
            f"{path.name} exports {named}; every export of a plugin file is called as a plugin, "
            f"so the only one allowed is FixCommands")


def test_the_plugin_loads_the_way_the_engine_loads_it_and_every_export_is_a_function():
    """The real check: import `plugins/fix_commands.js` from a copy laid out as the engine sees
    it, and require every export to be a function. This is what crashed pa_build (2026-10-29)."""
    if not shutil.which("node"):
        pytest.skip("node is not on PATH; this is JavaScript and cannot be judged without it")
    with tempfile.TemporaryDirectory(prefix="fixcmd-load-") as tmp:
        root = Path(tmp)
        (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
        (root / "plugins").mkdir()
        shutil.copyfile(LIB, root / "fix_commands_lib.js")
        shutil.copyfile(PLUGIN, root / "plugins" / "fix_commands.js")
        check = root / "load.mjs"
        check.write_text(
            'import * as mod from "./plugins/fix_commands.js";\n'
            'const bad = Object.entries(mod).filter(([, v]) => typeof v !== "function");\n'
            'if (bad.length) {\n'
            '  console.error("not a function: " + bad.map(([k]) => k).join(","));\n'
            '  process.exit(1);\n'
            '}\n'
            'console.log("exports: " + Object.keys(mod).join(","));\n', encoding="utf-8")
        proc = subprocess.run(
            [shutil.which("node"), "--permission", f"--allow-fs-read={root}", str(check)],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        assert proc.returncode == 0, (
            "importing the plugin failed (the engine calls every export):\n"
            + (proc.stdout or "") + (proc.stderr or ""))
        assert "FixCommands" in (proc.stdout or ""), proc.stdout
