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
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from . import mcp_catalog, playbook, task_types
from .config import CrewError, REPO_ROOT, load_config
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
    """Status of one task; with task_id empty, the open tasks plus at most 30
    needing attention from the last two days, newest first (older ones are only
    counted). wait_seconds (max 50) long-polls until the task leaves
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
      number, in notes and the job re-runs with it), unapprove (undo an approval:
      overwritten files come back from the job's backup, created ones move into the
      job folder; refused if a file was edited since), reject, or acknowledge (clear
      an auto-applied notice).
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


def _engine_http(method: str, url: str, timeout: float = 30.0) -> dict:
    """One call to The Crew engine's own HTTP API. Tests monkeypatch this, so no test opens a
    socket; the machine is offline while the suite runs."""
    request = urllib.request.Request(url, data=(b"" if method == "POST" else None),
                                     method=method)
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        text = answer.read().decode("utf-8", errors="replace")
    return json.loads(text) if text.strip() else {}


def _project_dir() -> str:
    """The chat's or build's project directory, for the engine's `directory` query parameter:
    the engine can hold several projects, so it needs to be told which one (Gordon, 2026-10-29).
    The crew MCP is started inside that project, so its own working directory is it."""
    return os.getcwd()


def _mcp_log(action: str, name: str, reason: str, decision: str) -> None:
    """One JSON line per crew_mcp call, in the crew's state home (runs/crew/mcp_switch.jsonl):
    who switched what, why, and what the catalogue decided."""
    try:
        home = Path(load_config().state_home)
    except (OSError, ValueError):
        home = REPO_ROOT / "runs" / "crew"
    home.mkdir(parents=True, exist_ok=True)
    line = {"ts": datetime.now().isoformat(timespec="seconds"), "client": CLIENT,
            "action": action, "name": name, "reason": reason, "decision": decision}
    with open(home / "mcp_switch.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _mcp_on(data: dict, name: str) -> bool:
    """Whether the engine's GET /mcp says this server is on. The shape is the engine's: a list of
    {"name", "status"/"connected"} or a dict keyed by name (or {"servers": ...})."""
    items = data.get("servers", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        entry = items.get(name)
        return isinstance(entry, dict) and bool(
            entry.get("connected") or entry.get("enabled")
            or entry.get("status") in ("connected", "ready", "on"))
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("name") == name:
                return bool(item.get("connected") or item.get("enabled")
                            or item.get("status") in ("connected", "ready", "on"))
    return False


def _mcp_refused(catalog: dict, name: str, decision: str) -> str:
    """The plain sentence crew_mcp returns when the catalogue will not let it switch a server on:
    a PA never switches it on without Kris, and here is why."""
    klass, why = mcp_catalog.klass(catalog, name), mcp_catalog.why(catalog, name)
    if decision == "deny":
        return (f"{name} is classed '{klass}' in the MCP catalogue: Kris does not allow it, so it "
                f"stays off. Why: {why}")
    return (f"{name} is classed '{klass}' in the MCP catalogue: Kris must approve switching it on "
            f"in this chat. Why: {why}")


@mcp.tool()
def crew_mcp(action: str, name: str = "", reason: str = "") -> str:
    """List the extra MCP servers a PA may switch on, or switch one on or off from chat.

    The catalogue (crew/mcp_catalog.json, which Kris edits) decides: read servers switch on
    freely, local_act once per chat, account only with Kris's approval, and never ones never.
    action: list | on | off. name: a catalogue name (e.g. arxiv, godot_mcp, github). reason: one
    line on why, kept in runs/crew/mcp_switch.jsonl with the decision. Switching needs The
    Crew's engine; in Claude's chat (no CREW_ENGINE_URL) this only says so."""
    base = os.environ.get("CREW_ENGINE_URL", "").rstrip("/")
    if not base:
        return "switching needs The Crew's engine"
    catalog = mcp_catalog.load()
    directory = quote(_project_dir())
    if action == "list":
        data = _engine_http("GET", f"{base}/mcp?directory={directory}")
        listing = [{"name": e.get("from"), "class": e.get("class"),
                    "on": _mcp_on(data, e.get("from"))}
                   for e in catalog.get("servers") or []]
        _mcp_log(action, name, reason, "list")
        return _ok(listing)
    if action not in ("on", "off"):
        return _err(ValueError(f"action {action!r} is not list, on or off"))
    decision = mcp_catalog.decide(catalog, name, action)
    _mcp_log(action, name, reason, decision)
    if decision != "allow":
        return _mcp_refused(catalog, name, decision)
    url = (f"{base}/mcp/{quote(name)}/"
           f"{'connect' if action == 'on' else 'disconnect'}?directory={directory}")
    return _ok({"action": action, "name": name, "decision": decision,
                "engine": _engine_http("POST", url)})


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
