"""Hand a chat in The Crew's window to another PA (or model) with a summary, not the transcript.

Kris, 2026-10-25: "when I want to switch to a new model, a separate action is run before the
user request that summarizes the conversation and goals of the project so far. another PA
specific prompt injection should be prepared ... a new prompt that explains it continuing to
work on this project, here is the summery, then the user request. This will hopefully lesson
the need to load the whole conversation to catch a new Model up to speed."

A switch of model re-reads the whole conversation from scratch (no cache carries across
models), so the new PA gets this instead:

    python crew/runners/pa_handoff.py --dir <artifacts>/handoff --n 1 --from Claude --to Gordon \
        [--title "..."] [--member Gordon]

The window writes `conversation-<n>.md` (what was said, tool calls on one line) and
`request-<n>.txt` (the PM's new message) into --dir first. This writes `summary-<n>.md` (one
request to the summarizer, personnel.json pa.handoff_summarizer, Gordon by default; a summary
built without a model if that call fails) and `prompt-<n>.md` - crew/pa_brief.py continuation():
who the new PA is, that it is continuing, the summary, then the request - and prints one JSON
answer: {"ok", "summary", "prompt_file", "prompt", "model", "fallback", "error"}.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from crew import pa_brief, personnel  # noqa: E402

# What the summarizer reads: the start (the goal) and the end (where it stands) of a long chat.
KEEP_HEAD, KEEP_TAIL = 20_000, 160_000
SECTIONS = ["The goal", "Decisions made", "Where the work stands", "Open items and next steps",
            "Problems, failures and warnings", "Waiting on the PM"]

SYSTEM = ("You write handoff summaries between Project Assistants (PAs) of The Crew, a small team "
          "of AI models that does bounded work for Kris, the Project Manager (PM). The next PA "
          "will NOT see the conversation: your summary is all it gets. Be exact and brief. Quote "
          "the PM's own words for goals and decisions. Copy ids, paths, numbers and statuses "
          "exactly as they appear; never invent one. Write facts, not advice.")


def cut_middle(text: str, head: int = KEEP_HEAD, tail: int = KEEP_TAIL) -> str:
    if len(text) <= head + tail:
        return text
    gone = len(text) - head - tail
    return f"{text[:head]}\n\n(... {gone} characters of the middle cut ...)\n\n{text[-tail:]}"


def _job_status(state: Path, job_id: str) -> str:
    try:
        return json.loads((state / "jobs" / job_id / "job.json").read_text(encoding="utf-8")).get("status", "?")
    except (OSError, ValueError):
        return "not found"


def artifacts_digest(artifacts: Path, state: Optional[Path]) -> str:
    """The chat's own files: the plan (head), the atomic tasks with each crew job's live status,
    the walkthrough (head), and the rest by name."""
    out: List[str] = []
    for name, limit in (("plan.md", 12_000), ("walkthrough.md", 6_000)):
        p = artifacts / name
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            more = f"\n(... {len(text) - limit} more characters in {p})" if len(text) > limit else ""
            out += [f"### {name}", text[:limit] + more, ""]
    tasks = artifacts / "tasks.json"
    if tasks.is_file():
        try:
            data = json.loads(tasks.read_text(encoding="utf-8"))
            rows = data.get("tasks") or data.get("jobs") or []
            out += [f"### tasks.json - {data.get('milestone', '')}",
                    "| id | title | member | task status | crew job | job status now |", "|---|---|---|---|---|---|"]
            for t in rows:
                job = t.get("job_id") or ""
                live = _job_status(state, job) if (job and state) else ""
                out.append(f"| {t.get('id', '')} | {t.get('title', '')} | {t.get('assigned_to', '')} | "
                           f"{t.get('status', '')} | {job} | {live} |")
            out.append("")
        except ValueError as e:
            out += [f"### tasks.json could not be read: {e}", ""]
    others = sorted(p.relative_to(artifacts).as_posix() for p in artifacts.rglob("*")
                    if p.is_file() and p.name not in ("plan.md", "walkthrough.md", "tasks.json")
                    and "handoff" not in p.relative_to(artifacts).parts)
    if others:
        out += ["### Other files in the artifacts folder", *[f"- {o}" for o in others[:60]], ""]
    return "\n".join(out) if out else "(the artifacts folder is empty)"


def summary_request(title: str, from_pa: str, to_pa: str, conversation: str, digest: str) -> str:
    heads = "\n".join(f"## {s}" for s in SECTIONS)
    return (f"Write the handoff summary for the chat \"{title}\": {from_pa} has been the PA, "
            f"{to_pa} takes over next.\n\nUse exactly these sections, in this order, as Markdown:\n"
            f"# Handoff - {title}\n{heads}\n\nUnder 900 words. 'Where the work stands' names every "
            f"artifact and crew job with its id and its live status from the table below. "
            f"'Waiting on the PM' lists questions or approvals the PM has not answered yet "
            f"('nothing' if none).\n\n--- THE CONVERSATION ---\n{cut_middle(conversation)}\n\n"
            f"--- THE CHAT'S ARTIFACTS (live) ---\n{digest}\n")


def fallback_summary(title: str, conversation: str, digest: str, error: str) -> str:
    """Built without a model, when the summarizer cannot be reached: the PM's first and last
    words, the PA's last reply, and the artifacts as they stand."""
    turns = [t for t in conversation.split("\n### ") if t.strip()]
    pm = [t for t in turns if t.lstrip("# ").startswith("You")]
    pa = [t for t in turns if not t.lstrip("# ").startswith("You")]
    first = pm[0].split("\n", 1)[-1].strip()[:3000] if pm else "(none)"
    last_pm = [t.split("\n", 1)[-1].strip()[:1500] for t in pm[-3:]] if pm else []
    last_pa = pa[-1].split("\n", 1)[-1].strip()[:3000] if pa else "(none)"
    return "\n".join([
        f"# Handoff - {title}",
        f"(Written without a model - the summarizer failed: {error}. These are the PM's own first "
        f"and latest messages, the PA's last reply, and the artifacts as they stand.)", "",
        "## The goal (the PM's first message)", first, "",
        "## The PM's latest messages", *[f"- {m}" for m in last_pm], "",
        "## The last reply of the previous PA", last_pa, "",
        "## Where the work stands", digest,
    ])


def harness_chat(member: str) -> Callable[[List[dict]], dict]:
    """One request to a crew member's model through the harness (its provider, ledger and
    per-model slot), as crew jobs make them."""
    staff = personnel.load()
    model = personnel.member(staff, member).get("model")
    if not model:
        raise ValueError(f"{member} has no model in personnel.json")
    from crew import core
    from crew.config import REPO_ROOT, load_config
    core._env_setup(load_config())
    sys.path.insert(0, str(REPO_ROOT / "v3-service"))
    from providers.telemetry import context as telemetry_context
    from stages.llm_client import chat_completion

    def chat(messages: List[dict]) -> dict:
        os.environ["ATLAS_CHAT_MODEL"] = model
        with core._ModelSlot(model, lambda: None), telemetry_context(
                run_id="pa-handoff", duty="pa:handoff", task_id="pa-handoff", role="senior",
                persona=member, attempt=1):
            out = chat_completion("", messages=messages, temperature=0.2, max_tokens=4096, timeout=600.0)
        out["model"] = model
        return out
    return chat


def handoff(folder: Path, n: int, from_pa: str, to_pa: str, title: str, member: str,
            state: Optional[Path], chat: Optional[Callable[[List[dict]], dict]] = None) -> dict:
    conversation = (folder / f"conversation-{n}.md").read_text(encoding="utf-8")
    request = (folder / f"request-{n}.txt").read_text(encoding="utf-8")
    artifacts = folder.parent
    digest = artifacts_digest(artifacts, state)
    used, error, fallback, tokens = member, "", False, {}
    try:
        call = chat or harness_chat(member)
        out = call([{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": summary_request(title, from_pa, to_pa, conversation, digest)}])
        summary = (out.get("content") or "").strip()
        used = f"{member} ({out.get('model', '?')})"
        tokens = out.get("tokens") or {}
        if len(summary) < 200 or "## " not in summary:
            raise ValueError(f"the summary came back too short ({len(summary)} characters)")
    except Exception as e:                                  # noqa: BLE001 - reported, never fatal
        error, fallback = f"{type(e).__name__}: {e}"[:300], True
        summary, used = fallback_summary(title, conversation, digest, error), "no model"
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    summary_file = folder / f"summary-{n}.md"
    summary_file.write_text(f"<!-- handoff {from_pa} -> {to_pa}, {stamp}, written by {used} -->\n{summary}\n",
                            encoding="utf-8")
    prompt = pa_brief.continuation(to_pa, from_pa, summary, str(summary_file), request)
    prompt_file = folder / f"prompt-{n}.md"
    prompt_file.write_text(prompt + "\n", encoding="utf-8")
    return {"ok": True, "summary": str(summary_file), "prompt_file": str(prompt_file), "prompt": prompt,
            "model": used, "fallback": fallback, "error": error, "tokens": tokens}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dir", required=True, type=Path, help="<chat artifacts>/handoff")
    ap.add_argument("--n", required=True, type=int)
    ap.add_argument("--from", dest="from_pa", required=True)
    ap.add_argument("--to", dest="to_pa", required=True)
    ap.add_argument("--title", default="this chat")
    ap.add_argument("--member", default=None, help="the summarizer (default: pa.handoff_summarizer)")
    args = ap.parse_args(argv)
    member = args.member or (personnel.load().get("pa") or {}).get("handoff_summarizer") or "Gordon"
    try:
        from crew.config import load_config
        state = Path(load_config().state_home)
    except Exception:                                       # noqa: BLE001
        state = None
    try:
        answer = handoff(args.dir, args.n, args.from_pa, args.to_pa, args.title, member, state)
    except Exception as e:                                  # noqa: BLE001
        answer = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(answer, ensure_ascii=False))
    return 0 if answer.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
