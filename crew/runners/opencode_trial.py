"""OpenCode trial: can a weaker crew member do better with a real agent framework?

Kris, 2026-09-25: "I would be interested in seeing if our less helpful crew
could take on the extra framework and improve the code." The crew's own loop
gives a member read-only tools and one shot per submission; OpenCode gives it
an edit -> run its own tests -> fix loop. This runs ONE member on ONE crew task
through OpenCode, then grades the result with exactly the gates a crew
code_task gets (airlock, API, no stubs, the hidden tests it never saw), so the
two routes are comparable.

Fenced in (opencode.json in a scratch folder): edits only inside the folder,
shell commands denied except `python -m pytest`, no web fetch, no outside
folders. Token usage is parsed from --format json and written to the crew's
telemetry ledger - OpenCode otherwise bypasses it (noted 2026-09-20).

  python C:/Users/user/ATLAS-api-harness/crew/runners/opencode_trial.py ^
      --member Barry --campaign C:/.../crew/campaigns/outline.json --task outline
"""

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "v3-service"))

from crew import gates  # noqa: E402
from crew.config import load_config  # noqa: E402

LEDGER = Path("C:/Users/user/Documents/Obsidian/Knowledge_Base/wiki/experiments/"
              "atlas-api-harness/runs/telemetry.jsonl")
HOUSE_STYLE = REPO / "crew" / "contracts" / "HOUSE_STYLE.md"
def _opencode_exe() -> str:
    """The native opencode.exe, never npm's opencode.CMD shim: a .CMD runs through
    cmd.exe, which cuts the command line at the first newline, so every multi-line
    prompt arrived as its FIRST LINE only - and with the message first, the -m/--dir/-f
    flags after it were lost too (2026-09-26). Every earlier OpenCode trial got a
    truncated prompt."""
    found = shutil.which("opencode") or "opencode"
    if not found.lower().endswith((".cmd", ".bat")):
        return found
    pkg = Path(found).parent / "node_modules" / "opencode-ai" / "node_modules"
    for flavour in ("opencode-windows-x64", "opencode-windows-x64-baseline"):
        exe = pkg / flavour / "bin" / "opencode.exe"
        if exe.is_file():
            return str(exe)
    raise SystemExit(f"only the {found} shim was found; it would truncate prompts")


OPENCODE = _opencode_exe()


def opencode_config(model_id: str, output_tokens: int, context_tokens: int) -> dict:
    # OpenCode's default output limit for a custom model is 32,000 tokens: Barry
    # thought until it and was cut off before writing a file (2026-09-26, the same
    # wall the crew hit - his measured need is 65,536). Give each member its real limits.
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"synthetic": {
            "npm": "@ai-sdk/openai-compatible", "name": "Synthetic",
            "options": {"baseURL": "https://api.synthetic.new/v1",
                        "apiKey": "{env:SYNTHETIC_API_KEY}"},
            "models": {model_id: {"name": model_id,
                                  "limit": {"output": output_tokens,
                                            "context": context_tokens}}}}},
        "permission": {"edit": "allow", "webfetch": "deny", "external_directory": "deny",
                       "bash": {"*": "deny", "python -m pytest*": "allow"}},
        "autoupdate": False, "share": "disabled"}


PROMPT = """You are a crew member writing ONE Python module, {module}, in this folder.
CONTRACT.md is the specification: satisfy it exactly. Its "Allowed imports" line is
enforced by a scanner; open(), eval, exec, file, network and registry access are refused.

Work like this: write {module}; write your own tests in test_mine.py from the contract;
run them with the shell command `python -m pytest -q test_mine.py`; fix what fails;
repeat until they pass. You cannot run any other shell command. When the tests pass,
stop. Hidden tests you never see decide the outcome, so test the contract's rules and
examples, not your own reading of them."""


RESCUE_PROMPT = """A crew member's attempt at {module} FAILED the grader. You are the
rescue session: {module} in this folder is that failed attempt. CONTRACT.md is the
specification. The grader's machine output is below - it is not an opinion.

Fix the cause in {module}; do not start over unless the file is unusable. Its
"Allowed imports" line is enforced by a scanner; open(), eval, exec, file, network and
registry access are refused. Write tests in test_mine.py for the failing rules, run
them with `python -m pytest -q test_mine.py` (the only shell command you may run), fix
what fails, and stop when they pass. Hidden tests you never see decide the outcome.

GRADER OUTPUT FOR THE FAILED ATTEMPT:
{failures}"""


def _usage(events: list) -> dict:
    """Sum token counts from OpenCode's JSON events, whatever the nesting."""
    tot = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "steps": 0}

    def walk(o):
        if isinstance(o, dict):
            t = o.get("tokens")
            if isinstance(t, dict) and ("input" in t or "output" in t):
                tot["input"] += int(t.get("input") or 0)
                tot["output"] += int(t.get("output") or 0)
                tot["reasoning"] += int(t.get("reasoning") or 0)
                tot["cache_read"] += int((t.get("cache") or {}).get("read") or 0)
                tot["steps"] += 1
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(events)
    return tot


def _grade(ws: Path, task: dict, deps: dict) -> list:
    """Exactly the gates a crew code_task gets."""
    mod = ws / task["module"]
    if not mod.is_file():
        return [{"rung": "output", "ok": False, "detail": f"{task['module']} was not written"}]
    # the same mechanical fixes the crew route applies before gating (em dashes,
    # curly quotes...) - Kris's rule: mechanical fixes never go back to a model.
    # Nemotron's OpenCode module failed only on one em dash before this.
    from crew import autofix
    fixed, notes = autofix.apply({mod.name: mod.read_text(encoding="utf-8")}, "", None)
    if notes:
        mod.write_text(fixed[mod.name], encoding="utf-8")
    src = mod.read_text(encoding="utf-8")
    dep_names = sorted(n[:-3] for n in deps)
    steps = [gates.ascii_only(src, mod.name), gates.module_is_safe(src, mod.name, dep_names),
             gates.defines_api(src, task["api"], mod.name),
             gates.not_stubbed(src, task["api"], mod.name)]
    if all(s["ok"] for s in steps):
        hidden = {Path(h).name: Path(h).read_text(encoding="utf-8")
                  for h in task.get("hidden_tests", [])}
        # the grader uses the ORIGINAL accepted dependencies, never the workspace
        # copies the member could have edited
        steps.append(gates.hidden_tests_pass({mod.name: src, **deps}, hidden, 180,
                                             mod.name, dep_names))
    return steps


def _events(raw: str) -> list:
    out = []
    for line in raw.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _writes_outside(events: list, ws: Path) -> list:
    """Paths an edit/write tool call touched outside the run's own folder."""
    root = ws.resolve()
    bad = []
    for e in events:
        part = e.get("part") or {}
        if e.get("type") == "tool_use" and part.get("tool") in ("edit", "write", "patch"):
            path = ((part.get("state") or {}).get("input") or {}).get("filePath") or ""
            try:
                target = (root / path).resolve()
            except (OSError, ValueError):
                target = None
            if path and (target is None or (target != root and root not in target.parents)):
                bad.append(path)
    return sorted(set(bad))


def run(member: str, task: dict, label: str, timeout_s: int, seed: dict = None,
        duty: str = "crew:opencode_trial") -> dict:
    """seed (a rescue): {"files": {name: source}, "failures": grader text} - the
    failed attempt goes into the folder and the prompt asks for a fix, not a rewrite."""
    from providers.registry import resolve_alias
    cfg = load_config()
    model_id = resolve_alias("synthetic", member)
    home = Path(cfg.state_home) / "opencode" / label
    ws = home / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    # Its own git repo: OpenCode's "project" is the nearest git root, and its
    # external_directory fence is relative to that. Without this the project was the
    # whole ATLAS repo and a run could edit any file in it (two runs edited another
    # run's folder, 2026-09-26).
    subprocess.run(["git", "init", "-q", str(ws)], capture_output=True)
    contract = Path(task["contract"]).read_text(encoding="utf-8")
    if HOUSE_STYLE.is_file():
        contract += "\n\n---\n\n" + HOUSE_STYLE.read_text(encoding="utf-8")
    (ws / "CONTRACT.md").write_text(contract, encoding="utf-8")
    from crew import personnel
    reply = int((cfg.defaults.get("max_tokens_by_member") or {}).get(member, 32768))
    window = int(personnel.member(personnel.load(), member).get("context_window") or 131072)
    (ws / "opencode.json").write_text(json.dumps(opencode_config(model_id, reply, window),
                                                 indent=1), encoding="utf-8")
    from crew import eta
    (home / "status.json").write_text(json.dumps({
        "state": "running", "pid": os.getpid(), "member": member,
        "started": dt.datetime.now().isoformat(timespec="seconds"),
        "eta": eta.estimate(member, duty)}, indent=1), encoding="utf-8")
    deps = {Path(d).name: Path(d).read_text(encoding="utf-8")
            for d in (task.get("depends_modules") or [])}
    for name, src in deps.items():                  # already-accepted modules it builds on
        (ws / name).write_text(src, encoding="utf-8")
    for name, src in ((seed or {}).get("files") or {}).items():   # the failed attempt
        (ws / Path(name).name).write_text(src, encoding="utf-8")
    prompt = (RESCUE_PROMPT.format(module=task["module"], failures=seed.get("failures", ""))
              if seed else PROMPT.format(module=task["module"]))
    if deps:
        prompt += ("\n\nALREADY ACCEPTED MODULES in this folder, which you may import by name "
                   "and must not rewrite: " + ", ".join(sorted(deps)))
    if task.get("instructions"):
        prompt += "\n\nEMPHASIS FOR THIS TASK: " + task["instructions"]
    # The key comes from the same place the crew's own calls get it (environment
    # variable, else providers.json's api_key_fallback) and goes straight into
    # the child's environment - it is never printed or written anywhere.
    from providers.registry import _get_provider, _resolve_secret
    env = dict(os.environ)
    # OpenCode caps output at 32,000 tokens internally whatever the model config
    # says (Barry hit "length" at exactly 32000 with limit.output 65536); this
    # variable lifts it to the member's real ceiling.
    env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = str(reply)
    if not env.get("SYNTHETIC_API_KEY"):
        key = _resolve_secret((_get_provider("synthetic").get("auth") or {}))
        if key:
            env["SYNTHETIC_API_KEY"] = key
    session, stopped = {"id": None}, {"why": ""}
    from crew import guard
    lim = guard.limits(member, "fix" if seed else "module")

    def opencode(message: str, first: bool):
        # Round 1 ATTACHES the contract (-f), the way the crew preloads it: Nemotron,
        # left to find it, never opened it and invented an API (2026-09-26). Later
        # rounds continue the same session with the grader's failures - the same
        # feedback a crew member gets on a retry.
        # The message goes FIRST: -f takes several values and swallowed a trailing
        # message as a second file ("File not found: You are a crew member..."). Later
        # rounds name round 1's session: --continue resumes the newest session of the
        # project, which was another member's run (2026-09-26).
        argv = [OPENCODE, "run", message, "-m", f"synthetic/{model_id}", "--format", "json",
                "--dir", str(ws)] + (["-f", str(ws / "CONTRACT.md")] if first
                                     else ["--session", session["id"]])
        # The guard runs it (its own database, output to files, the whole tree killed on
        # a limit or the timeout - subprocess.run(timeout=) left the opencode.exe
        # grandchild running, Nemotron v3 hung 3 h past a 30 min timeout, 2026-09-26).
        out, err, code, why = guard.launch(argv, ws, env, home, f"round{rounds}", lim, t0,
                                           timeout_s)
        stopped["why"] = why
        return out, err, code

    t0 = time.time()
    raw_all, err_all, rounds, steps, code = "", "", 0, [], 0
    message, first = prompt, True
    passing = []
    while rounds < 1 + min(int(task.get("feedback_rounds", 2)), int(lim["max_check_rounds"])):
        rounds += 1
        raw, err, code = opencode(message, first)
        raw_all += raw
        err_all += err or ""
        events_now = _events(raw)
        if first:
            session["id"] = next((e["sessionID"] for e in events_now if e.get("sessionID")), None)
        outside = _writes_outside(events_now, ws)
        if outside:
            steps = [{"rung": "fence", "ok": False,
                      "detail": "wrote outside its folder: " + ", ".join(outside)}]
            break
        if stopped["why"]:
            steps = [{"rung": "guard", "ok": False, "detail": "stopped by the guard: " + stopped["why"]}]
            break
        steps = _grade(ws, task, deps)
        if all(s["ok"] for s in steps):
            break
        passing.append(sum(1 for s in steps if s["ok"]))
        if not guard.next_round(passing):
            steps.append({"rung": "guard", "ok": False,
                          "detail": f"no improvement: grader rungs passing per round {passing}"})
            break
        if not session["id"]:
            steps.append({"rung": "session", "ok": False,
                          "detail": "round 1 started no OpenCode session: " + (err or "")[:300]})
            break
        failed = "\n".join(f"- [{s['rung']}] {s['detail'][:1500]}" for s in steps if not s["ok"])
        message = ("THE GRADER FAILED YOUR MODULE. This is machine output, not an opinion - "
                   f"fix the cause in {task['module']}, run your tests again, then stop:\n{failed}")
        first = False
    seconds = round(time.time() - t0, 1)
    (home / "opencode.jsonl").write_text(raw_all, encoding="utf-8")
    (home / "opencode.stderr.txt").write_text(err_all, encoding="utf-8")
    events = _events(raw_all)
    usage = _usage(events)
    with open(LEDGER, "a", encoding="utf-8") as fh:        # close the ledger blind spot
        fh.write(json.dumps({"source": "opencode", "provider": "synthetic", "model": model_id,
                             "persona": member, "run_id": f"opencode:{label}",
                             "duty": duty, "requests": usage["steps"],
                             "prompt_tokens": usage["input"], "completion_tokens": usage["output"],
                             "total_tokens": usage["input"] + usage["output"],
                             "latency_ms": round(seconds * 1000),   # for crew/eta.py
                             "ts": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")
    passed = bool(steps) and all(s["ok"] for s in steps)
    result = {"member": member, "model": model_id,
              "route": "opencode-rescue" if seed else "opencode", "task": task["id"],
              "passed": passed, "rounds": rounds, "seconds": seconds, "exit": code,
              "usage": usage,
              # any test_*.py counts: Barry named his test_outline.py, not test_mine.py
              "own_tests_written": sorted(p.name for p in ws.glob("test_*.py")),
              "steps": steps}
    (home / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (home / "status.json").write_text(json.dumps({"state": "finished", "passed": passed}),
                                      encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", required=True)
    ap.add_argument("--campaign", help="campaign json (with --task)")
    ap.add_argument("--task")
    ap.add_argument("--spec", help="or: one code_task job spec json")
    ap.add_argument("--label")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    if a.spec:
        task = json.loads(Path(a.spec).read_text(encoding="utf-8"))
        task.setdefault("id", Path(task["module"]).stem)
    else:
        spec = json.loads(Path(a.campaign).read_text(encoding="utf-8"))
        task = next(t for t in spec["tasks"] if t["id"] == a.task)
    r = run(a.member, task, a.label or f"{task['id']}-{a.member}", a.timeout)
    print(json.dumps({k: r[k] for k in ("member", "passed", "seconds", "usage")}))
    print("\n".join(f"[{'ok' if s['ok'] else 'FAIL'}] {s['rung']}: {s['detail'][:200]}"
                    for s in r["steps"]))
