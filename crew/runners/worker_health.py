"""Which crew workers are running - and are any of them running old code?

Each worker records the git revision it started from. A worker that started
before a pull keeps claiming jobs with the rules that were just replaced: on
2026-10-25 the claim-heartbeat fix landed while two workers started two days
earlier were still running, and one job was run twice for it. Nothing told anyone,
because a running worker looks the same until you ask it which code it has.

    python crew/runners/worker_health.py          the workers, and a warning
    python crew/runners/worker_health.py --json   the same, for another program

Exit codes: 0 every worker is on HEAD, 1 at least one is stale, 2 none running.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crew.config import load_config  # noqa: E402
from crew.store import Store, code_revision  # noqa: E402


def workers() -> list:
    """Every live worker: the registry first (it knows the start time), then any
    worker still holding a claim that the registry does not know about - those are
    the ones started before the registry existed, i.e. exactly the stale ones."""
    store = Store(load_config())
    out = store.live_workers()
    seen = {w.get("pid") for w in out} | {w.get("owner") for w in out}
    for w in store.claim_workers():
        if w.get("pid") not in seen and w.get("owner") not in seen:
            out.append(w)
    return out


def _claim_age(since) -> str:
    """A worker known only from its claim has no start time; its claim does."""
    import time as _t
    try:
        mins = (_t.time() - float(since)) / 60.0
    except (TypeError, ValueError):
        return "started ?"
    return f"claim held {mins:.0f} min"


def stale(items=None) -> list:
    """The live workers whose revision is not HEAD. `unknown` counts as stale:
    a worker that cannot say which code it runs cannot be trusted to be current."""
    head = code_revision()
    out = []
    for w in items if items is not None else workers():
        if (w.get("revision") or "unknown") != head:
            out.append(w)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    items, head = workers(), code_revision()
    old = stale(items)

    if args.json:
        print(
            json.dumps(
                {"head": head, "workers": items, "stale": [w.get("pid") for w in old]},
                indent=2,
            )
        )
    else:
        print(f"crew workers: {len(items)} running, HEAD is {head}")
        for w in items:
            rev = w.get("revision") or "unknown"
            flag = "  <-- STALE" if rev != head else ""
            when = w.get("started") or _claim_age(w.get("since"))
            print(
                f"  pid {w.get('pid'):<7} {w.get('client', '?'):<8} "
                f"{when:<22} {rev}{flag}"
            )
        if old:
            print(
                f"\nWARNING: {len(old)} of {len(items)} worker(s) are running code other "
                f"than HEAD.\nA stale worker claims jobs with the rules it started with. "
                f"Restart it after a pull:\n"
                f"  python -m crew.worker --stop-file runs/crew/stop  (or stop the "
                f"server that owns pid {old[0].get('pid')})"
            )
        elif items:
            print("\nAll workers are on HEAD.")

    if not items:
        return 2
    return 1 if old else 0


if __name__ == "__main__":
    raise SystemExit(main())
