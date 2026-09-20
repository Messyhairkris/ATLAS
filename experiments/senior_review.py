"""Senior review escalation for the falsifier battery.

When a junior model exhausts its repair rounds or its per-tier token budget,
the failure is escalated to a senior model the caller names explicitly (no
default: senior spend is always a deliberate choice). The senior
receives a compact evidence pack (prompt, verifier errors verbatim, last
attempt, token ledger) and returns DIRECTIVES, not code: root cause, ranked
fixes the junior can execute mechanically, and one plan constraint for the
next round. Directives are appended to experiments/pattern_cache.jsonl for
batched human review in the vault.

Standalone re-review of an existing run:
    python experiments/senior_review.py runs/battery-YYYYMMDD-HHMMSS/model/t3 \
        --senior Claude
"""

import argparse
import datetime
import difflib
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "v3-service"))

os.environ.setdefault("ATLAS_PROVIDER", "synthetic")
os.environ.setdefault(
    "ATLAS_TELEMETRY_FILE",
    str(Path(r"C:\Users\user\Documents\Obsidian\Knowledge_Base"
             r"\wiki\experiments\atlas-api-harness\runs") / "telemetry.jsonl"),
)

from providers.registry import resolve_alias, nickname_for  # noqa: E402
from providers.telemetry import context as telemetry_context  # noqa: E402
from providers.telemetry import record as telemetry_record  # noqa: E402
from stages.llm_client import chat_completion  # noqa: E402

PATTERN_CACHE = Path(__file__).resolve().parent / "pattern_cache.jsonl"
EVIDENCE_CHAR_CAP = 12000
DIFF_CHAR_CAP = 2000
SENIOR_MAX_TOKENS = 2048

SENIOR_SYSTEM = (
    "You are a senior Godot 4.6 engine engineer reviewing a junior model's "
    "failed attempt. You produce DIRECTIVES, never code. Output exactly "
    "this shape:\n"
    "ROOT CAUSE: <one or two lines>\n"
    "FIX 1: <highest-priority mechanical fix>\n"
    "FIX 2: <next fix>\n"
    "FIX 3: <optional third fix>\n"
    "CONSTRAINT: <one hard rule the junior must obey on its next attempt>\n"
    "Nothing else. Terse, imperative, Godot 4.6 specific."
)

REVIEW_TEMPLATE = (
    "TIER {tier} TASK (verbatim prompt given to the junior):\n{prompt}\n\n"
    "AUTOMATED VERIFIER ERRORS (verbatim):\n{errors}\n\n"
    "TOKEN LEDGER (per attempt: attempt, prompt+completion tokens):\n"
    "{ledger}\n\n"
    "{diff_block}"
    "JUNIOR'S LAST ATTEMPT (raw response, may be truncated):\n"
    "{last_attempt}\n"
)


def _failing_rungs(summary: dict) -> str:
    lines = []
    coverage = summary.get("coverage") or {}
    missing = [k for k, v in coverage.items() if not v]
    if missing:
        lines.append(f"MISSING required files: {', '.join(missing)}")
    for step in (summary.get("verify") or {}).get("steps", []):
        if not step.get("ok"):
            detail = (step.get("detail") or "")[:800]
            lines.append(f"[{step['rung']}] {step.get('file', '')}: {detail}")
    return "\n".join(lines) or "no verifier detail recorded"


def _ledger(summary: dict) -> str:
    rows = []
    for a in summary.get("attempts", []):
        rows.append(f"attempt {a['attempt']}: "
                    f"{a.get('prompt_tokens', 0)}+{a.get('completion_tokens', 0)} "
                    f"tok, {'PASS' if a.get('passed') else 'FAIL'}")
    rows.append(f"cumulative: {summary.get('total_tokens', 0)} tok "
                f"(cap {summary.get('budget_cap', '?')}, "
                f"class {summary.get('failure_class', '?')})")
    return "\n".join(rows)


def build_evidence_pack(tier: int, prompt: str, summary: dict,
                        last_content: str, first_content: str = "") -> str:
    diff_block = ""
    if first_content and first_content != last_content:
        diff = "\n".join(difflib.unified_diff(
            first_content.splitlines(), last_content.splitlines(),
            fromfile="attempt0", tofile="last", lineterm=""))
        diff_block = ("DIFF attempt0 -> last (truncated):\n"
                      + diff[:DIFF_CHAR_CAP] + "\n\n")
    body = REVIEW_TEMPLATE.format(
        tier=tier, prompt=prompt, errors=_failing_rungs(summary),
        ledger=_ledger(summary), diff_block=diff_block,
        last_attempt=last_content)
    return body[:EVIDENCE_CHAR_CAP]


DIRECTIVE_RE = re.compile(
    r"ROOT CAUSE:\s*(?P<root>.*?)\s*"
    r"(?P<fixes>(?:FIX \d+:.*?\s*)+)"
    r"CONSTRAINT:\s*(?P<constraint>.*?)\s*$",
    re.DOTALL)


def parse_directives(text: str) -> dict:
    m = DIRECTIVE_RE.search(text or "")
    if not m:
        return {"root_cause": "", "fixes": [], "constraint": "", "raw_ok": False}
    fixes = re.findall(r"FIX \d+:\s*(.+?)(?=\s*FIX \d+:|\s*$)",
                       m.group("fixes"), re.DOTALL)
    return {"root_cause": " ".join(m.group("root").split()),
            "fixes": [" ".join(f.split()) for f in fixes],
            "constraint": " ".join(m.group("constraint").split()),
            "raw_ok": True}


def _save_pattern(entry: dict) -> None:
    with PATTERN_CACHE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _call_claude_cli(system: str, user: str) -> dict:
    import shutil
    import subprocess
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError(
            "senior 'Claude' requested but no `claude` CLI on PATH; "
            "install Claude Code or use another --senior")
    prompt = system + "\n\n" + user
    t0 = datetime.datetime.now()
    proc = subprocess.run([exe, "-p", "--output-format", "text"],
                          input=prompt, capture_output=True, text=True,
                          timeout=600)
    # Claude CLI usage is plan-billed and not metered here, but the call is
    # still logged so the ledger shows every senior touch.
    telemetry_record({"source": "senior_review", "provider": "claude-cli",
                      "model": "claude", "requests": 1,
                      "prompt_chars": len(prompt),
                      "latency_ms": round((datetime.datetime.now() - t0)
                                          .total_seconds() * 1000, 1),
                      "prompt_tokens": None, "completion_tokens": None,
                      "cost_usd": None})
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exit {proc.returncode}: "
                           f"{(proc.stderr or '')[:300]}")
    return {"content": proc.stdout.strip(), "raw": {"usage": {}}}


def review_failure(tier: int, prompt: str, summary: dict, last_content: str,
                   senior_model: str, tier_dir: Path,
                   first_content: str = "") -> dict:
    senior_model = resolve_alias(os.environ.get("ATLAS_PROVIDER"),
                                 senior_model)
    pack = build_evidence_pack(tier, prompt, summary, last_content,
                               first_content)
    with telemetry_context(role="senior", senior=senior_model):
        if senior_model.lower() in ("claude", "claude-code"):
            result = _call_claude_cli(SENIOR_SYSTEM, pack)
        else:
            junior_model = os.environ.get("ATLAS_CHAT_MODEL", "")
            os.environ["ATLAS_CHAT_MODEL"] = senior_model
            try:
                result = chat_completion(
                    "", messages=[{"role": "system",
                                   "content": SENIOR_SYSTEM},
                                  {"role": "user", "content": pack}],
                    temperature=0.2, max_tokens=SENIOR_MAX_TOKENS,
                    timeout=600.0)
            finally:
                os.environ["ATLAS_CHAT_MODEL"] = junior_model
    raw = result["content"]
    usage = (result.get("raw") or {}).get("usage") or {}
    directives = parse_directives(raw)
    review = {
        "senior_model": senior_model,
        "senior_nickname": nickname_for(os.environ.get("ATLAS_PROVIDER"),
                                        senior_model),
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "evidence_chars": len(pack),
        "raw": raw,
        **directives,
        "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
        "completion_tokens": usage.get("completion_tokens", 0) or 0,
    }
    tier_dir = Path(tier_dir)
    tier_dir.mkdir(parents=True, exist_ok=True)
    (tier_dir / "senior_review.json").write_text(
        json.dumps(review, indent=2), encoding="utf-8")
    _save_pattern({
        "ts": review["ts"],
        "model": summary.get("model"),
        "tier": tier,
        "failure_class": summary.get("failure_class"),
        "root_cause": review["root_cause"],
        "fixes": review["fixes"],
        "constraint": review["constraint"]})
    return review


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tier_dir", help="tier dir of an existing run, e.g. "
                    "runs/battery-.../hf_x_model/t3")
    ap.add_argument("--senior", required=True,
                    help="senior model id or alias (e.g. Claude, Kimi); "
                         "required so senior spend is always explicit")
    args = ap.parse_args()

    tier_dir = Path(args.tier_dir)
    summary = json.loads((tier_dir / "summary.json").read_text("utf-8"))
    tier = summary["tier"]
    prompt_path = (Path(__file__).resolve().parent / "prompts"
                   / f"t{tier}.md")
    prompt = prompt_path.read_text(encoding="utf-8")
    subs = sorted(tier_dir.glob("repair*/response.txt"))
    last_content = (subs[-1] if subs else tier_dir / "response.txt") \
        .read_text(encoding="utf-8")
    first = tier_dir / "response.txt"
    first_content = first.read_text(encoding="utf-8") \
        if subs and first.exists() else ""
    review = review_failure(tier, prompt, summary, last_content,
                            args.senior, tier_dir, first_content)
    print(json.dumps({k: review[k] for k in
                      ("senior_nickname", "root_cause", "fixes",
                       "constraint", "prompt_tokens",
                       "completion_tokens")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
