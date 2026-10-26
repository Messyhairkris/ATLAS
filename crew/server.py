"""The Crew MCP server (stdio).

Architects (Claude Code, Crush, any MCP client) submit tasks; the server's
background worker has a crew member (Hoss by default) work them with
read-only tools; the architect reviews. Several server processes (one per
client) share the same queue on this machine; claims decide who runs what.

Register:
  Claude Code: .mcp.json at the repo root (committed alongside this file).
  Crush (Windows): crush.json "mcp" entry through mcp_stdio_wrapper.py (see
  crew/README.md) — Crush's non-overlapped pipes break FastMCP's stdin.
"""

import io
import json
import os
import sys
from typing import List, Optional

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from . import playbook, task_types
from .config import CrewError
from .core import Crew

INSTRUCTIONS = """The Crew: a work queue of cheap roster models (Hoss = gpt-oss-120b by default) that do bounded, checkable work with READ-ONLY tools while you architect and review.

Workflow: crew_task_types -> crew_submit (one atomic task per call; split big asks) -> crew_status(task_id, wait_seconds=45) until it leaves ready/in_progress -> crew_result -> crew_review (approve | revise with a retry_constraint | reject; add playbook_add lessons so the next run starts smarter).
Output is staged and only written to the workspace when approved, or automatically once Kris has promoted that member+task type to Supervised/Autonomous. You cannot change autonomy stages from here.
Good tasks: indexing a vault folder, a cited research digest from workspace files, an organize plan, triaging a project's own test run (the harness runs the suite; the member explains the failures). Bad tasks: anything that needs writing code, or judgment the gates cannot check."""

mcp = FastMCP("crew", instructions=INSTRUCTIONS)
_crew: Optional[Crew] = None
CLIENT = os.environ.get("CREW_CLIENT", "mcp-client")


def crew() -> Crew:
    global _crew
    if _crew is None:
        _crew = Crew()
    return _crew


def _ok(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _err(e: Exception) -> str:
    return _ok({"error": str(e)})


@mcp.tool()
def crew_task_types() -> str:
    """List the task types the crew accepts: required spec fields, the automatic
    gates each output must pass, what approval does, and playbook size."""
    cat = task_types.public_catalog()
    for c in cat:
        c["playbook_entries"] = len(playbook.entries(c["task_type"]))
    return _ok(cat)


@mcp.tool()
def crew_submit(task_type: str, title: str, instructions: str = "",
                folder: str = "", project_root: str = "", test_command: str = "",
                app: str = "", watch_log: str = "", assigned_to: str = "",
                context_files: Optional[List[str]] = None,
                read_roots: Optional[List[str]] = None,
                output_root: str = "", output_file: str = "",
                must_mention: Optional[List[str]] = None,
                must_read: Optional[List[str]] = None,
                dependencies: Optional[List[str]] = None,
                log_file: str = "", claim: str = "",
                expected: Optional[List[dict]] = None, lsp: bool = False,
                max_requests: int = 0, submitted_by: str = "") -> str:
    """Submit ONE atomic task. Returns its task_id and status (ready, or blocked
    until dependencies complete).

    task_type: vault_index | research_digest | organize_plan | test_triage |
      ui_sweep | scout | log_clerk | completion_audit (see crew_task_types).
    log_file: for log_clerk - the log to report on.
    claim / expected: for completion_audit - the work claimed complete, and
      [{artifact, path?}, ...]; read_roots names the project.
    lsp: give the member language-server tools (symbols, definition,
      references, diagnostics) - see config.json "lsp".
    folder: required for vault_index and organize_plan (absolute path).
    app / watch_log: for ui_sweep - the .exe the harness drives (each control
      highlighted orange for half a second, then pressed) and the app log it
      watches for errors.
    project_root / test_command: for test_triage — the project whose own test
      suite the HARNESS runs (the member never chooses a command).
    instructions: the ask; required for research_digest.
    assigned_to: crew member nickname (default Hoss).
    context_files: files to preload so the member spends fewer requests.
    output_root/output_file: where an approved research_digest lands (must be a
      crew write root; default runs/crew/outbox). output_file also names a
      vault_index file (default INDEX.md).
    must_mention: terms the output must contain (extra acceptance gate).
    must_read: files the member must open itself before its output passes.
    max_requests: model-request budget (default 12).
    submitted_by: your name, e.g. Claude or Crush (goes into the action log)."""
    spec = {"task_type": task_type, "title": title, "instructions": instructions}
    if folder:
        spec["folder"] = folder
    if project_root:
        spec["project_root"] = project_root
    if app:
        spec["app"] = app
    if watch_log:
        spec["watch_log"] = watch_log
    if test_command:
        spec["test_command"] = test_command
    if assigned_to:
        spec["assigned_to"] = assigned_to
    if context_files:
        spec["context_files"] = context_files
    if read_roots:
        spec["read_roots"] = read_roots
    if task_type == "vault_index" and output_file:
        spec["output_file"] = output_file
    elif output_root or output_file:
        spec["output"] = {"root": output_root or None,
                          "files": [output_file] if output_file else None}
    if must_mention or must_read:
        spec["acceptance"] = {k: v for k, v in (("must_mention", must_mention),
                                                ("must_read", must_read)) if v}
    if dependencies:
        spec["dependencies"] = dependencies
    if log_file:
        spec["log_file"] = log_file
    if claim:
        spec["claim"] = claim
    if expected:
        spec["expected"] = expected
    if lsp:
        spec["lsp"] = True
    if max_requests:
        spec["budget"] = {"max_requests": max_requests}
    try:
        return _ok(crew().submit(spec, submitted_by or CLIENT))
    except (CrewError, Exception) as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def crew_status(task_id: str = "", wait_seconds: int = 0) -> str:
    """Status of one task, or of all open/attention-needing tasks when task_id
    is empty. wait_seconds (max 50) long-polls until the task leaves
    ready/in_progress, saving you repeated calls."""
    try:
        return _ok(crew().status(task_id or None, wait_seconds))
    except (CrewError, Exception) as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def crew_result(task_id: str) -> str:
    """Full result: staged output text, every gate result, files the member
    actually read, its proposed playbook lessons, budget used, reviews."""
    try:
        return _ok(crew().result(task_id))
    except (CrewError, Exception) as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def crew_review(task_id: str, decision: str, reviewer: str, notes: str = "",
                retry_constraint: str = "",
                playbook_add: Optional[List[str]] = None,
                accept_member_notes: bool = False,
                must_read: Optional[List[str]] = None,
                ascii_only: bool = False) -> str:
    """Review a task.
    decision: approve (review-state only; writes the staged output to its
      target), revise (re-queue with retry_constraint = what to do differently;
      the member sees it verbatim), answer (a stuck member asked ONE question -
      crew_status shows it under "question"; put the answer, or an option's
      number, in notes and the job re-runs with it), reject, or acknowledge
      (clear an auto-applied notice).
    must_read / ascii_only (revise only): make your constraint ENFORCEABLE —
      the next submission fails unless the member actually opened each
      must_read file (paths relative to the task's read root) / wrote plain
      ASCII. Small models skip instructions; they cannot skip gates.
    playbook_add: one-line lessons appended to this task type's playbook, so
      every future run starts with them (near-duplicates are skipped).
    accept_member_notes: also adopt the lessons the member proposed."""
    try:
        return _ok(crew().review(task_id, decision, reviewer, notes, retry_constraint,
                                 playbook_add, accept_member_notes,
                                 must_read, ascii_only))
    except (CrewError, Exception) as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def crew_inbox() -> str:
    """Everything waiting on a reviewer: questions a stuck member asked (answer
    them with crew_review decision "answer", or put them on Kris's Review Desk),
    outputs in review, failed tasks (revise or reject them), and auto-applied
    notices to acknowledge."""
    return _ok(crew().inbox())


@mcp.tool()
def crew_roster() -> str:
    """Crew members' performance per task type (pass rates, median requests
    and tokens, reviews) with their Autonomy Stage and any promotion
    suggestion. Promotion itself is Kris-only, via the CLI."""
    return _ok(crew().roster.summary())


@mcp.tool()
def crew_budget() -> str:
    """Provider request budget for the rolling window: how many requests the
    crew has used and has left. Check this before queueing a campaign; the
    worker also holds jobs by itself when the window is full."""
    return _ok(crew().rate.report())


@mcp.tool()
def crew_playbook(task_type: str) -> str:
    """Show the retained playbook a crew member receives for a task type."""
    try:
        return playbook.load(task_type)
    except (CrewError, Exception) as e:  # noqa: BLE001
        return _err(e)


def main() -> None:
    # The MCP transport owns the real stdout; anything else that prints goes
    # to stderr so it can never corrupt the protocol stream.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    c = crew()
    if os.environ.get("CREW_WORKER", "1") != "0":
        c.start_worker()

    async def serve():
        out = anyio.wrap_file(io.TextIOWrapper(real_stdout.buffer, encoding="utf-8"))
        async with stdio_server(stdout=out) as (read, write):
            await mcp._mcp_server.run(read, write,
                                      mcp._mcp_server.create_initialization_options())

    try:
        anyio.run(serve)
    finally:
        c.stop()


if __name__ == "__main__":
    main()
