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


def provider_model(pa: str, scope: dict, staff: dict) -> tuple:
    """-> (model id, its entry under the Synthetic provider)."""
    model = scope["model"]
    member = (staff.get("members") or {}).get(pa) or {}
    return model, {"name": f"{pa} ({model})",
                   "limit": {"output": int(scope.get("reply_tokens") or 32768),
                             "context": int(member.get("context_window") or 200000)}}


# Kris 2026-10-24: "a healthy toggle at the top to switch between planning with the PA and
# Assigning the Crew. This way I can talk to the agent in charge to plan or adapt to new
# information without immediately assigning work." In plan mode the crew's write tools are
# off (enforced here, not just asked of the model), and so is every edit but the chat's own
# artifacts. Tool names are the MCP server's name + "_" + the tool's (crew_crew_roster).
PLAN_DENIED_TOOLS = ("crew_crew_submit", "crew_crew_review")

# The read-only commands the PA brief lists (crew/pa_brief.py COMMANDS) run without a card in
# The Crew's chat; any other shell command asks. 2026-10-24: a PA reaching for
# active_status.py lost its turn when the card was refused. OpenCode checks each command of a
# chain on its own, so `git log; anything` still asks for `anything`.
READ_ONLY_COMMANDS = (
    "python crew/runners/active_status.py", "python crew/runners/member_stats.py",
    "python crew/runners/rs_scoping.py", "python crew/runners/pm_queue.py status",
    "python -m crew budget", "git status", "git log", "git diff", "git show",
    # Same day: models list folders with PowerShell whatever the brief says, and a card per
    # listing would bury the PM. Read-only cmdlets only; paths outside the project still ask
    # (OpenCode's external_directory rule).
    "Get-ChildItem", "Get-Item", "Get-Content", "Test-Path", "Resolve-Path", "Split-Path",
    "Join-Path", "Select-Object", "Select-String", "Where-Object", "Sort-Object",
    "Measure-Object", "Format-Table", "Format-List", "Out-String", "Write-Output",
    "ConvertFrom-Json",
    # Kris 2026-10-27: PAs hand off and reply through vault mail. Not read-only, but it only
    # ever creates new message files and moves the PA's own inbox pointers (create-only).
    "python crew/runners/mail.py",
)


def chat_bash(mode: str = "assign") -> dict:
    """In plan mode every other command is refused, not asked: 2026-10-25 a plan-mode PA
    (Claude, in The Crew's chat) was allowed a shell card and rewrote another chat's
    tasks.json and plan.md with it. A redirection turns a read-only command into a write, so
    `*>*` comes last (OpenCode: the last matching rule wins)."""
    other = "deny" if mode == "plan" else "ask"
    rules = {"*": other}
    for command in READ_ONLY_COMMANDS:
        for form in {command, command.replace("/", "\\")}:
            rules[form + "*"] = "allow"
    rules["*>*"] = other
    return rules


def pa_agent(pa: str, scope: dict, brief: Path, artifacts: Path = None, mode: str = None) -> dict:
    """A PA as an OpenCode primary agent: its model, its brief as the prompt, its steps.
    Edits, shell commands and web fetches ask the human; crew MCP tools and skills do not.
    With `artifacts`, writing its own plan/walkthrough there asks nobody: the last matching
    rule wins in OpenCode, and the pattern is given relative and absolute, both slash forms.
    (Measured 2026-10-24: OpenCode 1.2.6 on Windows matches the project-relative path with
    backslashes, `runs\\crew\\pa\\chats\\...`.) `mode` is "plan" or "assign" for The Crew's
    chat (see PLAN_DENIED_TOOLS); None is the terminal session of main() below."""
    edit = "ask"
    if artifacts is not None:
        edit = {"*": "deny" if mode == "plan" else "ask"}
        forms = {artifacts.as_posix(), str(artifacts)}
        try:
            relative = artifacts.relative_to(REPO)
            forms |= {relative.as_posix(), str(relative)}
        except ValueError:
            pass
        for form in sorted(forms):
            edit[form.rstrip("/\\") + ("\\*" if "\\" in form else "/*")] = "allow"
    bash = chat_bash(mode) if mode in ("plan", "assign") else "ask"
    permission = {"edit": edit, "bash": bash, "webfetch": "ask", "skill": {"*": "allow"}}
    if mode == "plan":
        permission.update({tool: "deny" for tool in PLAN_DENIED_TOOLS})
    what = {"plan": "plans with the PM (cannot assign crew work)",
            "assign": "assigns the crew"}.get(mode, "is the PA of The Crew")
    return {"mode": "primary", "description": f"{pa} {what}",
            "model": f"synthetic/{scope['model']}", "prompt": "{file:" + brief.as_posix() + "}",
            **({"steps": int(scope["steps"])} if scope.get("steps") else {}),
            "permission": permission}


def base_config(models: dict, agents: dict, default_agent: str, client: str,
                worker: bool = False) -> dict:
    """The parts every PA config shares: Synthetic, the crew MCP, LSP, no updates or sharing."""
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
            "models": models}},
        "mcp": {"crew": {"type": "local", "command": _keeper("crew") + [PYTHON, str(REPO / "crew_server.py")],
                         # worker off by default: a worker would also run every stale READY job in
                         # the queue (14 on 2026-10-23); the PA runs work with campaigns
                         "environment": {"CREW_CLIENT": client,
                                         "CREW_WORKER": "1" if worker else "0"},
                         "enabled": True, "timeout": 120000}},
        "lsp": lsp,
        "agent": agents,
        "default_agent": default_agent,
        "autoupdate": False, "share": "disabled",
    }


def opencode_config(pa: str, scope: dict, staff: dict, brief: Path, worker: bool = False) -> dict:
    """The generated opencode.json: one provider, one primary agent, the crew MCP."""
    model, entry = provider_model(pa, scope, staff)
    return base_config({model: entry}, {"pa": pa_agent(pa, scope, brief)}, "pa",
                       f"OpenCode-{pa}", worker)


def with_real_python(env: dict) -> dict:
    """`python` in the PA's shell must be this Python (3.14, with the harness's packages), not
    the hermes venv that is first on this machine's PATH."""
    first = [str(Path(PYTHON).parent), str(Path(PYTHON).parent / "Scripts")]
    env["PATH"] = os.pathsep.join(first + [env.get("PATH", "")])
    return env


def synthetic_key() -> str:
    """The Synthetic key from the environment or the provider registry; never printed."""
    if os.environ.get("SYNTHETIC_API_KEY"):
        return os.environ["SYNTHETIC_API_KEY"]
    from providers.registry import _get_provider, _resolve_secret
    return _resolve_secret((_get_provider("synthetic") or {}).get("auth") or {}) or ""


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
    env = with_real_python(dict(os.environ))
    env["OPENCODE_CONFIG"] = str(config)
    env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(int(scope.get("reply_tokens") or 32768))
    key = synthetic_key()
    if key:
        env["SYNTHETIC_API_KEY"] = key
    print(f"opening OpenCode with {args.pa} as the PA in {args.project} ...")
    return subprocess.call([exe, args.project], env=env)


if __name__ == "__main__":
    sys.exit(main())
