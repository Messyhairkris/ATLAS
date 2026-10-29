"""Put an approved OpenCode PA (Kimi, Qwen, Gordon) to work on ONE feature, headless.

Kris, 2026-10-26: "You should assign Additional PAs to work on different features at the
same time. Concurrent calls are still queued." Claude stays the senior PA: it writes the
feature brief and the check, and reviews the diff before anything is merged. This runs one
PA, unattended, the way opencode_trial.py runs one crew member:

- its own git worktree and branch (C:/Users/user/pa-work/<slug>), so PAs working
  at once never touch each other's files, and OpenCode's project fence is that folder;
- edits allowed only inside it; shell commands refused except the tests and builds the
  brief needs and read-only git/listing; no web fetch; nothing is committed by the PA;
- the PA brief (crew/pa_brief.py) once as the agent prompt, the build rules below, and the
  feature brief as the first message - nothing is added per reply;
- after the PA stops, the runner runs the check commands itself; a failing check goes back
  to the same session as machine output, up to --rounds times;
- usage is written to the crew's telemetry ledger, and status.json says it is working.

  python crew/runners/pa_build.py --pa Gordon --repo C:/Users/user/ATLAS-api-harness ^
      --branch pa/gordon-changes --brief brief.md --check "python -m pytest -q tests/test_x.py"
"""

import argparse
import datetime as dt
import json
import os
import re
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "v3-service"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from opencode_trial import LEDGER, OPENCODE, _events, _usage, _writes_outside  # noqa: E402

WORK = Path("C:/Users/user/pa-work")

BUILD_RULES = """

## This session: you BUILD one feature yourself

You are working alone, unattended, in a git worktree: {worktree} (branch {branch}).
Claude, the senior PA, wrote the brief in your first message and will review your diff.

1. Only this folder exists for you. Edits outside it are refused.
2. Windows 10, and the shell behind the bash tool is **Windows PowerShell**, not cmd.exe and
   not git-bash (measured 2026-10-28: opencode runs `powershell -NoProfile -ExecutionPolicy
   Bypass -Command`). cmd.exe syntax therefore cannot work here: no `dir /s /b`, no `for %f`,
   no `2>nul`. PowerShell has `Get-ChildItem -Recurse -Filter`, `ForEach-Object`, `2>$null`.
2b. Find and read files with the built-in glob, grep, list and read tools - NOT the shell.
   Use the shell only for cargo, pytest and git. Commands you may run: {allowed}. No pipes
   (`|`), no `&`, no redirection (`>`, `2>&1`), and every piped or chained part is checked
   too; outputs are captured already, so none of them are needed. Every other command is
   refused. If a call is refused, do NOT try another form of it - use the built-in tool
   instead, and carry on.
3. Build exactly what the brief asks. Touch only the files it names. Do not reformat or
   "tidy" code you were not asked to change; match the surrounding style and comments.
4. Write tests for what you build. These checks must pass, and the runner runs them
   itself when you stop: {checks}
5. Do not commit. Never print or copy a key, token or password. No network.
6. When the checks pass, write PA_REPORT.md in the worktree root: what you built, the files,
   how you checked it (commands and their result lines), and anything you could not do.
   (The runner moves it out of the tree to the build's own folder afterwards - write it there
   anyway, that is where it is collected from.) Then stop.
"""

ALLOWED = ("python -m pytest", "python -I -m pytest", "git status", "git diff", "git log",
           "git show", "ls", "dir", "Get-ChildItem", "Get-Content", "Select-String", "cat",
           "type", "rg", "grep", "head", "tail", "wc",
           # Read-only PowerShell cmdlets (Kris, 2026-10-28): they only ever appear as a pipe
           # stage, and opencode checks every stage, so a display pipe used to be refused. All
           # read; none writes. `2>&1` and `>` are deliberately NOT matched here - a pattern
           # like "*2>&1*" would also match "x > file 2>&1", which is a write.
           "Select-Object", "Format-Table", "Format-List", "Sort-Object", "Where-Object",
           "Measure-Object", "Compare-Object", "Test-Path", "Get-Item")
CARGO = ("cargo build", "cargo test", "cargo check")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def worktree(repo: Path, branch: str, base: str) -> Path:
    """The PA's own checkout; reused when it exists (a second run continues the work)."""
    path = WORK / f"{repo.name.lower()}-{_slug(branch)}"
    if path.is_dir():
        return path
    WORK.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(["git", "-C", str(repo), "worktree", "add", "-b", branch, str(path),
                          base], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"git worktree add failed: {out.stderr.strip()}")
    return path


def permissions(cargo: bool) -> dict:
    bash = {"*": "deny"}
    for command in ALLOWED + (CARGO if cargo else ()):
        bash[command + "*"] = "allow"
    bash["*>*"] = "deny"                  # a redirection turns a read into a write; last wins
    return {"edit": "allow", "webfetch": "deny", "external_directory": "deny", "bash": bash}


def config(pa: str, scope: dict, staff: dict, brief: Path, cargo: bool) -> dict:
    from crew import personnel
    model = scope["model"]
    member = personnel.member(staff, pa) or {}
    limits = {"output": int(scope.get("reply_tokens") or 32768),
              "context": int(member.get("context_window") or 131072)}
    perm = permissions(cargo)
    return {"$schema": "https://opencode.ai/config.json",
            "formatter": False,            # see pa_session.base_config
            "provider": {"synthetic": {
                "npm": "@ai-sdk/openai-compatible", "name": "Synthetic",
                "options": {"baseURL": "https://api.synthetic.new/v1",
                            "apiKey": "{env:SYNTHETIC_API_KEY}"},
                "models": {model: {"name": f"{pa} ({model})", "limit": limits}}}},
            "agent": {"pa-build": {"mode": "primary", "model": f"synthetic/{model}",
                                   "description": f"{pa} builds one feature",
                                   "prompt": "{file:" + brief.as_posix() + "}",
                                   **({"steps": int(scope["steps"])} if scope.get("steps") else {}),
                                   "permission": perm}},
            "permission": perm, "autoupdate": False, "share": "disabled"}


def run_checks(cwd: Path, checks: list, env: dict, timeout_s: int) -> tuple:
    """-> (all passed, the output the PA is shown when they did not)."""
    report, ok = [], True
    for command in checks:
        try:
            p = subprocess.run(command, cwd=str(cwd), shell=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env, timeout=timeout_s)
            passed, text = p.returncode == 0, (p.stdout + p.stderr)
        except subprocess.TimeoutExpired:
            passed, text = False, f"timed out after {timeout_s} s"
        ok &= passed
        report.append(f"$ {command}\n-> {'passed' if passed else 'FAILED'}\n{text[-3000:]}")
    return ok, "\n\n".join(report)


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def no_session_reason(err: str) -> str:
    """The stop reason when a round produced no session: the engine never started.

    The engine's own last error line is worth more than our summary of it: opencode
    prints its reason on stderr ("service=server error= failed", then "Error: Session
    not found"). A preflight, so a broken engine fails in seconds with its words.
    """
    lines = [l.strip() for l in (err or "").splitlines() if l.strip()]
    engine = next((l for l in reversed(lines) if "error" in l.lower()),
                  lines[-1] if lines else "")
    engine = _ANSI.sub("", engine).strip()
    base = "no session: the engine did not start, so nothing was built"
    return f"{base} (engine said: {engine})" if engine else base


def _actionable(report: str) -> bool:
    """True when some failed check printed something the PA can act on."""
    for block in report.split("\n\n$ "):
        head, _, text = block.partition("\n-> FAILED")
        if _ and text.strip():
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--pa", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--brief", required=True, help="the feature brief (markdown file)")
    ap.add_argument("--check", action="append", default=[], help="a command that must pass")
    ap.add_argument("--rounds", type=int, default=2, help="feedback rounds after the first")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds per round")
    ap.add_argument("--cargo-target", default="", help="parent of each build's own CARGO_TARGET_DIR; also allows cargo")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    from crew import pa_brief, personnel
    from crew.config import load_config
    from providers.registry import _get_provider, _resolve_secret
    staff = personnel.load()
    pa_cfg = staff.get("pa") or {}
    scope = (pa_cfg.get("scopes") or {}).get(a.pa) or {}
    if a.pa not in (pa_cfg.get("approved") or []) or scope.get("runtime") != "opencode":
        raise SystemExit(f"{a.pa} is not an approved OpenCode PA")
    # Kimi's Inbox build ran 3 rounds / 80 steps / 8.6M tokens on 2026-10-26 and
    # drained the week's credit: a member marked builds=false is refused here, and
    # max_rounds caps the feedback rounds whatever --rounds says.
    if scope.get("builds") is False:
        raise SystemExit(f"{a.pa} is not a building PA (personnel.json pa.scopes.{a.pa}.builds)")
    a.rounds = min(a.rounds, int(scope.get("max_rounds", a.rounds)))
    from crew import guard
    lim = guard.limits(a.pa, "build")
    a.rounds = min(a.rounds, int(lim.get("max_check_rounds", a.rounds)))
    repo = Path(a.repo).resolve()
    ws = worktree(repo, a.branch, a.base)
    home = Path(load_config().state_home) / "pa" / "builds" / ws.name
    if (home / "status.json").is_file() and not a.dry_run:
        # A rerun gets a clean folder, so the guard counts THIS run only (a rerun in place
        # counted the first attempt's 13 steps against the second, 2026-10-26).
        home.rename(home.with_name(f"{home.name}-{dt.datetime.now():%Y%m%d-%H%M%S}"))
    home.mkdir(parents=True, exist_ok=True)
    feature = Path(a.brief).read_text(encoding="utf-8")
    cargo = bool(a.cargo_target)
    allowed = ", ".join(f"`{c} ...`" for c in ALLOWED + (CARGO if cargo else ()))
    brief = home / "brief.md"
    brief.write_text(pa_brief.render(a.pa, f"build: {a.branch}", staff) + BUILD_RULES.format(
        worktree=ws, branch=a.branch, allowed=allowed,
        checks="; ".join(f"`{c}`" for c in a.check) or "(none given)"), encoding="utf-8")
    (home / "feature.md").write_text(feature, encoding="utf-8")
    cfg_path = home / "opencode.json"
    cfg_path.write_text(json.dumps(config(a.pa, scope, staff, brief, cargo), indent=1),
                        encoding="utf-8")
    if a.dry_run:
        print(f"worktree {ws}\nrun dir {home}\nbrief {len(brief.read_text(encoding='utf-8'))} chars")
        return 0

    env = {k: v for k, v in os.environ.items() if k != "CREW_HOME"}
    env["OPENCODE_CONFIG"] = str(cfg_path)
    # Its own OpenCode database: three PAs started at once on the shared
    # ~/.local/share/opencode/opencode.db, and two stopped on "database is locked"
    # before their first request (2026-10-26). Also keeps them out of the window's engine.
    env["XDG_DATA_HOME"] = str(home / "data")      # guard.launch sets the same
    env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(int(scope.get("reply_tokens") or 32768))
    if cargo:
        # One folder PER BUILD under --cargo-target: with one shared folder, two worktrees of
        # the same crate overwrote each other's binaries, and a check ran the OTHER PA's
        # tests ("running 0 tests" for a worktree with 44, 2026-10-26).
        env["CARGO_TARGET_DIR"] = str(Path(a.cargo_target) / ws.name)
    if not env.get("SYNTHETIC_API_KEY"):
        key = _resolve_secret((_get_provider("synthetic").get("auth") or {}))
        if key:
            env["SYNTHETIC_API_KEY"] = key       # into the child only; never printed

    started = dt.datetime.now().isoformat(timespec="seconds")

    def status(state: str, **extra) -> None:
        (home / "status.json").write_text(json.dumps({
            "state": state, "pid": os.getpid(), "pa": a.pa, "branch": a.branch,
            "worktree": str(ws), "started": started, **extra}, indent=1), encoding="utf-8")

    session, raw_all, err_all, checks_text = None, "", "", ""
    message, rounds, passed, outside, stopped, passing = feature, 0, False, [], "", []
    t0 = time.time()
    while rounds < 1 + a.rounds:
        rounds += 1
        status("running", round=rounds, you_might_see="an opencode.exe process; it works "
               "only inside its own worktree")
        argv = [OPENCODE, "run", message, "--agent", "pa-build", "--format", "json",
                "--dir", str(ws)] + (["--session", session] if session else [])
        out, err, _, stopped = guard.launch(
            argv, ws, env, home, f"round{rounds}", lim, t0, a.timeout,
            lambda c: (status("running", round=rounds, guard=c, you_might_see="an opencode.exe "
                              "process; it works only inside its own worktree"),
                       # one line per guard poll, so the terminal never looks idle
                       print(f"{dt.datetime.now():%H:%M:%S} {a.pa} round {rounds}: "
                             f"{c['steps']} steps, {c['tokens'] / 1e6:.2f}M tokens, "
                             f"{c['progress']} changes, {c['tool_errors']} errors",
                             flush=True)))
        raw_all, err_all = raw_all + (out or ""), err_all + (err or "")
        events = _events(out or "")
        session = session or next((e["sessionID"] for e in events if e.get("sessionID")), None)
        if not session:
            # The engine never started (its local server failed): no work happened, so
            # run_checks would grade an UNTOUCHED worktree and "pass" - a run that did not
            # happen must never be reported as a pass. Report the engine's own words.
            stopped = no_session_reason(err)
            break
        outside = _writes_outside(events, ws)
        if outside or stopped:
            break
        passed, checks_text = run_checks(ws, a.check, env, 1800)
        passing.append(checks_text.count("-> passed"))
        if passed or not session or not _actionable(checks_text):
            break                      # a failure with no output gives the PA nothing to fix
        if not guard.next_round(passing):
            stopped = f"no improvement: checks passing per round {passing}"
            break
        message = ("THE CHECKS FAILED. This is machine output, not an opinion. Fix the cause, "
                   "run the checks again, update PA_REPORT.md, then stop.\n\n" + checks_text)
    seconds = round(time.time() - t0, 1)
    (home / "opencode.jsonl").write_text(raw_all, encoding="utf-8")
    (home / "opencode.stderr.txt").write_text(err_all, encoding="utf-8")
    (home / "checks.txt").write_text(checks_text, encoding="utf-8")
    usage = _usage(_events(raw_all))
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"source": "opencode", "provider": "synthetic",
                             "model": scope["model"], "persona": a.pa,
                             "run_id": f"pa-build:{ws.name}", "duty": "pa:build",
                             "requests": usage["steps"], "prompt_tokens": usage["input"],
                             "completion_tokens": usage["output"],
                             "total_tokens": usage["input"] + usage["output"],
                             "latency_ms": round(seconds * 1000),
                             "ts": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")
    # The build's own report belongs with the build's other records, not in the tree: EVERY build
    # writes one, so in the worktree it is scratch that collides with the next build on merge
    # (Kris, 2026-10-28). Move it beside status.json, checks.txt and the round's stream, and
    # leave the tree clean - which is also why it is moved BEFORE the status below, so it is not
    # listed as a change the build made.
    report = ws / "PA_REPORT.md"
    wrote_report = report.is_file()
    if wrote_report:
        try:
            report.replace(home / "PA_REPORT.md")
        except OSError:
            pass
    stat = subprocess.run(["git", "-C", str(ws), "status", "--short"], capture_output=True,
                          text=True).stdout
    result = {"pa": a.pa, "branch": a.branch, "worktree": str(ws), "passed": passed,
              "stopped_by_guard": stopped, "rounds": rounds, "seconds": seconds, "usage": usage, "session": session,
              "wrote_outside": outside, "changed": stat.splitlines(),
              "report": wrote_report}
    (home / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    status("finished", passed=passed, stopped_by_guard=stopped, finished=dt.datetime.now().isoformat(timespec="seconds"))
    print(json.dumps({k: result[k] for k in ("pa", "branch", "passed", "stopped_by_guard",
                                              "rounds", "seconds")}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
