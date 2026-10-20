"""Crew CLI.

    python -m crew serve                      MCP server over stdio (+ worker)
    python -m crew worker                     worker only, no MCP
    python -m crew submit spec.json [--by Kris]
    python -m crew run TASK_ID                run one ready task now (foreground)
    python -m crew status [TASK_ID]
    python -m crew result TASK_ID
    python -m crew inbox
    python -m crew review TASK_ID approve|revise|reject|acknowledge --by Kris
                          [--notes ...] [--constraint ...] [--lesson ...]...
                          [--must-read PATH]... [--ascii-only]
    python -m crew roster
    python -m crew promote PERSONA TASK_TYPE STAGE --by Kris [--demote]

Promotion lives only here, on purpose: the MCP tools cannot raise a crew
member's autonomy, so no agent can promote itself.
"""

import argparse
import json
import pathlib
import sys

from .config import CrewError


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    # Model output is full of typographic Unicode; the Windows console
    # default (cp1252) cannot print it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    # `unify` takes its own flags, and argparse.REMAINDER does not capture
    # leading options, so it is delegated before the parent parser runs.
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "unify":
        from . import unify
        return unify.main(raw[1:])
    if raw and raw[0] == "vendor":
        from . import vendor
        return vendor.main(raw[1:])

    ap = argparse.ArgumentParser(prog="python -m crew")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("worker")
    s = sub.add_parser("submit"); s.add_argument("spec"); s.add_argument("--by", default="Kris")
    s.add_argument("--run", action="store_true",
                   help="claim before queueing and run it now in this process")
    s = sub.add_parser("run"); s.add_argument("task_id")
    s = sub.add_parser("status"); s.add_argument("task_id", nargs="?")
    s = sub.add_parser("result"); s.add_argument("task_id")
    sub.add_parser("inbox")
    s = sub.add_parser("review")
    s.add_argument("task_id"); s.add_argument("decision")
    s.add_argument("--by", required=True); s.add_argument("--notes", default="")
    s.add_argument("--constraint", default="")
    s.add_argument("--lesson", action="append", default=[])
    s.add_argument("--accept-member-notes", action="store_true")
    s.add_argument("--must-read", action="append", default=[])
    s.add_argument("--ascii-only", action="store_true")
    sub.add_parser("roster")
    sub.add_parser("budget")
    s = sub.add_parser("campaign")
    s.add_argument("action", choices=["run", "status", "plan"])
    s.add_argument("file", help="campaign json (run/plan) or campaign name (status)")
    s.add_argument("--deadline", default="",
                   help="ISO time to stop starting new work, e.g. 2026-09-20T10:00")
    s.add_argument("--max-requests", type=int, default=0)
    s.add_argument("--resume", action="store_true",
                   help="keep the tasks a stopped run already accepted; rerun the rest")
    s = sub.add_parser("loadlab")
    s.add_argument("file", help="load lab json")
    s = sub.add_parser("promote")
    s.add_argument("persona"); s.add_argument("task_type"); s.add_argument("stage")
    s.add_argument("--by", required=True); s.add_argument("--demote", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "serve":
        from .server import main as serve
        serve()
        return 0

    if args.cmd == "campaign":
        from . import campaign as camp
        if args.action == "status":
            from .config import load_config
            home = pathlib.Path(load_config().state_home) / "campaigns" / args.file
            path = home / "status.json"
            if not path.exists():
                print(f"no campaign status at {path}", file=sys.stderr)
                return 2
            print(path.read_text(encoding="utf-8"))
            return 0
        spec = camp.load(args.file)
        if args.deadline:
            spec["deadline"] = args.deadline
        if args.max_requests:
            spec["max_requests"] = args.max_requests
        c = camp.Campaign(spec)
        if args.action == "run" and args.resume:
            kept = c.resume()
            print(f"resuming {c.name}: kept {len(kept)} accepted task(s): {', '.join(kept)}")
        if args.action == "plan":
            _print({"name": c.name, "tasks": {i: {k: t[k] for k in
                    ("kind", "team", "member", "depends")}
                    for i, t in c.tasks.items()},
                    "max_requests": c.max_requests,
                    "deadline": spec.get("deadline")})
            return 0
        _print(c.run())
        return 0

    if args.cmd == "loadlab":
        from .runners import load_lab
        return load_lab.main([args.file])

    from .core import Crew
    crew = Crew()
    try:
        if args.cmd == "worker":
            print("crew worker running; Ctrl+C to stop", file=sys.stderr)
            crew.work_forever()
        elif args.cmd == "submit":
            with open(args.spec, encoding="utf-8") as fh:
                job = crew.submit(json.load(fh), args.by, claim=args.run)
            _print(job)
            if args.run:
                try:
                    _print(crew.run_job(job["task_id"]))
                finally:
                    crew.store.release(job["task_id"])
        elif args.cmd == "run":
            if not crew.store.try_claim(args.task_id):
                raise CrewError(f"{args.task_id} is claimed by another worker")
            try:
                _print(crew.run_job(args.task_id))
            finally:
                crew.store.release(args.task_id)
        elif args.cmd == "status":
            _print(crew.status(args.task_id))
        elif args.cmd == "result":
            _print(crew.result(args.task_id))
        elif args.cmd == "inbox":
            _print(crew.inbox())
        elif args.cmd == "review":
            _print(crew.review(args.task_id, args.decision, args.by, args.notes,
                               args.constraint, args.lesson, args.accept_member_notes,
                               args.must_read, args.ascii_only))
        elif args.cmd == "roster":
            _print(crew.roster.summary())
        elif args.cmd == "budget":
            _print(crew.rate.report())
        elif args.cmd == "promote":
            _print(crew.roster.promote(args.persona, args.task_type, args.stage,
                                       args.by, args.demote))
    except CrewError as e:
        print(f"crew: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
