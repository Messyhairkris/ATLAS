"""The PA brief: the first prompt of every PA session, rendered from live state.

Kris, 2026-10-23: the PA may be Claude, Kimi, Qwen or Gordon, "even PAs are scoped so
when the first prompt is set all understanding of the system is easily accessed and used
when needed", and "we should write a really good prompt to inject at the start of each
conversation". Also: Crush's hooks "injected way too much information at each reply"
and burned the weekly limits. So the brief is injected ONCE per session (start, clear,
compact), has a hard size cap (personnel.json pa.brief_max_chars), and points to where
things are instead of pasting them - the way skills are listed by name and read on
demand.

Layers (CrossTalk's Three-Layer Context Injection): 1 = who the PA is, its scope and the
standing rules; 2 = the live project state (crew, work in flight, the PM's queue, last
night); 3 = the session's task, from the PM (--task, or the PM's first message).

  python crew/pa_brief.py --pa Gordon                 # print the brief
  python crew/pa_brief.py --pa Claude --hook          # Claude Code SessionStart hook JSON
  python crew/pa_brief.py --pa Kimi --write FILE      # the agent prompt for OpenCode
"""

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HOME = Path.home()
SKILL_DIRS = [HOME / ".claude" / "skills", REPO / ".claude" / "skills"]
CRUSH_SKILLS = HOME / ".crush" / "skills"
VAULT = HOME / "Documents" / "Obsidian" / "Knowledge_Base"
THE_CREW = HOME / "TheCrew"

RULES = [
    "This machine is Windows 10 and PowerShell is the default shell: no Unix commands "
    "(ls -la, rm -rf, head, grep, which, touch). Full Windows paths in everything you "
    "write for the PM.",
    "When the PM asks for a change, it is decided: build it, verify it (tests, gates), "
    "commit it on the working branch and summarize. Ask only when something is "
    "questionable, destructive, outside the ask, or would push/upload anything.",
    "Hand the PM a task as short numbered steps at the TOP of your reply: exact paths, "
    "one copyable command per step, what they should see. One ask per reply.",
    "Delegate bounded, checkable work to the crew. You write the contract, a reference "
    "implementation and the hidden tests, and run the reference against the tests "
    "before any request is spent. A member is never trusted; the gates decide.",
    "When a crew job fails, read its stop reason first: budget_tokens, budget_requests, "
    "output_truncated, empty_replies and thinking_cut_off are OUR ceilings, a 5xx is the "
    "provider, a test failing on an edge the contract never stated is the contract.",
    "Campaigns rework instead of restarting and relay a stuck task to the next capable "
    "member (personnel.json posts). Pick members by their measured record, not reputation.",
    "No program may look idle: long runs write a status.json (and a you_might_see note "
    "when something will appear on screen). Report what was observed, not intended.",
    "Never run AutoHotkey on the desktop (Windows Sandbox only). Run "
    "crew/runners/security_scan.py on a folder before it becomes a crew read root.",
]

# Kris 2026-10-24 (after the Antigravity study): every PA chat leaves a plan, a task list and
# a walkthrough, with a review policy. For the PAs that chat in The Crew's window; Claude
# Code PAs keep CLAUDE.md. Shapes follow Antigravity's implementation_plan / task / walkthrough.
ARTIFACTS = [
    "In The Crew's chat each message from the PM ends with a line `[The Crew] chat <id>; mode: "
    "<plan|assign>; artifacts: <folder>; review: <policy>`. Keep this chat's artifacts in that "
    "folder (writing there needs no approval); answer questions and small requests without them.",
    "mode: plan = deliberate with the PM: research, read crew state (status, roster, budget, "
    "task types, results), write and revise plan.md. Crew submissions and other edits are "
    "switched off in this mode; when the plan is ready, say so - the PM switches to Assign.",
    "mode: assign = turn the approved plan into atomic tasks (CrossTalk's AtomicTask): write "
    "tasks.json in the artifacts folder as {\"milestone\": \"...\", \"tasks\": [{\"id\": \"t1\", "
    "\"title\": \"...\", \"assigned_to\": \"<member>\", \"task_type\": \"...\", \"contract\": "
    "\"<path>\", \"depends\": [], \"context_files\": [], \"status\": \"ready\", \"job_id\": \"\"}]}. "
    "A task with unfinished dependencies is blocked, not ready. Submit only ready tasks "
    "(crew_submit, or a campaign for a batch), put each job id in its task, and keep every "
    "status current: blocked, ready, in_progress, completed, failed.",
    "Look around with your read, list, glob and grep tools: they need no approval. Shell "
    "commands ask the PM, and one the PM refuses ends your turn.",
    "plan.md, BEFORE work that changes files or spends crew requests: # Goal; ## Review "
    "required (what the PM must decide, or 'nothing'); ## Changes, grouped by component, each "
    "file marked [NEW], [MODIFY] or [DELETE]; ## Crew jobs (member, task type, contract); "
    "## Verification (tests, gates, what the PM will see). Revise the same file, never a second.",
    "Tasks: keep your todo list current with your todo tool (pending, in_progress, completed); "
    "the PM sees it live beside the chat.",
    "walkthrough.md, when the work is done: what changed (files, crew jobs and their results), "
    "what was tested and how, the results, anything left over. Update the same file for "
    "follow-ups.",
    "review: request = after writing plan.md, stop and ask the PM to review it; change no "
    "files and spend no crew requests until the PM approves. pa = you decide: ask only when the "
    "plan is risky, costly or unclear. proceed = go ahead; the PM reads the plan when they like.",
]

WHERE = [
    ("How the crew works, every tool", REPO / "crew" / "README.md"),
    ("The playbook for delegating (contracts, gates, roster, cost)",
     HOME / ".claude" / "skills" / "crew-tasking" / "SKILL.md"),
    ("Members, posts, budgets, PA scopes", REPO / "crew" / "personnel.json"),
    ("Measured record per member", REPO / "crew" / "PERSONNEL.md"),
    ("Contracts and house styles", REPO / "crew" / "contracts"),
    ("Campaign files", REPO / "crew" / "campaigns"),
    ("Live state: campaigns, jobs, night reports", REPO / "runs" / "crew"),
    ("A new language for the crew", REPO / "crew" / "HARNESS_BUILDING.md"),
    ("The Crew (Rust control room, guard hook)", THE_CREW),
    ("CrossTalk design (vault)", VAULT / "wiki" / "concepts" / "CrossTalk MOC.md"),
    ("The Crew research and decisions",
     VAULT / "wiki" / "research" / "crew-swarm-tools-2026-10-23.md"),
]

COMMANDS = [
    ("plan / run a campaign", "python -m crew campaign plan|run crew/campaigns/<x>.json"),
    ("each member's record", "python crew/runners/member_stats.py"),
    ("everything running now", "python crew/runners/active_status.py"),
    ("accepted modules vs hidden tests", "python crew/runners/check_accepted.py"),
    ("do tests catch seeded bugs", "python crew/runners/mutants.py --module m.py"),
    ("the night report, now", "python crew/runners/night_shift.py"),
    ("what waits on the PM", "python crew/runners/pm_queue.py status"),
    ("provider quota", "python -m crew budget"),
]


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _first_sentence(text: str, limit: int = 110) -> str:
    """At most `limit` characters, ending at a sentence break when one falls late
    enough to keep the line informative ("vision 3/3." alone says too little)."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text.rfind(". ", 0, limit)
    if cut >= limit // 2:
        return text[:cut + 1]
    return text[:limit - 3].rstrip() + "..."


def _skill_line(path: Path) -> Optional[str]:
    """'name - description' from a SKILL.md's frontmatter, or None."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    meta: Dict[str, str] = {}
    for line in text.split("\n")[1:40]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        if key.strip() in ("name", "description") and value.strip():
            meta[key.strip()] = value.strip().strip("'\"")
    if "name" not in meta:
        return None
    return f"{meta['name']} - {_first_sentence(meta.get('description', ''), 100)}"


def skills() -> List[str]:
    lines, seen = [], set()
    for folder in SKILL_DIRS:
        for skill in sorted(folder.glob("*/SKILL.md")):
            line = _skill_line(skill)
            if line and line.split(" - ")[0] not in seen:
                seen.add(line.split(" - ")[0])
                lines.append(f"- {line} ({skill})")
    return lines


def roster(staff: dict) -> List[str]:
    rows = ["| member | model | posts | measured |", "|---|---|---|---|"]
    for name, m in (staff.get("members") or {}).items():
        rows.append(f"| {name} | {str(m.get('model', '')).split('/')[-1]} | "
                    f"{', '.join(m.get('posts') or []) or '-'} | "
                    f"{_first_sentence(m.get('measured', ''))} |")
    return rows


def work_in_flight(state: Path, hours: int = 48) -> List[str]:
    out = []
    cutoff = dt.datetime.now().timestamp() - hours * 3600
    for path in sorted((state / "campaigns").glob("*/status.json")):
        try:
            if path.stat().st_mtime < cutoff or (path.parent / "summary.json").exists():
                continue
        except OSError:
            continue
        status = _read_json(path) or {}
        counts = status.get("counts") or {}
        running = [f"{t}: {v.get('member')}" for t, v in (status.get("tasks") or {}).items()
                   if v.get("state") == "running"]
        out.append(f"- campaign {status.get('campaign') or path.parent.name}: "
                   f"{counts.get('accepted', 0)} accepted, {counts.get('failed', 0)} failed, "
                   f"{counts.get('waiting', 0)} waiting"
                   + (f"; running {', '.join(running)}" if running else ""))
    return out or ["- (no open campaigns)"]


def pm_queue(limit: int = 6) -> List[str]:
    try:
        sys.path.insert(0, str(REPO / "crew" / "runners"))
        import review_desk as rd
        items = [i for i in rd.load_queue() if i.get("state") == "pending"]
    except Exception:                                       # noqa: BLE001
        return ["- (the Review Desk queue could not be read)"]
    lines = [f"- {i.get('title', '?')}" for i in items[:limit]]
    if len(items) > limit:
        lines.append(f"- ... and {len(items) - limit} more "
                     f"(python crew/runners/pm_queue.py status)")
    return lines or ["- (nothing is waiting on the PM)"]


def last_night(state: Path) -> List[str]:
    data = None
    for path in sorted((state / "night").glob("night-*.json"))[-1:]:
        data = _read_json(path)
    if not data:
        return ["- (no night report yet)"]
    lines = [f"- {data.get('generated', '?')[:16]}: {data.get('headline', '')}",
             f"- report: {state / 'night' / 'NIGHT_REPORT.md'}"]
    for g in [g for g in data.get("groups") or [] if g.get("candidate")][:4]:
        lines.append(f"- fixer candidate: {g['signature']} ({g['count']}x)")
    return lines


def recent_commits(repo: Path, n: int = 4) -> List[str]:
    if not (repo / ".git").exists():
        return []
    try:
        done = subprocess.run(["git", "-C", str(repo), "log", "--oneline", f"-{n}"],
                              capture_output=True, text=True, timeout=20,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        branch = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"],
                                capture_output=True, text=True, timeout=20,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return []
    head = f"- {repo} (branch {branch.stdout.strip() or '?'}):"
    return [head] + [f"  - {line}" for line in done.stdout.strip().splitlines()]


def scope_lines(pa: str, cfg: dict) -> List[str]:
    scope = (cfg.get("scopes") or {}).get(pa) or {}
    common = cfg.get("common") or {}
    lines = [f"- Runtime: {scope.get('runtime', '?')}; model: {scope.get('model', '?')}"
             + (f"; up to {scope['steps']} steps per message" if scope.get("steps") else "")]
    if scope.get("notes"):
        lines.append(f"- About you: {scope['notes']}")
    lines += ["- You may: " + "; ".join(common.get("may") or [])]
    lines += ["- You may NOT: " + "; ".join(common.get("may_not") or [])]
    others = [p for p in cfg.get("approved") or [] if p != pa]
    if others:
        lines.append(f"- Other approved PAs: {', '.join(others)}. Only the PM promotes or "
                     f"demotes a PA.")
    return lines


def render(pa: str, task: str = "", staff: Optional[dict] = None,
           state: Optional[Path] = None, now: Optional[dt.datetime] = None) -> str:
    """The brief for `pa`, within the size cap. Raises ValueError for an unapproved PA."""
    from crew import personnel
    staff = staff if staff is not None else personnel.load()
    cfg = staff.get("pa") or {}
    if pa not in (cfg.get("approved") or []):
        raise ValueError(f"{pa} is not an approved PA (approved: "
                         f"{', '.join(cfg.get('approved') or []) or 'none'}); "
                         f"only the PM promotes one: python -m crew pa promote {pa} --by Kris")
    if state is None:
        from crew.config import load_config
        state = Path(load_config().state_home)
    now = now or dt.datetime.now()
    runtime = ((cfg.get("scopes") or {}).get(pa) or {}).get("runtime")
    cap = int(cfg.get("brief_max_chars") or 14000)

    head = [f"# PA brief - The Crew - {now:%Y-%m-%d %H:%M}", "",
            f"You are {pa}, the Project Assistant (PA). Kris is the Project Manager (PM): the "
            f"PM owns every decision, you execute and keep the work moving. You plan the path "
            f"with the PM, assign the crew by measured ability, check results with gates "
            f"they cannot fake, and report back. This brief is given ONCE per session; open "
            f"the files below when a task needs them instead of guessing.", "",
            "## Your scope", *scope_lines(pa, cfg), ""]
    if runtime == "claude-code":
        rules = ["## Standing rules",
                 "- Your CLAUDE.md and project memory carry the standing rules; they are "
                 "already loaded, so they are not repeated here.", ""]
    else:
        rules = ["## Standing rules", *[f"- {r}" for r in RULES], "",
                 "## Plan, tasks, walkthrough (The Crew's chat)", *[f"- {r}" for r in ARTIFACTS], ""]
    live = (["## The crew (personnel.json; measured outranks reputation)", *roster(staff), "",
             "## Work in flight", *work_in_flight(state), "",
             "## Waiting on the PM (Review Desk)", *pm_queue(), "",
             "## Last night", *last_night(state), "",
             "## Recent commits", *recent_commits(REPO), *recent_commits(THE_CREW), ""])
    where = (["## Where things are (read when needed)"]
             + [f"- {what}: {path}" for what, path in WHERE]
             + ["", "Commands (PowerShell, from C:\\Users\\user\\ATLAS-api-harness):"]
             + [f"- {what}: `{cmd}`" for what, cmd in COMMANDS] + [""])
    crush = sorted(p.name for p in CRUSH_SKILLS.glob("*/") if (p / "SKILL.md").is_file())
    skill_part = (["## Skills (open a SKILL.md when a task matches it)", *skills()]
                  + ([f"- Crush's {len(crush)} skills, by name, in {CRUSH_SKILLS}: "
                      + ", ".join(crush)] if crush else []) + [""])
    tail = (["## This session's task", task.strip(), ""] if task.strip() else
            ["## This session's task", "- The PM's first message sets it.", ""])

    parts = [head, rules, live, where, skill_part, tail]
    text = "\n".join(line for part in parts for line in part)
    if len(text) > cap:
        # drop the lowest-priority detail first: the skills list, then the roster's notes
        parts[4] = ["## Skills", f"- Listed in {SKILL_DIRS[0]} and {CRUSH_SKILLS} "
                    f"(cut to keep this brief under {cap} characters).", ""]
        text = "\n".join(line for part in parts for line in part)
    if len(text) > cap:
        text = text[:cap - 80].rstrip() + f"\n\n(brief cut at {cap} characters)"
    return text


def hook_json(brief: str) -> str:
    """Claude Code SessionStart output: the brief as additional context, once."""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": brief}})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--pa", default=None, help="the PA (default: personnel.json pa.default)")
    ap.add_argument("--task", default="", help="layer 3: this session's task")
    ap.add_argument("--hook", action="store_true", help="print Claude Code SessionStart JSON")
    ap.add_argument("--write", help="write the brief to this file instead of printing it")
    args = ap.parse_args(argv)
    from crew import personnel
    staff = personnel.load()
    pa = args.pa or (staff.get("pa") or {}).get("default") or "Claude"
    try:
        brief = render(pa, args.task, staff)
    except Exception as e:                                  # noqa: BLE001
        if args.hook:        # a broken brief must never stop a session from starting
            print(hook_json(f"(The PA brief could not be built: {type(e).__name__}: {e})"))
            return 0
        raise
    if args.hook:
        print(hook_json(brief))
    elif args.write:
        Path(args.write).write_text(brief, encoding="utf-8")
        print(f"wrote {len(brief)} characters to {args.write}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(brief)
    return 0


if __name__ == "__main__":
    sys.exit(main())
