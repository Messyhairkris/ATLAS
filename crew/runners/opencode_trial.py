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


def opencode_config(model_id: str) -> dict:
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"synthetic": {
            "npm": "@ai-sdk/openai-compatible", "name": "Synthetic",
            "options": {"baseURL": "https://api.synthetic.new/v1",
                        "apiKey": "{env:SYNTHETIC_API_KEY}"},
            "models": {model_id: {"name": model_id}}}},
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
    (ws / "opencode.json").write_text(json.dumps(opencode_config(model_id), indent=1),
                                      encoding="utf-8")
    (home / "status.json").write_text(json.dumps({"state": "running", "member": member,
                                                  "started": dt.datetime.now().isoformat(
                                                      timespec="seconds")}), encoding="utf-8")
    prompt = PROMPT.format(module=task["module"])
    if task.get("instructions"):
        prompt += "\n\nEMPHASIS FOR THIS TASK: " + task["instructions"]
    # The key comes from the same place the crew's own calls get it (environment
    # variable, else providers.json's api_key_fallback) and goes straight into
    # the child's environment - it is never printed or written anywhere.
    import os
    from providers.registry import _get_provider, _resolve_secret
    env = dict(os.environ)
    if not env.get("SYNTHETIC_API_KEY"):
        key = _resolve_secret((_get_provider("synthetic").get("auth") or {}))
        if key:
            env["SYNTHETIC_API_KEY"] = key
    t0 = time.time()
    try:
        p = subprocess.run([OPENCODE, "run", "-m", f"synthetic/{model_id}", "--format", "json",
                            "--dir", str(ws), prompt], cwd=str(ws), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout_s,
                           env=env)
        raw, err, code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        raw, err, code = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) \
            else (e.stdout or ""), "timeout", -1
    seconds = round(time.time() - t0, 1)
    (home / "opencode.jsonl").write_text(raw, encoding="utf-8")
    (home / "opencode.stderr.txt").write_text(err or "", encoding="utf-8")
    events = []
    for line in raw.splitlines():
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
                             "ts": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")
    # -- grade exactly like a crew code_task ------------------------------------------
    mod = ws / task["module"]
    steps = []
    if not mod.is_file():
        steps.append({"rung": "output", "ok": False, "detail": f"{task['module']} was not written"})
    else:
        src = mod.read_text(encoding="utf-8")
        steps = [gates.ascii_only(src, mod.name), gates.module_is_safe(src, mod.name),
                 gates.defines_api(src, task["api"], mod.name),
                 gates.not_stubbed(src, task["api"], mod.name)]
        if all(s["ok"] for s in steps):
            hidden = {Path(h).name: Path(h).read_text(encoding="utf-8")
                      for h in task.get("hidden_tests", [])}
            steps.append(gates.hidden_tests_pass({mod.name: src}, hidden, 180, mod.name, []))
    passed = bool(steps) and all(s["ok"] for s in steps)
    result = {"member": member, "model": model_id, "route": "opencode", "task": task["id"],
              "passed": passed, "seconds": seconds, "exit": code, "usage": usage,
              "own_tests_written": (ws / "test_mine.py").is_file(),
              "steps": steps}
    (home / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (home / "status.json").write_text(json.dumps({"state": "finished", "passed": passed}),
                                      encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--label")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    spec = json.loads(Path(a.campaign).read_text(encoding="utf-8"))
    task = next(t for t in spec["tasks"] if t["id"] == a.task)
    r = run(a.member, task, a.label or f"{a.task}-{a.member}", a.timeout)
    print(json.dumps({k: r[k] for k in ("member", "passed", "seconds", "usage")}))
    print("\n".join(f"[{'ok' if s['ok'] else 'FAIL'}] {s['rung']}: {s['detail'][:200]}"
                    for s in r["steps"]))
