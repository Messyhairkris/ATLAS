// OpenCode plugin: rewrite a bash command that would be refused, BEFORE it runs.
//
// The refusal is usually mechanical: a trailing ` 2>&1` or ` 2>nul` (the crew's own `*>*` deny
// rule) or a display pipe (`| Select-Object ...`). Dropping that tail cannot change what the
// command does - OpenCode captures stdout and stderr already - so the command runs instead of
// being refused, and the round is not wasted.
//
// Loaded ONLY for PA builds: `pa_build` sets `OPENCODE_CONFIG_DIR` to `crew/opencode_config`, and
// OpenCode searches that directory for plugins exactly like a project's `.opencode`. The PM's own
// sessions and the build worktree itself never load it.
//
// The rules that make it safe to run unattended (Kris, 2026-10-29):
//   * it only ever DROPS a tail - it never adds a redirect, a flag or a write;
//   * an unmatched command is returned untouched, byte for byte;
//   * it fails open: any exception means the call goes through exactly as the model wrote it;
//   * every rewrite is appended to `CREW_FIX_LOG` (the build's `fixes.jsonl`) for the miner.
//
// `rewriteCommand` is pure (no I/O) so `tests/test_fix_commands.py` can judge it under node.
//
// The catalogue (`crew/fixes.json`) is the source of the patterns: only entries with
// `kind: "plugin"` and `status: "active"` are applied, each through its `STRATEGY`.

import fs from "node:fs";
import path from "node:path";

// One rewrite per catalogue entry name. A name with no strategy here is a gap the gate catches.
export const STRATEGY = {
  drop_stderr_redirect: (command) => command.replace(/\s+2>(&1|nul|\$null)\s*$/i, ""),
  display_pipe: (command) =>
    command.replace(/\|\s*(Select-Object|Format-Table|Format-List)\b[^|]*$/i, "").trimEnd(),
};

export const FALLBACK_ENTRIES = [
  { name: "drop_stderr_redirect", pattern: "\\s+2>(&1|nul|\\$null)\\s*$" },
  { name: "display_pipe", pattern: "\\|\\s*(Select-Object|Format-Table|Format-List)\\b[^|]*$" },
];

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

export const FixCommands = async (ctx) => {
  const entries = readEntries(ctx);
  const applied = new Map();
  return {
    "tool.execute.before": async (input, output) => {
      try {
        if (!input || input.tool !== "bash") return;
        const args = output && output.args;
        if (!args || typeof args.command !== "string") return;
        const result = rewriteCommand(args.command, entries);
        if (!result.entry || result.command === args.command) return;
        const from = args.command;
        args.command = result.command;
        if (input.callID) applied.set(input.callID, result);
        log(ctx, { entry: result.entry, from, to: result.command });
      } catch {
        // fail open: a rewrite is an optimisation, never a blocker
      }
    },
    "tool.execute.after": async (input, output) => {
      try {
        const result = input && input.callID ? applied.get(input.callID) : null;
        if (!result) return;
        applied.delete(input.callID);
        if (output && typeof output.output === "string") {
          output.output = `[ran as: ${result.command} - ${result.entry}]\n` + output.output;
        }
      } catch {
        // fail open
      }
    },
  };
};

function readEntries(ctx) {
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

function log(ctx, row) {
  try {
    const target = process.env.CREW_FIX_LOG;
    if (!target) return;
    fs.appendFileSync(target, JSON.stringify(row) + "\n");
  } catch {
    // fail open
  }
}
