"""Open a PA session with an approved crew member as the PA (the OpenCode runtime).

Kris, 2026-10-23: choose the PA from Claude, Kimi, Qwen and Gordon, and "deploy the crew
using approved agents" - with Crush's good parts (LSP, Skills) and without its bad one
(hooks that injected context on every reply). Claude runs in the Claude Code desktop app
and gets its brief from a SessionStart hook; every other approved PA runs here, in
OpenCode, which gives it native tool calling, LSP and skills:

- the brief (crew/pa_brief.py) is written to runs/crew/pa/<PA>/brief.md and becomes the
  PA agent's prompt: rendered once when the session opens, never per reply;
- the crew MCP server is attached, so this PA submits and reads crew work with the same
  tools Claude uses;
- LSP: Python with pylsp and AutoHotkey with Crush's ahk-lsp (Crush's servers), Rust
  with rust-analyzer, TypeScript built in;
- skills: OpenCode reads ~/.claude/skills; Crush's skills are linked into ~/.agents/skills
  (one directory junction, created the first time) so the PA can load any on demand;
- Synthetic is the provider; the key goes straight into OpenCode's environment, from the
  same place the crew's own calls get it, and is never printed or written.

  python crew/runners/pa_session.py --pa Gordon [--project DIR] [--task "..."] [--dry-run]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "v3-service"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PYTHON = sys.executable
HOME = Path.home()
CRUSH_SKILLS = HOME / ".crush" / "skills"
SHARED_SKILLS = HOME / ".agents" / "skills"
AHK_LSP = HOME / ".ahk-lsp" / "server.js"
PYLSP = Path(PYTHON).parent / "Scripts" / "pylsp.exe"


KEEPER = HOME / "TheCrew" / "bin" / "mcp-keeper.exe"
KEEPER_LOG = REPO / "runs" / "mcp-keeper" / "keeper.jsonl"


def _keeper(name: str) -> list:
    """Kris 2026-10-23: every MCP server starts behind mcp-keeper, which starts it again
    when the first (cold) start fails. Without the keeper built, the server runs bare."""
    if not KEEPER.is_file():
        return []
    return [str(KEEPER), "--name", name, "--first-wait", "40", "--total", "85",
            "--log", str(KEEPER_LOG), "--"]


def opencode_config(pa: str, scope: dict, staff: dict, brief: Path, worker: bool = False) -> dict:
    """The generated opencode.json: one provider, one primary agent, the crew MCP."""
    model = scope["model"]
    member = (staff.get("members") or {}).get(pa) or {}
    reply = int(scope.get("reply_tokens") or 32768)
    lsp = {"pyright": {"disabled": True}}             # not installed; pylsp instead
    if PYLSP.is_file():
        lsp["pylsp"] = {"command": [str(PYLSP)], "extensions": [".py", ".pyi"]}
    if AHK_LSP.is_file():
        lsp["autohotkey"] = {"command": ["node", str(AHK_LSP), "--stdio"],
                             "extensions": [".ahk"]}
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"synthetic": {
            "npm": "@ai-sdk/openai-compatible", "name": "Synthetic",
            "options": {"baseURL": "https://api.synthetic.new/v1",
                        "apiKey": "{env:SYNTHETIC_API_KEY}"},
            "models": {model: {"name": f"{pa} ({model})",
                               "limit": {"output": reply,
                                         "context": int(member.get("context_window")
                                                        or 200000)}}}}},
        "mcp": {"crew": {"type": "local", "command": _keeper("crew") + [PYTHON, str(REPO / "crew_server.py")],
                         # worker off by default: a worker would also run every stale READY job in
                         # the queue (14 on 2026-10-23); the PA runs work with campaigns
                         "environment": {"CREW_CLIENT": f"OpenCode-{pa}",
                                         "CREW_WORKER": "1" if worker else "0"},
                         "enabled": True, "timeout": 120000}},
        "lsp": lsp,
        "agent": {"pa": {
            "mode": "primary", "description": f"{pa} as the PA of The Crew",
            "model": f"synthetic/{model}", "prompt": "{file:" + brief.as_posix() + "}",
            **({"steps": int(scope["steps"])} if scope.get("steps") else {}),
            "permission": {"edit": "ask", "bash": "ask", "webfetch": "ask",
                           "skill": {"*": "allow"}}}},
        "default_agent": "pa",
        "autoupdate": False, "share": "disabled",
    }


def link_crush_skills() -> str:
    """~/.agents/skills -> ~/.crush/skills, once, as a junction (no admin rights needed).
    Only OpenCode-style tools read ~/.agents/skills, so Claude Code's own list is unchanged."""
    if SHARED_SKILLS.exists():
        return f"skills: {SHARED_SKILLS} already present"
    if not CRUSH_SKILLS.is_dir():
        return "skills: no Crush skills folder to share"
    SHARED_SKILLS.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(SHARED_SKILLS), str(CRUSH_SKILLS)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return f"skills: could not link {SHARED_SKILLS} ({done.stderr.strip()[:120]})"
    return f"skills: linked {SHARED_SKILLS} -> {CRUSH_SKILLS}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--pa", required=True, help="an approved PA whose runtime is opencode")
    ap.add_argument("--project", default=str(REPO), help="folder OpenCode opens (default: "
                                                        "the harness)")
    ap.add_argument("--task", default="", help="this session's task (layer 3 of the brief)")
    ap.add_argument("--worker", action="store_true",
                    help="let this session's crew server run queued jobs too")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the brief and config, print what would run, do not start")
    args = ap.parse_args(argv)

    from crew import pa_brief, personnel
    from crew.config import load_config
    staff = personnel.load()
    cfg = staff.get("pa") or {}
    scope = (cfg.get("scopes") or {}).get(args.pa) or {}
    if args.pa not in (cfg.get("approved") or []):
        raise SystemExit(f"{args.pa} is not an approved PA "
                         f"(approved: {', '.join(cfg.get('approved') or [])})")
    if scope.get("runtime") != "opencode":
        raise SystemExit(f"{args.pa}'s runtime is {scope.get('runtime')!r}: open the Claude "
                         f"Code desktop app instead (its brief comes from a SessionStart hook)")

    home = Path(load_config().state_home) / "pa" / args.pa
    home.mkdir(parents=True, exist_ok=True)
    brief = home / "brief.md"
    brief.write_text(pa_brief.render(args.pa, args.task, staff), encoding="utf-8")
    config = home / "opencode.json"
    config.write_text(json.dumps(opencode_config(args.pa, scope, staff, brief, args.worker), indent=2),
                      encoding="utf-8")
    print(f"brief: {brief} ({len(brief.read_text(encoding='utf-8'))} characters, once)")
    print(f"config: {config}")

    from opencode_trial import _opencode_exe
    exe = _opencode_exe()
    if args.dry_run:
        print(f"would run: {exe} {args.project}   (OPENCODE_CONFIG={config})")
        return 0
    print(link_crush_skills())
    env = dict(os.environ)
    env["OPENCODE_CONFIG"] = str(config)
    env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(int(scope.get("reply_tokens") or 32768))
    if not env.get("SYNTHETIC_API_KEY"):
        from providers.registry import _get_provider, _resolve_secret
        key = _resolve_secret((_get_provider("synthetic") or {}).get("auth") or {})
        if key:
            env["SYNTHETIC_API_KEY"] = key
    print(f"opening OpenCode with {args.pa} as the PA in {args.project} ...")
    return subprocess.call([exe, args.project], env=env)


if __name__ == "__main__":
    sys.exit(main())
