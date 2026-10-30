// OpenCode plugin: rewrite a bash command that would be refused, BEFORE it runs.
//
// Loaded ONLY for PA builds: `pa_build` sets `OPENCODE_CONFIG_DIR` to `crew/opencode_config`, and
// OpenCode searches that directory for plugins exactly like a project's `.opencode`. The PM's own
// sessions and the build worktree itself never load it.
//
// This file exports ONE function and nothing else. OpenCode calls EVERY export of a file in
// `plugins/` as a plugin at start-up, so a second export - even a plain array - crashes the
// engine before its first tool call and takes down the whole build (measured 2026-10-29). All
// the logic is in `../fix_commands_lib.js`, which nothing auto-loads.
//
// What it does, and what keeps it safe to run unattended (Kris, 2026-10-29):
//   * it only ever DROPS a tail - a trailing ` 2>&1` / ` 2>nul` (the crew's own `*>*` deny rule)
//     or a display pipe (`| Select-Object ...`); it never adds a redirect, a flag or a write;
//   * an unmatched command is returned untouched, byte for byte;
//   * it fails open: any exception means the call goes through exactly as the model wrote it;
//   * every rewrite is appended to `CREW_FIX_LOG` (the build's `fixes.jsonl`) for the miner.
//
// Proven 2026-10-29 (OpenCode 1.2.6, with the real config dir): `tool.execute.before` runs BEFORE
// the bash permission check, so a refused `python -m pytest --version 2>&1` becomes
// `python -m pytest --version` and really runs ("pytest 9.1.0"), while the same command with the
// plugin off is refused.
//
// There is deliberately NO `tool.execute.after` hook. One was written to prepend a
// `[ran as: ...]` note to the tool result; measurement showed the hook does receive
// `output.output` ("pytest 9.1.0\r\n") but its mutation is NOT what gets stored - the model never
// sees it. Rather than keep code that only pretends to act, it is gone.

import { log, readEntries, rewriteCommand } from "../fix_commands_lib.js";

export const FixCommands = async (ctx) => {
  const entries = readEntries(ctx);
  return {
    "tool.execute.before": async (input, output) => {
      try {
        if (!input || input.tool !== "bash") return;
        const args = output && output.args;
        if (!args || typeof args.command !== "string") return;
        const result = rewriteCommand(args.command, entries);
        if (!result.entry || result.command === args.command) return;
        const was = args.command;
        args.command = result.command;
        log({ entry: result.entry, command: result.command, was });
      } catch {
        // fail open: a rewrite is an optimisation, never a blocker
      }
    },
  };
};
