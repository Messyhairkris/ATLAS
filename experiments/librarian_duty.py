"""Librarian duty runner — first real job for a graduated small model.

DUTY: maintain wiki/experiments/atlas-api-harness/ (the lab notebook).
Protocol: the model NEVER touches the filesystem. It receives an evidence
pack (file inventory + excerpts), produces one markdown file, and the
harness applies it ONLY after verification:

  1. path gate     — target file inside the whitelisted folder, no ".."
  2. link gate     — every wikilink/relative link resolves to a real file
                     in the folder (no dangling references, no absolute
                     paths, no escapes)
  3. coverage gate — every .md note in the folder is linked somewhere
  4. grounding gate — every number/ratio/$/verdict word on a line appears
                     in the note(s) that line links to (stops a confident
                     but miscalibrated summary line; zero tokens)

Failure: repair feedback (verbatim gate output) up to --repair rounds, then
senior escalation (Kimi / Claude). Success threshold and failure realignment
are identical in shape to the battery loop — this is the "bigger task"
pattern: large model designs the task structure, Hoss executes parts, gates
verify, seniors realign.

    python experiments/librarian_duty.py --model Hoss
    python experiments/librarian_duty.py --model Hoss --senior Claude --dry
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "v3-service"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("ATLAS_PROVIDER", "synthetic")
os.environ.setdefault(
    "ATLAS_TELEMETRY_FILE",
    str(Path(r"C:\Users\user\Documents\Obsidian\Knowledge_Base"
             r"\wiki\experiments\atlas-api-harness\runs") / "telemetry.jsonl"),
)

from providers.registry import resolve_alias  # noqa: E402
from providers.telemetry import context as telemetry_context  # noqa: E402
from attempts import AttemptTracker  # noqa: E402
from stages.llm_client import chat_completion  # noqa: E402

VAULT_DUTY_ROOT = Path(
    r"C:\Users\user\Documents\Obsidian\Knowledge_Base"
    r"\wiki\experiments\atlas-api-harness")
TARGET_FILE = "INDEX.md"
TEMPERATURE = 0.2
MAX_TOKENS = 4096

SYSTEM = (
    "You are the Librarian of an experiment lab notebook (Obsidian vault). "
    "Output exactly ONE markdown file. No prose outside it."
)

TASK_TEMPLATE = (
    "Write INDEX.md — a Map of Content for this lab notebook folder.\n"
    "RULES:\n"
    "1. Link every note using Obsidian wikilinks relative to the folder, "
    "e.g. [[PLAN]] or [[runs/RUN-20260918-battery-2.0]].\n"
    "2. One short line per note: what it decides or records.\n"
    "3. Group by theme; put the experiment thesis + verdict at the top.\n"
    "4. Files under runs/ are run logs; PLAN.md is the master plan.\n"
    "5. Do NOT link INDEX.md itself. Do NOT link telemetry.jsonl.\n"
    "6. No invented paths: only files from the inventory below.\n\n"
    "FOLDER INVENTORY + EXCERPTS:\n{inventory}\n"
)

REPAIR_TEMPLATE = (
    "Your previous INDEX.md FAILED verification.\n"
    "Gate output (verbatim):\n{errors}\n\n"
    "Rewrite the COMPLETE file. Fix only what the gates reported.\n"
)

WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def build_inventory(root: Path, excerpt_lines: int = 6) -> str:
    parts = []
    for p in sorted(root.rglob("*")):
        if p.is_dir() or p.suffix != ".md":
            continue
        rel = p.relative_to(root).as_posix()
        lines = [ln for ln in p.read_text(encoding="utf-8", errors="replace")
                 .splitlines() if ln.strip()][:excerpt_lines]
        parts.append(f"--- {rel} ---\n" + "\n".join(lines))
    return "\n\n".join(parts)


def verify_index(text: str, root: Path) -> dict:
    steps = []
    if ".." in text or re.search(r"\b[A-Za-z]:\\|/[A-Za-z]/", text):
        steps.append({"rung": "path-gate", "ok": False,
                      "detail": "absolute path or '..' escape detected"})
    else:
        steps.append({"rung": "path-gate", "ok": True, "detail": "ok"})

    links = [l.strip().removesuffix(".md") for l in WIKILINK.findall(text)]
    dangling = []
    for link in links:
        if not (root / (link + ".md")).exists():
            dangling.append(link)
    steps.append({"rung": "link-gate", "ok": not dangling,
                  "detail": ("dangling links: " + ", ".join(dangling))
                  if dangling else "ok"})

    notes = {p.relative_to(root).with_suffix("").as_posix()
             for p in root.rglob("*.md")}
    notes.discard(TARGET_FILE.rsplit(".", 1)[0])
    linked = set(links)
    unlinked = sorted(n for n in notes if n not in linked)
    steps.append({"rung": "coverage-gate", "ok": not unlinked,
                  "detail": ("notes not linked: " + ", ".join(unlinked))
                  if unlinked else "ok"})
    ungrounded = grounding_violations(text, root)
    steps.append({"rung": "grounding-gate", "ok": not ungrounded,
                  "detail": ("claims not found in the linked note(s): "
                             + "; ".join(ungrounded[:8]))
                  if ungrounded else "ok"})
    return {"steps": steps, "passed": all(s["ok"] for s in steps)}


# Claims a summary line can get confidently wrong: numbers/ratios/money and
# verdict words. Each must literally appear in a note the line links to (or,
# for an unlinked line, in some note in the folder). Zero tokens.
CLAIM_NUMBER = re.compile(r"\$?\d[\d.,]*(?:/\d+)?(?:%|k|K|x|×)?")
VERDICT_WORDS = ("PASS", "FAIL", "MET", "CONFIRMED", "PARTIAL", "DONE",
                 "BLOCKED", "REJECTED")


def _claims(line: str) -> list:
    bare = WIKILINK.sub(" ", line)
    nums = [n.rstrip(".,") for n in CLAIM_NUMBER.findall(bare)]
    words = [w for w in VERDICT_WORDS if re.search(rf"\b{w}\b", bare)]
    return [n for n in nums if len(n) >= 2] + words


def grounding_violations(text: str, root: Path) -> list:
    corpus = {p.relative_to(root).with_suffix("").as_posix():
              p.read_text(encoding="utf-8", errors="replace")
              for p in root.rglob("*.md") if p.name != TARGET_FILE}
    everything = "\n".join(corpus.values())
    out = []
    for line in text.splitlines():
        claims = _claims(line)
        if not claims:
            continue
        links = [l.strip().removesuffix(".md") for l in WIKILINK.findall(line)]
        sources = ("\n".join(corpus.get(l, "") for l in links)
                   if links else everything)
        for c in claims:
            if c not in sources:
                where = ", ".join(links) if links else "any note"
                out.append(f"'{c}' (line: {line.strip()[:70]}) not in {where}")
    return out


def _errors(report: dict) -> str:
    return "\n".join(f"[{s['rung']}] {s['detail']}"
                     for s in report["steps"] if not s["ok"])


def strip_fence(text: str) -> str:
    m = re.match(r"\s*```(?:markdown|md)?\s*\r?\n(.*?)\n?```\s*$",
                 text, re.DOTALL)
    return m.group(1) if m else text


def run_duty(model: str, repair_rounds: int = 1, senior: str = "",
             dry: bool = False, out_dir: Path = None) -> dict:
    model = resolve_alias(os.environ.get("ATLAS_PROVIDER"), model)
    os.environ["ATLAS_CHAT_MODEL"] = model
    root = VAULT_DUTY_ROOT
    inventory = build_inventory(root)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK_TEMPLATE.format(
                    inventory=inventory)}]
    attempts, totals = [], 0
    tracker = AttemptTracker()
    for attempt in range(1 + repair_rounds):
        best = tracker.best
        if attempt and best:
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK_TEMPLATE.format(
                    inventory=inventory)},
                {"role": "assistant", "content": best["content"]},
                {"role": "user", "content": REPAIR_TEMPLATE.format(
                    errors=_errors(best["report"]))},
            ]
        with telemetry_context(attempt=attempt):
            result = chat_completion("", messages=messages,
                                     temperature=TEMPERATURE,
                                     max_tokens=MAX_TOKENS, timeout=600.0)
        content = strip_fence(result["content"])
        usage = (result.get("raw") or {}).get("usage") or {}
        totals += usage.get("total_tokens", 0) or 0
        report = verify_index(content, root)
        attempts.append({"attempt": attempt,
                         "passed": report["passed"],
                         "tokens": usage.get("total_tokens", 0)})
        if not tracker.add(attempt, {TARGET_FILE: content}, report["steps"],
                           report["passed"], content=content, report=report):
            break
    best = tracker.best
    content, report = best["content"], best["report"]

    applied = False
    if report["passed"] and not dry:
        (root / TARGET_FILE).write_text(content.rstrip() + "\n",
                                        encoding="utf-8")
        applied = True

    senior_review = None
    if senior and not report["passed"]:
        import senior_review as senior_mod
        senior_review = senior_mod.review_failure(
            0, TASK_TEMPLATE.format(inventory="<inventory, 3k chars>"),
            {"model": model, "coverage": {}, "verify": report,
             "attempts": attempts, "total_tokens": totals,
             "budget_cap": "-", "failure_class": "duty_gates"},
            content, senior, out_dir, "")

    summary = {
        "duty": "librarian-index", "model": model,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "total_tokens": totals, "attempts": attempts,
        "passed": report["passed"], "applied": applied, "dry": dry,
        "verify": report,
        **tracker.summary(),
        "senior_review": {"root_cause": senior_review["root_cause"],
                          "fixes": senior_review["fixes"],
                          "constraint": senior_review["constraint"]}
        if senior_review else None,
    }
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "duty_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        (out_dir / TARGET_FILE).write_text(content, encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="Hoss")
    ap.add_argument("--repair", type=int, default=1)
    ap.add_argument("--senior", default="")
    ap.add_argument("--dry", action="store_true",
                    help="verify but never write into the vault")
    args = ap.parse_args()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = REPO_ROOT / "runs" / f"duty-librarian-{stamp}"
    with telemetry_context(run_id=out_dir.name, duty="librarian-index",
                           task_id="INDEX.md", role="junior",
                           persona=args.model):
        summary = run_duty(args.model, repair_rounds=args.repair,
                           senior=args.senior, dry=args.dry, out_dir=out_dir)
    print(json.dumps({k: summary[k] for k in
                      ("passed", "applied", "total_tokens", "attempts")},
                     indent=2))
    if not summary["passed"]:
        print(_errors(summary["verify"]))
    print(f"Artifacts: {out_dir}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
