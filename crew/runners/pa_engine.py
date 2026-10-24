"""The Crew's chat engine: every approved OpenCode PA in one `opencode serve`.

Kris, 2026-10-24: "The most important feature is to get a chat history and instance system
so I can use that tool to assign crew jobs separately than asking Claude to use the Crew ...
The Goal is to allow the Crew to run as its own version of Claude Desktop or Antigravity."

The Crew window starts this (inside a job object, so it ends with the window) and is the
chat: it lists sessions, sends prompts to the PA Kris picks, follows the event stream, and
answers permission requests. OpenCode keeps the history. Each approved PA whose runtime is
opencode (Kimi, Qwen, Gordon) is a primary agent named after itself, with its own model and
its brief (crew/pa_brief.py) as the prompt; all of them share the crew MCP (worker off),
LSP and skills - exactly what pa_session.py gives one PA in a terminal. Claude is not here:
it runs through the Claude Code CLI.

The Synthetic key goes only into the server's environment; it is never printed or written.
The server listens on 127.0.0.1 only.

    python crew/runners/pa_engine.py --port 4199 [--project DIR] [--dry-run]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pa_session  # noqa: E402

REPO = pa_session.REPO


def engine_pas(staff: dict) -> list:
    """The approved PAs that run in OpenCode, in the approved order."""
    cfg = staff.get("pa") or {}
    scopes = cfg.get("scopes") or {}
    return [pa for pa in cfg.get("approved") or []
            if (scopes.get(pa) or {}).get("runtime") == "opencode"]


MODES = ("plan", "assign")


def agent_name(pa: str, mode: str) -> str:
    """`Gordon-plan`, `Gordon-assign`: one chat, two agents; the window picks by its toggle."""
    return f"{pa}-{mode}"


def engine_config(staff: dict, briefs: dict, chats: Path = None, worker: bool = False) -> dict:
    """One config for all of them: one Synthetic provider, and per PA a plan agent and an
    assign agent. `chats` is where each chat keeps its artifacts (runs/crew/pa/chats/<id>/)."""
    scopes = (staff.get("pa") or {}).get("scopes") or {}
    models, agents = {}, {}
    for pa, brief in briefs.items():
        model, entry = pa_session.provider_model(pa, scopes[pa], staff)
        models.setdefault(model, entry)
        for mode in MODES:
            agents[agent_name(pa, mode)] = pa_session.pa_agent(pa, scopes[pa], brief, chats, mode)
    return pa_session.base_config(models, agents, agent_name(next(iter(briefs)), "plan"),
                                  "TheCrew-chat", worker)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--project", default=str(REPO), help="the folder the PAs work in")
    ap.add_argument("--dry-run", action="store_true", help="write the config, do not start")
    args = ap.parse_args(argv)

    from crew import pa_brief, personnel
    from crew.config import load_config
    staff = personnel.load()
    pas = engine_pas(staff)
    if not pas:
        raise SystemExit("no approved PA runs in OpenCode (personnel.json, pa.scopes.*.runtime)")
    state = Path(load_config().state_home) / "pa"
    briefs = {}
    for pa in pas:
        home = state / pa
        home.mkdir(parents=True, exist_ok=True)
        brief = home / "brief.md"
        brief.write_text(pa_brief.render(pa, "", staff), encoding="utf-8")   # once per start
        briefs[pa] = brief
    config = state / "engine" / "opencode.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    chats = state / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(engine_config(staff, briefs, chats), indent=2), encoding="utf-8")
    print(f"PAs: {', '.join(pas)}; config: {config}", flush=True)

    from opencode_trial import _opencode_exe
    exe = _opencode_exe()
    argv_serve = [exe, "serve", "--hostname", "127.0.0.1", "--port", str(args.port)]
    if args.dry_run:
        print(f"would run: {' '.join(argv_serve)} in {args.project}")
        return 0
    print(pa_session.link_crush_skills(), flush=True)
    scopes = (staff.get("pa") or {}).get("scopes") or {}
    env = pa_session.with_real_python(dict(os.environ))
    env["OPENCODE_CONFIG"] = str(config)
    env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(max(
        int((scopes.get(pa) or {}).get("reply_tokens") or 32768) for pa in pas))
    key = pa_session.synthetic_key()
    if key:
        env["SYNTHETIC_API_KEY"] = key
    return subprocess.call(argv_serve, cwd=args.project, env=env)


if __name__ == "__main__":
    sys.exit(main())
