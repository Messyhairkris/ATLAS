"""The building directory: who holds which post, what a job of each kind
would get right now, what the Inspector is trialling, and what it proposes.

  python crew/runners/building.py                     # the directory
  python crew/runners/building.py --budgets scout     # every member's budget for one task type
  python crew/runners/building.py --trial Gordon scout lsp=true --because "LSP for navigation"
  python crew/runners/building.py --proposals         # open Inspector proposals
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crew import inspector, personnel  # noqa: E402
from crew.config import load_config  # noqa: E402


def _value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budgets", metavar="TASK_TYPE")
    ap.add_argument("--trial", nargs="+", metavar="ARG",
                    help="MEMBER TASK_TYPE key=value ...")
    ap.add_argument("--because", default="started by the PA")
    ap.add_argument("--proposals", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    staff = personnel.load()
    hist = personnel.history(Path(cfg.state_home) / "jobs")
    members = [m for m in staff["members"]]

    if a.trial:
        member, tt, *kv = a.trial
        overrides = {k: _value(v) for k, v in (x.split("=", 1) for x in kv)}
        t = inspector.start_manual_trial(cfg, member, tt, overrides, a.because)
        print(json.dumps(t, indent=1))
        return 0

    if a.proposals:
        p = Path(cfg.state_home) / "inspector" / "proposals.jsonl"
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] \
            if p.is_file() else []
        for r in rows:
            if r.get("status") == "open":
                print(f"- [{r['store']}] {r['member']}/{r['task_type']} ({r['job']}): "
                      f"{r['detail']} -> {r['proposal']}")
        print(f"{sum(r.get('status') == 'open' for r in rows)} open proposal(s)")
        return 0

    if a.budgets:
        print(f"| member | requests | tokens | working context | obs chars | trial | from |")
        print("|---|---|---|---|---|---|---|")
        for m in members:
            tr = inspector.active_trial(cfg, m, a.budgets)
            b = personnel.budget_for(staff, m, a.budgets, hist, (tr or {}).get("overrides"))
            print(f"| {m} | {b['max_requests']} | {b['max_tokens']:,} | {b['context_tokens']:,} "
                  f"| {b['observation_chars']:,} | {(tr or {}).get('id', '')} | {b['source']} |")
        return 0

    print("# The building\n")
    print("| post | holders (first is sent first) |\n|---|---|")
    for post, holders in staff["posts"].items():
        if post != "comment":
            print(f"| {post} | {', '.join(holders)} |")
    print("\n| member | window | working context | posts | measured |\n|---|---|---|---|---|")
    for m in members:
        d = staff["members"][m]
        print(f"| {m} | {d.get('context_window', 0):,} | "
              f"{personnel.working_context_tokens(staff, m):,} | "
              f"{', '.join(d.get('posts') or []) or '-'} | {d.get('measured', '')[:90]} |")
    trials = inspector._load_trials(cfg)
    print(f"\nTrials: {sum(t['status'] == 'running' for t in trials)} running, "
          f"{sum(t['status'] == 'kept' for t in trials)} kept, "
          f"{sum(t['status'] == 'reverted' for t in trials)} reverted")
    for t in trials:
        print(f"- {t['status']:8} {t['member']}/{t['task_type']} {t['overrides']} "
              f"({len(t['jobs'])}/{inspector.TRIAL_WINDOW} jobs) - {t['because']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
