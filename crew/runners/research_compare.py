"""Ask several crew members the same research question, side by side.

Kris, 2026-09-21: "I would like to see if the more verbose teammates are good at
research as well as coding." One question, the same sources, the same gates, the
same budget - so the only thing that differs is the member. Members on different
models run at the same time (Synthetic allows concurrent requests to different
models), so four digests cost the wall-clock time of the slowest.

    python crew/runners/research_compare.py --members Hoss Nemotron Barry Gordon \\
        --question question.md --name ahk-cli

Each digest lands in runs/crew/outbox/research/<name>-<member>.md, and a
summary.json beside them records the gate result, requests, tokens and seconds.
Grading what they SAY is a reader's job: the gates prove a digest is cited and
grounded, not that it is right.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.config import load_config                          # noqa: E402
from crew.core import Crew                                   # noqa: E402


def run_one(member: str, question: str, name: str, out_dir: Path, budget: dict,
            results: dict) -> None:
    crew = Crew()
    started = time.time()
    record = {"member": member}
    try:
        brief = crew.submit({"task_type": "research_digest",
                             "title": f"{name}: {member}",
                             "instructions": question,
                             "assigned_to": member,
                             "output": {"root": str(out_dir),
                                        "files": [f"{name}-{member.lower()}.md"]},
                             "budget": budget},
                            submitted_by="research_compare", claim=True)
        job = crew.run_job(brief["task_id"])
        result = (crew.store.load(brief["task_id"]).get("result") or {})
        record.update(job_id=brief["task_id"], status=job.get("status"),
                      requests=result.get("requests"), tokens=result.get("tokens"),
                      stop_reason=result.get("stop_reason"),
                      failed_gates=[f"{s['rung']}: {s['detail']}"[:200]
                                    for s in result.get("steps", []) if not s["ok"]],
                      error=result.get("error"))
    except Exception as exc:                                  # noqa: BLE001
        record.update(status="error", error=f"{type(exc).__name__}: {exc}"[:300])
    record["seconds"] = round(time.time() - started, 1)
    results[member] = record
    print(f"[{time.strftime('%H:%M:%S')}] {member}: {record.get('status')} "
          f"in {record['seconds']}s, {record.get('requests')} requests", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", nargs="+", required=True)
    ap.add_argument("--question", required=True, help="a file holding the question")
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-requests", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=150000)
    args = ap.parse_args(argv)

    question = Path(args.question).read_text(encoding="utf-8")
    out_dir = Path(load_config().state_home) / "outbox" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    budget = {"max_requests": args.max_requests, "max_tokens": args.max_tokens}
    results: dict = {}
    threads = [threading.Thread(target=run_one, args=(m, question, args.name, out_dir,
                                                      budget, results))
               for m in args.members]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    summary = out_dir / f"{args.name}-summary.json"
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
