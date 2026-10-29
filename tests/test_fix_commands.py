"""The plugin that rewrites a refused bash command, before it runs (build C gate).

The rewrite itself is JavaScript, so it is judged by node through `crew/jsrun` - a throwaway
directory, a `package.json` with `"type": "module"`, node's permission model on. OpenCode loads
the plugin from the directory `pa_build` points `OPENCODE_CONFIG_DIR` at, so nothing here starts
the engine.

THIS FILE IS THE GATE. The plugin must export exactly the names below and behave exactly as these
cases say. Changing this file to make an implementation pass is the one thing a build may not do.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import jsrun  # noqa: E402

PLUGIN = REPO / "crew" / "opencode_config" / "plugins" / "fix_commands.js"


def _active_plugin_entries() -> list:
    data = json.loads((REPO / "crew" / "fixes.json").read_text(encoding="utf-8"))
    return [e for e in data["entries"]
            if e.get("kind") == "plugin" and e.get("status") == "active"]


def _run(js_test: str):
    """Run one node test file against the plugin, on its own, and return (passed, tap)."""
    if not PLUGIN.is_file():
        pytest.fail(f"the plugin is missing: {PLUGIN}")
    if not shutil.which("node"):
        pytest.skip("node is not on PATH; the plugin is JavaScript and cannot be judged without it")
    source = {"fix_commands.js": PLUGIN.read_text(encoding="utf-8")}
    passed, tap, _ = jsrun.run_node_tests(source, {"fix_commands.test.js": js_test})
    return passed, tap


def test_a_refused_shape_is_rewritten_and_an_allowed_one_is_untouched():
    entries = json.dumps([{"name": e["name"], "pattern": e["pattern"]}
                          for e in _active_plugin_entries()])
    js = """
import test from "node:test";
import assert from "node:assert/strict";
import { rewriteCommand } from "./fix_commands.js";

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
    passed, tap = _run(js)
    assert passed, f"node said:\n{tap}"


def test_every_active_plugin_entry_has_a_rewrite():
    names = [e["name"] for e in _active_plugin_entries()]
    assert names, "the catalogue has no active 'plugin' entry to cover"
    js = """
import test from "node:test";
import assert from "node:assert/strict";
import { STRATEGY } from "./fix_commands.js";

const NAMES = %s;

test("STRATEGY covers every active plugin entry in the catalogue", () => {
  for (const name of NAMES) {
    assert.ok(STRATEGY && typeof STRATEGY[name] === "function",
              "no rewrite registered for the catalogue entry: " + name);
  }
});
""" % json.dumps(names)
    passed, tap = _run(js)
    assert passed, f"node said:\n{tap}"
