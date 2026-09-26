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
OPENCODE = shutil.which("opencode") or "opencode"


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


def run(member: str, task: dict, label: str, timeout_s: int) -> dict:
    from providers.registry import resolve_alias
    cfg = load_config()
    model_id = resolve_alias("synthetic", member)
    home = Path(cfg.state_home) / "opencode" / label
    ws = home / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
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
        "eta": eta.estimate(member, "crew:opencode_trial")}, indent=1), encoding="utf-8")
    deps = {Path(d).name: Path(d).read_text(encoding="utf-8")
            for d in (task.get("depends_modules") or [])}
    for name, src in deps.items():                  # already-accepted modules it builds on
        (ws / name).write_text(src, encoding="utf-8")
    prompt = PROMPT.format(module=task["module"])
    if deps:
        prompt += ("\n\nALREADY ACCEPTED MODULES in this folder, which you may import by name "
                   "and must not rewrite: " + ", ".join(sorted(deps)))
    if task.get("instructions"):
        prompt += "\n\nEMPHASIS FOR THIS TASK: " + task["instructions"]
    # The key comes from the same place the crew's own calls get it (environment
    # variable, else providers.json's api_key_fallback) and goes straight into
    # the child's environment - it is never printed or written anywhere.
    import os
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
    def opencode(message: str, first: bool):
        # Round 1 ATTACHES the contract (-f), the way the crew preloads it: Nemotron,
        # left to find it, never opened it and invented an API (2026-09-26). Later
        # rounds continue the same session with the grader's failures - the same
        # feedback a crew member gets on a retry.
        argv = [OPENCODE, "run", "-m", f"synthetic/{model_id}", "--format", "json",
                "--dir", str(ws)] + (["-f", str(ws / "CONTRACT.md")] if first else ["--continue"])
        # Not subprocess.run(timeout=): on Windows it kills only the direct child, the
        # opencode.exe grandchild keeps the pipes open, and the wait never ends (Nemotron
        # v3 hung 3 h past a 30 min timeout, 2026-09-26). On timeout, kill the whole tree.
        p = subprocess.Popen(argv + [message], cwd=str(ws), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8",
                             errors="replace", env=env)
        try:
            out, err = p.communicate(timeout=timeout_s)
            return out, err, p.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            try:
                out, _ = p.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                out = ""
            return out or "", "timeout", -1

    t0 = time.time()
    raw_all, err_all, rounds, steps, code = "", "", 0, [], 0
    message, first = prompt, True
    while rounds < 1 + int(task.get("feedback_rounds", 2)):
        rounds += 1
        raw, err, code = opencode(message, first)
        raw_all += raw
        err_all += err or ""
        steps = _grade(ws, task, deps)
        if all(s["ok"] for s in steps):
            break
        failed = "\n".join(f"- [{s['rung']}] {s['detail'][:1500]}" for s in steps if not s["ok"])
        message = ("THE GRADER FAILED YOUR MODULE. This is machine output, not an opinion - "
                   f"fix the cause in {task['module']}, run your tests again, then stop:\n{failed}")
        first = False
    seconds = round(time.time() - t0, 1)
    (home / "opencode.jsonl").write_text(raw_all, encoding="utf-8")
    (home / "opencode.stderr.txt").write_text(err_all, encoding="utf-8")
    events = []
    for line in raw_all.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    usage = _usage(events)
    with open(LEDGER, "a", encoding="utf-8") as fh:        # close the ledger blind spot
        fh.write(json.dumps({"source": "opencode", "provider": "synthetic", "model": model_id,
                             "persona": member, "run_id": f"opencode:{label}",
                             "duty": "crew:opencode_trial", "requests": usage["steps"],
                             "prompt_tokens": usage["input"], "completion_tokens": usage["output"],
                             "total_tokens": usage["input"] + usage["output"],
                             "latency_ms": round(seconds * 1000),   # for crew/eta.py
                             "ts": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")
    passed = bool(steps) and all(s["ok"] for s in steps)
    result = {"member": member, "model": model_id, "route": "opencode", "task": task["id"],
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
