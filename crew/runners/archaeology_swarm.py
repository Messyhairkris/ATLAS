"""Delegate an archaeology dig - planning included - to the crew.

Kris, 2026-09-22: can Gordon and Qwen not just execute a contract but SET ONE
UP - survey a dormant project, propose what from it is worth extracting, and
have Kimi unify their two takes into one plan - before any of it reaches a
senior for the go/no-go on turning backlog entries into real code_task
contracts? This is that experiment's harness, built once so it can be reused
on the next dormant folder, not just CASSIA.

Three stages, each judged the same way research_digest already is (cited,
grounded, wikilinks resolve) - a member's opinion is never taken on its own
say-so, whether the question is a fact or a plan:

  1. RECON  - each member independently surveys the folder and writes a
              cited research_digest: what is there, grounded in files it
              actually opened. Members on different models run at the same
              time (Synthetic allows concurrent requests to different
              models), so this costs the wall-clock of the slowest, not the
              sum.
  2. PLAN   - every member is handed BOTH digests (its own and every other
              member's) and drafts a candidate extraction backlog - still a
              research_digest, so the same citation/grounding gates apply,
              just aimed at a plan instead of a fact.
  3. UNIFY  - Kimi (the crew's senior_fallback, called directly through the
              provider layer - no interactive Crush session needed) reads
              every digest and every plan and writes ONE unified backlog,
              flagging contradictions and anything ungrounded. This is the
              report a senior reads before deciding what becomes a real
              campaign.

A gate failure gets ONE retry with the failure quoted back to the member,
the same "previous attempt failed these checks" pattern crew/campaign.py
uses for code tasks - Kris's observation that a second try often succeeds
where the first did not.

Some members are on a Beta/flakier Synthetic connection (Gordon, 2026-09-22)
and answer with a 5xx/timeout instead of an actual reply. That is not a
"previous attempt failed these checks" situation - nothing was judged, so
nothing should be quoted back or count against the member's real attempts.
Retries here follow crew/ahkrun.py's cold-boot/warm-boot naming: a COLD
attempt is a fresh submission (what --retries counts); a WARM retry is the
SAME submission tried again, only because the connection itself never
answered, with backoff and a bounded ceiling (PROVIDER_ERROR_LIMIT) so a
truly dead connection still gives up rather than hanging the run. Every wait
prints where it is and how long it is waiting - Kris's rule that slow is
always fine as long as it is visibly still happening, never silent.

Nothing here writes into a real project or starts a code_task. It is
read-only in, markdown (and one JSON backlog block) out, under
runs/crew/outbox/archaeology/<name>/. Turning a backlog entry into a
contract + hidden tests is a separate, later, human-gated step.

    python crew/runners/archaeology_swarm.py --name cassia \\
        --folder "C:/Users/user/Desktop/AHK V1 Agentic Project/CASSIA_Workspace_v3" \\
        --members Gordon Qwen \\
        --recon-question crew/campaigns/questions/cassia_recon.md \\
        --plan-question crew/campaigns/questions/cassia_plan.md \\
        --extra-read-root "C:/Users/user/Cross_talk"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.config import load_config                          # noqa: E402
from crew.core import Crew                                   # noqa: E402

RECON, PLAN, UNIFY = "recon", "plan", "unify"


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


class Status:
    """Live status.json, rewritten every time anything happens - Kris's rule
    that no program may look idle. `crew/runners/active_status.py` reads
    every run's status.json at once so the PM (or anyone) can see what's
    actively running without hunting down a log file per process."""

    def __init__(self, out_dir: Path, name: str, folder: str):
        self.path = out_dir / "status.json"
        self.lock = threading.Lock()
        self.data = {"name": name, "folder": folder, "stage": "starting",
                    "pid": os.getpid(), "members": {}, "requests_used": 0,
                    "started_at": _now(), "updated_at": _now()}
        self._write()

    def _write(self) -> None:
        self.data["updated_at"] = _now()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def stage(self, name: str) -> None:
        with self.lock:
            self.data["stage"] = name
            self._write()

    def member(self, member: str, **fields) -> None:
        with self.lock:
            self.data["members"].setdefault(member, {}).update(fields)
            if "requests" in fields:
                self.data["requests_used"] = sum(
                    m.get("requests") or 0 for m in self.data["members"].values())
            self._write()

    def done(self, outcome: str) -> None:
        with self.lock:
            self.data["stage"] = outcome
            self._write()


def _history(failed_gates: list) -> str:
    if not failed_gates:
        return ""
    return ("\n\nTHE PREVIOUS ATTEMPT FAILED THESE CHECKS. This is machine "
            "output, not an opinion - fix the cause, do not argue with it:\n- "
            + "\n- ".join(str(g) for g in failed_gates[:6]))


def submit_digest(member: str, instructions: str, out_dir: Path, filename: str,
                  budget: dict, read_roots: list, context_files: list) -> dict:
    """One attempt. Returns the brief (task_id, passed_gates, failed_gates, ...)."""
    crew = Crew()
    spec = {"task_type": "research_digest",
            "title": f"{out_dir.name}: {filename}",
            "instructions": instructions,
            "assigned_to": member,
            "output": {"root": str(out_dir), "files": [filename]},
            "budget": budget,
            **({"read_roots": list(read_roots)} if read_roots else {}),
            **({"context_files": list(context_files)} if context_files else {})}
    brief = crew.submit(spec, submitted_by="archaeology_swarm", claim=True)
    job_id = brief["task_id"]
    try:
        brief = crew.run_job(job_id)
        if brief.get("passed_gates"):
            # Gates passing only STAGES the file in the job's own folder; a
            # member below Supervised/Autonomous autonomy (the default) never
            # auto-applies. crew/campaign.py does this same explicit approve
            # after every accepted attempt - without it the output never
            # reaches out_dir, which is what crashed the first run of this
            # script on a later stage's read of a file that "passed" but was
            # never actually copied anywhere.
            crew.review(job_id, "approve", reviewer="archaeology_swarm",
                       notes=f"{out_dir.name}: every gate passed")
        return brief
    finally:
        crew.store.release(job_id)


PROVIDER_ERROR_LIMIT = 3
PROVIDER_BACKOFF_S = 45
# Any 5xx (Synthetic wraps upstream errors this way even for codes with no
# standard name, e.g. "524 unknown" from Gordon's Beta connection 2026-09-22)
# plus 429 and the httpx timeout/connection exception class names.
_PROVIDER_STATUS = re.compile(r"\b5\d{2}\b|\b429\b")
_PROVIDER_EXC = ("ReadTimeout", "ConnectTimeout", "ConnectError",
                 "RemoteProtocolError", "PoolTimeout")


def _is_provider_error(brief: dict) -> bool:
    """True when the member's own connection failed to answer at all - a Beta
    model's flaky API, not its work. Ported from crew/campaign.py's
    _provider_error, which makes the same call for code campaigns."""
    error = str(brief.get("error") or "")
    if not error or brief.get("failed_gates"):
        return False
    return bool(_PROVIDER_STATUS.search(error)) or any(
        m in error for m in _PROVIDER_EXC)


def _say(log: list, line: str) -> None:
    stamped = f"[{time.strftime('%H:%M:%S')}] {line}"
    log.append(stamped)
    print(stamped, flush=True)


def run_with_retry(member: str, instructions: str, out_dir: Path, filename: str,
                   budget: dict, read_roots: list, context_files: list,
                   retries: int, log: list, status: Optional[Status] = None) -> dict:
    """COLD attempts (up to retries+1) are fresh submissions, the failure
    quoted back each time - crew/campaign.py's "previous attempt failed these
    checks" pattern. A WARM retry is the identical submission tried again
    because the connection itself never answered; it costs no cold attempt
    and needs no history, since nothing was judged. Naming matches
    crew/ahkrun.py's sandbox cold-boot/warm-boot retry."""
    text = instructions
    brief = None
    provider_errors = 0
    cold = 0
    if status:
        status.member(member, file=filename, state="working", attempt=0)
    while cold < retries + 1:
        cold += 1
        if status:
            status.member(member, state="working", attempt=cold, since=_now())
        started = time.time()
        try:
            brief = submit_digest(member, text, out_dir, filename, budget,
                                  read_roots, context_files)
        except Exception as exc:                              # noqa: BLE001
            brief = {"status": "error", "passed_gates": False,
                     "error": f"{type(exc).__name__}: {exc}"[:300]}
        seconds = round(time.time() - started, 1)
        if _is_provider_error(brief):
            provider_errors += 1
            cold -= 1                       # a warm retry is not a cold attempt
            _say(log, f"{out_dir.name}/{filename}: {member}'s connection "
                     f"failed ({provider_errors}/{PROVIDER_ERROR_LIMIT}) after "
                     f"{seconds}s - {str(brief.get('error'))[:160]}")
            if provider_errors >= PROVIDER_ERROR_LIMIT:
                _say(log, f"{out_dir.name}/{filename}: giving up on {member} - "
                         f"its connection failed {provider_errors} times in a "
                         f"row; that is its link, not its work")
                if status:
                    status.member(member, state="connection_failed")
                return brief
            wait = PROVIDER_BACKOFF_S * provider_errors
            _say(log, f"{out_dir.name}/{filename}: warm retry for {member} in "
                     f"{wait}s (still running, not stuck)")
            if status:
                status.member(member, state="warm_retry_wait",
                             wait_seconds=wait, connection_failures=provider_errors)
            time.sleep(wait)
            continue
        provider_errors = 0
        ok = bool(brief.get("passed_gates"))
        _say(log, f"{out_dir.name}/{filename} cold attempt {cold}: "
                 f"{'accepted' if ok else 'failed'} in {seconds}s, "
                 f"{brief.get('requests')} requests"
                 + ("" if ok else f" - {str(brief.get('failed_gates') or brief.get('error'))[:200]}"))
        if status:
            status.member(member, state="accepted" if ok else "gate_failed",
                          requests=brief.get("requests"), tokens=brief.get("tokens"))
        if ok or cold == retries + 1:
            return brief
        text = instructions + _history(brief.get("failed_gates") or [brief.get("error")])
    return brief


def stage_parallel(members: list, task_fn) -> dict:
    """task_fn(member) -> brief. Runs every member's job in its own thread -
    different members are usually different models, and Synthetic allows one
    concurrent request per model, so this is genuinely parallel wall-clock."""
    results: dict = {}

    def go(m):
        results[m] = task_fn(m)

    threads = [threading.Thread(target=go, args=(m,)) for m in members]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def ask_kimi(prompt: str, run_name: str) -> str:
    """Call the crew's senior_fallback directly - the same provider path
    crew/campaign.py uses for a senior escalation, without needing a live
    Crush session. Raises on failure; the caller decides what a missing
    senior means for the run."""
    import os
    sys.path.insert(0, str(REPO_ROOT / "v3-service"))
    from providers.telemetry import context as telemetry_context
    from stages.llm_client import chat_completion
    from providers.registry import resolve_alias
    system = ("You are Kimi, acting as the unifying senior reviewer for a crew "
              "swarm's own planning output. Two crew members each surveyed the "
              "same dormant project and each drafted an extraction backlog from "
              "what they found. Read all of it and write ONE unified backlog: "
              "merge duplicates, resolve contradictions by saying which side you "
              "believe and why, drop anything neither digest actually grounds, "
              "and flag anything that looks fabricated or unsupported. This "
              "unified report is what a human senior reads next to decide what "
              "becomes real work - be blunt about weaknesses, do not smooth them "
              "over. If any plan you were given includes a cut_list (a keep/cut "
              "verdict per file or folder, for an archiving pass), merge those "
              "too: resolve any keep/cut disagreement the same evidence-based "
              "way as a backlog disagreement, and default to \"keep\" when the "
              "inputs genuinely disagree or the evidence is thin - a wrongly "
              "kept file costs a little disk space, a wrongly cut one is a "
              "lesson lost for good. End with one fenced ```json block: "
              '{"backlog": [{"id","title","source","target","rationale","shape",'
              '"effort"}...], "cut_list": [{"path","verdict","why"}...], '
              '"flagged": ["..."], "not_grounded": ["..."]}. Omit "cut_list" '
              "entirely if none of your inputs included one.")
    model = "Kimi"
    os.environ["ATLAS_CHAT_MODEL"] = resolve_alias(os.environ.get("ATLAS_PROVIDER"), model)
    with telemetry_context(run_id=f"archaeology:{run_name}",
                           duty="crew:archaeology_unify", role="senior",
                           persona=model, attempt=1):
        out = chat_completion("", messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=12000, timeout=900.0)
    return (out.get("content") or "").strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--folder", required=True, help="the dormant project to survey")
    ap.add_argument("--members", nargs="+", default=["Gordon", "Qwen"])
    ap.add_argument("--plan-members", nargs="+", default=None,
                    help="who drafts a plan in stage 2, if different from --members "
                         "(e.g. add Kimi to the planning seat without having it do "
                         "recon too). Defaults to whichever --members passed recon.")
    ap.add_argument("--recon-question", required=True)
    ap.add_argument("--plan-question", required=False, default=None)
    ap.add_argument("--recon-only", action="store_true",
                    help="stop after stage 1 - for surveying an ACTIVE project "
                         "for house-style lessons, where there is no plan/cut "
                         "list to draft, just raw grounded digests to gather. "
                         "A later consolidation pass reads every digest at once "
                         "instead of unifying per-project.")
    ap.add_argument("--extra-read-root", action="append", default=[],
                    help="additional read root for the PLAN stage (e.g. the "
                         "live project being compared against)")
    ap.add_argument("--max-requests", type=int, default=18)
    ap.add_argument("--max-tokens", type=int, default=150000)
    ap.add_argument("--retries", type=int, default=1,
                    help="extra attempts on a gate failure, history quoted back")
    ap.add_argument("--resume", action="store_true",
                    help="skip stage 1 and reuse recon-<member>.md files already "
                         "accepted in the output dir (for re-running plan/unify "
                         "after a bug or a question wording change, without "
                         "re-spending the recon budget)")
    args = ap.parse_args(argv)

    out_dir = Path(load_config().state_home) / "outbox" / "archaeology" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    log: list = []
    status = Status(out_dir, args.name, args.folder)
    budget = {"max_requests": args.max_requests, "max_tokens": args.max_tokens}
    if not args.recon_only and not args.plan_question:
        print("--plan-question is required unless --recon-only", file=sys.stderr)
        return 2
    recon_q = Path(args.recon_question).read_text(encoding="utf-8")
    plan_q = Path(args.plan_question).read_text(encoding="utf-8") if args.plan_question else ""
    recon_roots = [str(Path(args.folder).resolve())]
    plan_roots = recon_roots + [str(Path(r).resolve()) for r in args.extra_read_root]

    if args.resume:
        recon_briefs = {}
        for m in args.members:
            if (out_dir / f"recon-{m.lower()}.md").is_file():
                recon_briefs[m] = {"passed_gates": True, "requests": 0, "tokens": 0,
                                   "resumed": True}
            else:
                print(f"--resume: no recon-{m.lower()}.md in {out_dir}; dropping {m}",
                     flush=True)
        print(f"=== STAGE 1: skipped (--resume) - reusing {', '.join(recon_briefs)}",
             flush=True)
    else:
        print(f"=== STAGE 1: recon - {', '.join(args.members)} survey {args.folder}",
             flush=True)
        status.stage("recon")
        recon_briefs = stage_parallel(args.members, lambda m: run_with_retry(
            m, recon_q, out_dir, f"recon-{m.lower()}.md", budget, recon_roots, [],
            args.retries, log, status))
    recon_ok = {m: b for m, b in recon_briefs.items() if b.get("passed_gates")}
    if not recon_ok:
        print("no recon digest was accepted; stopping before the plan stage", flush=True)
        status.done("failed_no_recon")
        _write_summary(out_dir, args, recon_briefs, {}, None, log)
        return 1
    if args.recon_only:
        print(f"=== recon-only: {len(recon_ok)}/{len(recon_briefs)} accepted; "
              f"stopping before the plan stage", flush=True)
        status.done("complete_recon_only")
        _write_summary(out_dir, args, recon_briefs, {}, None, log)
        return 0
    recon_paths = [str(out_dir / f"recon-{m.lower()}.md") for m in recon_ok]
    plan_members = args.plan_members or list(recon_ok)

    print(f"=== STAGE 2: plan - {', '.join(plan_members)} draft a backlog from "
          f"{len(recon_paths)} digest(s)", flush=True)
    # context_files are read through THIS task's own read_roots (crew/tools.py
    # Toolbox.resolve), not the harness-wide ones - out_dir (where the recon
    # digests actually live) must be one of them or every context_file preload
    # fails as "outside this job's read roots" even though the file exists.
    plan_read_roots = plan_roots + [str(out_dir)]
    status.stage("plan")
    plan_briefs = stage_parallel(plan_members, lambda m: run_with_retry(
        m, plan_q, out_dir, f"plan-{m.lower()}.md", budget, plan_read_roots,
        recon_paths, args.retries, log, status))
    plan_ok = {m: b for m, b in plan_briefs.items() if b.get("passed_gates")}
    if not plan_ok:
        print("no plan draft was accepted; stopping before Kimi unify", flush=True)
        status.done("failed_no_plan")
        _write_summary(out_dir, args, recon_briefs, plan_briefs, None, log)
        return 1

    print("=== STAGE 3: unify - Kimi reads every digest and every plan", flush=True)
    status.stage("unify")
    parts = ["## Recon digests"]
    for m in recon_ok:
        parts.append(f"### recon-{m.lower()}.md\n\n"
                     + (out_dir / f"recon-{m.lower()}.md").read_text(encoding="utf-8"))
    parts.append("## Plan drafts")
    for m in plan_ok:
        parts.append(f"### plan-{m.lower()}.md\n\n"
                     + (out_dir / f"plan-{m.lower()}.md").read_text(encoding="utf-8"))
    unify_text, unify_error = None, None
    try:
        unify_text = ask_kimi("\n\n".join(parts), args.name)
    except Exception as exc:                                    # noqa: BLE001
        unify_error = f"{type(exc).__name__}: {exc}"
        print(f"Kimi was not reachable: {unify_error}", flush=True)
    if unify_text:
        (out_dir / "UNIFY.md").write_text(unify_text, encoding="utf-8")
        print(f"unified backlog written: {out_dir / 'UNIFY.md'}", flush=True)

    _write_summary(out_dir, args, recon_briefs, plan_briefs, unify_text, log,
                   unify_error=unify_error)
    status.done("complete" if unify_text else "complete_no_unify")
    print(f"=== done. Awaiting senior review: {out_dir}", flush=True)
    return 0


def _write_summary(out_dir: Path, args, recon_briefs: dict, plan_briefs: dict,
                   unify_text, log: list, unify_error: str = None) -> None:
    def slim(briefs):
        return {m: {"passed_gates": b.get("passed_gates"),
                    "requests": b.get("requests"), "tokens": b.get("tokens"),
                    "failed_gates": b.get("failed_gates")}
                for m, b in briefs.items()}
    summary = {"name": args.name, "folder": args.folder, "members": args.members,
              "recon": slim(recon_briefs), "plan": slim(plan_briefs),
              "unified": bool(unify_text), "unify_error": unify_error,
              "log": log}
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
