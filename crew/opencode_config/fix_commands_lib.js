// The refused-command plugin's logic. Deliberately NOT in `plugins/`.
//
// OpenCode loads EVERY export of every file in `plugins/` as a plugin function and calls it at
// start-up. Measured 2026-10-29 (Claude Code's proof run): a plugin file that also exported an
// array crashed the engine before its first tool call - "fn3 is not a function. (In 'fn3(input)',
// 'fn3' is an instance of Array)" - and that took down every PA build, because pa_build points
// OPENCODE_CONFIG_DIR at this directory. So `plugins/fix_commands.js` exports ONE function and
// nothing else, and every helper lives here, where nothing is auto-loaded.
//
// tests/test_fix_commands.py holds both lines: the pure rewrite is judged here, and the plugin
// file is imported the way the engine imports it, with every export required to be a function.

import fs from "node:fs";
import path from "node:path";

// One rewrite per catalogue entry name. A name with no strategy here is a gap the gate catches.
export const STRATEGY = {
  drop_stderr_redirect: (command) => command.replace(/\s+2>(&1|nul|\$null)\s*$/i, ""),
  display_pipe: (command) =>
    command.replace(/\|\s*(Select-Object|Format-Table|Format-List)\b[^|]*$/i, "").trimEnd(),
};

// Used when the catalogue cannot be read: the two active `plugin` entries it holds today.
export const FALLBACK_ENTRIES = [
  { name: "drop_stderr_redirect", pattern: "\\s+2>(&1|nul|\\$null)\\s*$" },
  { name: "display_pipe", pattern: "\\|\\s*(Select-Object|Format-Table|Format-List)\\b[^|]*$" },
];

// The pure rewrite: no I/O, so a test can judge it on its own. Only ever DROPS a tail; an
// unmatched command comes back byte for byte, with `entry` null.
export function rewriteCommand(command, entries) {
  if (typeof command !== "string" || !command) return { command, entry: null };
  let out = command;
  let applied = null;
  for (const entry of entries || []) {
    const fix = entry && STRATEGY[entry.name];
    if (!fix) continue;
    let matches;
    try {
      matches = new RegExp(entry.pattern, "i").test(out);
    } catch {
      continue;
    }
    if (!matches) continue;
    const next = fix(out);
    if (next !== out && next.trim()) {
      out = next;
      applied = entry.name;
    }
  }
  return { command: out, entry: applied };
}

// The catalogue's active `plugin` entries, from the project the engine is running in. Falls back
// to FALLBACK_ENTRIES on anything at all - the plugin must never be the reason a build stops.
export function readEntries(ctx) {
  try {
    const file = path.join(ctx && ctx.directory ? ctx.directory : ".", "crew", "fixes.json");
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    const entries = (data.entries || []).filter(
      (e) => e && e.kind === "plugin" && e.status === "active");
    return entries.length ? entries : FALLBACK_ENTRIES;
  } catch {
    return FALLBACK_ENTRIES;
  }
}

// BEST EFFORT ONLY. One JSON line per rewrite, for the miner: `command` is what ran, `was` is
// what the model wrote. Measured 2026-10-29 over four engine runs with identical inputs and a
// fresh log path each time: the rewrite happened in every run, but the line was written in only
// two of them. The cause is on the engine's side (not the path, which was set and readable), and
// this plugin cannot fix it. So treat the file as a PARTIAL sample, never a complete count - if
// the miner needs exact numbers, compare the model's own tool-call arguments with what ran.
export function log(row) {
  try {
    const target = process.env.CREW_FIX_LOG;
    if (!target) return;
    fs.appendFileSync(target, JSON.stringify(row) + "\n");
  } catch {
    // fail open: a log line is not worth a broken call
  }
}
