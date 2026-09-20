"""Godot side-scroller falsifier battery for the ATLAS API harness.

Runs the T1-T4 test battery identically against the Phase 1 model roster,
records per-call token telemetry (via the providers layer) plus per-tier
summaries, and verifies outputs through the structural/check-only/WSB ladder
(experiments/verify.py).

Usage (zero-config; reads the Synthetic key from crush.json automatically):
    SET ATLAS_PROVIDER=synthetic
    python experiments/godot_battery.py --model hf:zai-org/GLM-4.7-Flash
    python experiments/godot_battery.py --model all --tiers all

Modes:
    raw (default) — bare chat completion, harness OFF. Baseline condition.
    v3            — reserved: route through the V3 pipeline (Phase B).
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "v3-service"))

os.environ.setdefault("ATLAS_PROVIDER", "synthetic")
os.environ.setdefault(
    "ATLAS_TELEMETRY_FILE",
    str(Path(r"C:\Users\user\Documents\Obsidian\Knowledge_Base"
             r"\wiki\experiments\atlas-api-harness\runs") / "telemetry.jsonl"),
)

from providers.telemetry import record as telemetry_record  # noqa: E402
from providers.telemetry import context as telemetry_context  # noqa: E402
from providers.registry import resolve_alias, nickname_for  # noqa: E402
from stages.llm_client import chat_completion  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attempts import AttemptTracker  # noqa: E402

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
ROSTER_PHASE1 = [
    "hf:openai/gpt-oss-120b",
    "hf:zai-org/GLM-4.7-Flash",
    "hf:Qwen/Qwen3.8-27B",
]
TIERS = [1, 2, 3, 4]
MAX_TOKENS = {1: 4096, 2: 6144, 3: 8192, 4: 8192}
BUDGET_CAP_PER_TIER = 15000  # cumulative tokens per tier incl. repair rounds;
# Qwen-shaped runaways (30-44k) escalate instead of burning through (2026-09-18)
TEMPERATURE = 0.2
SEED_BASE = 4200

DEFAULT_SYSTEM = (
    "You are a precise Godot 4.6 engine programmer. Follow the output contract "
    "exactly: fenced code blocks whose info string is the file path, and "
    "nothing else."
)

FILE_BLOCK = re.compile(r"^```([A-Za-z0-9_./-]+)\s*\r?\n(.*?)```\s*$",
                        re.MULTILINE | re.DOTALL)

# Language tags models substitute for real paths. Observed in the field:
# GLM-4.7-Flash fenced as ```gdscript/```xml, losing every file it wrote.
LANG_TAGS = {
    "gdscript", "gd", "tscn", "godot", "ini", "xml", "python", "json",
    "cfg", "txt", "md", "sh", "bash", "cs", "csharp",
}

EXPECTED_FILES = {
    1: {"project.godot": "project.godot", "main.tscn": "any .tscn",
        "main.gd": "any .gd"},
    2: {"player.gd": "player controller script",
        "player.tscn": "player scene", "main.tscn": "main scene"},
    3: {"goal.gd": "goal script", "player.gd": "player script",
        "level_1.tscn": "level scene"},
    4: {"project.godot": "project config",
        "level_1.tscn": "level scene", "player.gd": "player script",
        "goal.gd": "goal script", "level_1.gd": "level script"},
}


# Path hints inside language-tagged blocks: all 3 roster models ignore the
# fence-filename contract but consistently put the path as a first-line comment
# (run battery-20260918-052452). Honor that instead of discarding their files.
HEADER_PATH = re.compile(
    r"^\s*#\s*(?:file:\s*)?([A-Za-z0-9_./-]+\.(?:gd|tscn|tres|cfg|godot|cs))\b",
    re.IGNORECASE)


def _valid_relpath(rel: str) -> bool:
    return bool(rel) and not rel.startswith(("http", "c:", "/")) \
        and ".." not in rel and bool(re.search(r"\.[a-z0-9]{1,10}$", rel))


def extract_files(text: str) -> dict:
    files = {}
    for info, content in FILE_BLOCK.findall(text):
        rel = info.strip().lower()
        if rel in LANG_TAGS:
            rel = ""
            for line in content.splitlines()[:3]:
                m = HEADER_PATH.match(line)
                if m:
                    rel = m.group(1).lower()
                    break
            if not rel:
                continue
        if not _valid_relpath(rel):
            continue
        files[rel] = content.lstrip("\r\n").rstrip() + "\n"
    return files


def expected_coverage(tier: int, files: dict) -> dict:
    """Which required deliverables the model actually produced, by basename."""
    basenames = {Path(k).name for k in files}
    required = EXPECTED_FILES.get(tier, {})
    return {req: (req in basenames) for req in required}


REPAIR_PROMPT = (
    "Your previous output FAILED automated Godot 4.6 verification.\n"
    "Errors reported by the tools:\n{errors}\n\n"
    "Fix ONLY the reported problems. Keep everything else identical.\n"
    "Output the COMPLETE file set again using the same output contract "
    "(fenced code blocks, path in the fence info string OR as a first-line "
    "# comment). No prose."
)


def _verify_and_grade(tier: int, files: dict, tier_dir: Path):
    coverage = expected_coverage(tier, files)
    verify = None
    if files:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import verify as verify_mod
        verify = verify_mod.verify_tier(tier, files, tier_dir)
    passed = (bool(files) and all(coverage.values())
              and bool(verify and verify.get("passed")))
    return passed, coverage, verify


def _collect_errors(coverage: dict, verify) -> str:
    lines = []
    missing = [k for k, v in coverage.items() if not v]
    if missing:
        lines.append(f"MISSING required files: {', '.join(missing)}")
    for step in (verify or {}).get("steps", []):
        if not step.get("ok"):
            detail = (step.get("detail") or "")[:800]
            lines.append(f"[{step['rung']}] {step.get('file', '')}: {detail}")
    return "\n".join(lines) or "unknown failure"


def _should_escalate(tier: int, failure_class, attempts: list,
                     repair_rounds: int) -> bool:
    if failure_class == "budget_exceeded":
        return True
    if tier == 4:
        return True
    return repair_rounds > 0 and len(attempts) >= 1 + repair_rounds


def run_tier(model: str, tier: int, run_dir: Path, mode: str = "raw",
             repair_rounds: int = 0, budget: int = BUDGET_CAP_PER_TIER,
             senior: str = "", module=None, module_mode: str = "off",
             seed_base: int = SEED_BASE) -> dict:
    prompt_path = PROMPTS_DIR / f"t{tier}.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    os.environ["ATLAS_CHAT_MODEL"] = model

    use_prompt = module_mode in ("prompted", "both")
    use_frontload = module_mode in ("frontload", "both")
    system_prompt = DEFAULT_SYSTEM
    if module and module_mode != "off":
        system_prompt = (DEFAULT_SYSTEM + "\n\n"
                         + module.knowledge_for_system())
    if module and use_prompt:
        prompt = prompt + "\n\n" + module.prompt_appendix()

    tier_dir = run_dir / f"t{tier}"
    tier_dir.mkdir(parents=True, exist_ok=True)

    attempts = []
    totals = {"prompt": 0, "completion": 0, "total": 0, "latency_ms": 0.0}
    passed = coverage = verify = files = None
    first_content = None
    backfilled = []
    tracker = AttemptTracker()

    for attempt in range(1 + repair_rounds):
        best = tracker.best
        if attempt == 0 or not best:
            messages = [{"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}]
        else:
            # Repair from the BEST attempt so far, never from a regression.
            errors = _collect_errors(best["coverage"], best["verify"])
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": best["content"]},
                {"role": "user", "content": REPAIR_PROMPT.format(errors=errors)},
            ]
        with telemetry_context(task_id=f"t{tier}", attempt=attempt):
            result = chat_completion("", messages=messages,
                                     temperature=TEMPERATURE,
                                     max_tokens=MAX_TOKENS[tier],
                                     seed=seed_base + tier, timeout=900.0)
        content = result["content"]
        if first_content is None:
            first_content = content
        usage = (result.get("raw") or {}).get("usage") or {}
        totals["prompt"] += usage.get("prompt_tokens", 0) or 0
        totals["completion"] += usage.get("completion_tokens", 0) or 0
        totals["total"] += usage.get("total_tokens", 0) or 0
        totals["latency_ms"] += result.get("time_ms", 0) or 0

        sub = tier_dir if attempt == 0 else tier_dir / f"repair{attempt}"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "response.txt").write_text(content, encoding="utf-8")

        files = extract_files(content)
        verify_files = files
        backfilled = []
        if module and use_frontload and module.template_files:
            verify_files = {**module.template_files, **files}
            backfilled = [k for k in module.template_files if k not in files]
        passed, coverage, verify = _verify_and_grade(tier, verify_files,
                                                     sub / "work")
        attempts.append({"attempt": attempt, "passed": passed,
                         "prompt_tokens": usage.get("prompt_tokens", 0),
                         "completion_tokens": usage.get("completion_tokens", 0),
                         "latency_ms": round(result.get("time_ms", 0), 1),
                         "coverage": coverage,
                         "verify_passed": bool(verify and verify.get("passed"))})
        steps = ([{"rung": "coverage", "file": k, "ok": v}
                  for k, v in coverage.items()]
                 + list((verify or {}).get("steps", [])))
        go_on = tracker.add(attempt, files, steps, passed, content=content,
                            coverage=coverage, verify=verify,
                            backfilled=backfilled)
        if not go_on:
            break
        if totals["total"] >= budget:
            tracker.stop_reason = "budget"
            print(f"  [budget] tier cumulative {totals['total']} tok >= cap "
                  f"{budget}: escalate, no more repair rounds", flush=True)
            break

    # Grade the BEST attempt, not the last one.
    best = tracker.best
    passed, coverage, verify = best["passed"], best["coverage"], best["verify"]
    files, backfilled = best["files"], best["backfilled"]
    prev_content = best["content"]

    failure_class = None
    if not passed and totals["total"] >= budget:
        failure_class = "budget_exceeded"
    elif not passed and not (files or {}):
        failure_class = "contract_violation"
    elif not passed:
        failure_class = "verification"

    senior_review = None
    if senior and not passed and _should_escalate(tier, failure_class,
                                                  attempts, repair_rounds):
        import senior_review as senior_mod
        senior_review = senior_mod.review_failure(
            tier, prompt, {"model": model, "coverage": coverage,
                           "verify": verify, "attempts": attempts,
                           "total_tokens": totals["total"],
                           "budget_cap": budget,
                           "failure_class": failure_class},
            prev_content or "", senior, tier_dir, first_content or "")
        print(f"  [senior] {senior_review['senior_nickname']}: "
              f"{senior_review['root_cause'][:100]}", flush=True)

    summary = {
        "model": model,
        "nickname": nickname_for(os.environ.get("ATLAS_PROVIDER"), model),
        "tier": tier,
        "mode": mode,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "prompt_tokens": totals["prompt"],
        "completion_tokens": totals["completion"],
        "total_tokens": totals["total"],
        "budget_cap": budget,
        "failure_class": failure_class,
        "latency_ms": round(totals["latency_ms"], 1),
        "files_extracted": len(files or {}),
        "module": module.name if module else None,
        "module_mode": module_mode if module else "off",
        "template_backfilled": backfilled,
        "coverage": coverage,
        "verify": verify,
        "attempts": attempts,
        "repaired": len(attempts) - 1,
        **tracker.summary(),
        "senior_review": {k: senior_review[k] for k in
                          ("senior_model", "senior_nickname", "root_cause",
                           "fixes", "constraint", "prompt_tokens",
                           "completion_tokens")} if senior_review else None,
        "passed": bool(passed),
    }
    (tier_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    telemetry_record({"source": "battery", "event": "tier_result", **{
        k: summary[k] for k in ("model", "tier", "mode", "prompt_tokens",
                                "completion_tokens", "total_tokens",
                                "latency_ms", "files_extracted", "passed")}})
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="all",
                    help="model id, or 'all' for the Phase 1 roster")
    ap.add_argument("--tiers", default="all",
                    help="'all' or comma list, e.g. '1,2'")
    ap.add_argument("--mode", default="raw", choices=["raw", "v3"])
    ap.add_argument("--repair", type=int, default=0,
                    help="repair feedback rounds per tier after a failure "
                         "(0 = pure baseline, >0 measures harness effect)")
    ap.add_argument("--budget", type=int, default=BUDGET_CAP_PER_TIER,
                    help="cumulative token cap per tier before escalation "
                         "(failure_class=budget_exceeded)")
    ap.add_argument("--module", default="",
                    help="domain knowledge module (e.g. godot); empty = raw "
                         "baseline")
    ap.add_argument("--module-mode", default="both",
                    choices=["prompted", "frontload", "both"],
                    help="delivery: prompted = knowledge+examples in prompt; "
                         "frontload = starter template merged under output "
                         "at verification; both = both")
    ap.add_argument("--seed-base", type=int, default=SEED_BASE,
                    help="base for per-tier seeds (seed = base + tier); vary "
                         "it for stability probes")
    ap.add_argument("--senior", default="",
                    help="escalation model id or alias (e.g. Kimi); empty = "
                         "senior review off")
    ap.add_argument("--runs-root", default=str(REPO_ROOT / "runs"))
    args = ap.parse_args()

    if args.mode == "v3":
        print("v3 mode is Phase B: not wired yet. Use --mode raw.", file=sys.stderr)
        return 2

    if args.model.lower() == "all":
        models = ROSTER_PHASE1
    else:
        models = [resolve_alias(os.environ.get("ATLAS_PROVIDER"), m)
                  for m in args.model.split(",")]
    tiers = TIERS if args.tiers == "all" else [int(t) for t in args.tiers.split(",")]

    module = None
    if args.module:
        import modules as module_loader
        module = module_loader.load_module(args.module)
        print(f"Module: {module.name} v{module.manifest.get('version')} "
              f"(mode {args.module_mode}; template "
              f"{len(module.template_files)} files, examples "
              f"{len(module.example_files)} files)")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.runs_root) / f"battery-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"started": stamp, "models": models, "tiers": tiers,
                "mode": args.mode, "repair_rounds": args.repair,
                "budget_cap": args.budget,
                "senior": args.senior,
                "module": module.name if module else None,
                "module_mode": args.module_mode if module else "off",
                "temperature": TEMPERATURE,
                "seed_base": args.seed_base}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"Battery run dir: {run_dir}")
    print(f"Telemetry: {os.environ['ATLAS_TELEMETRY_FILE']}\n")

    all_summaries = []
    for model in models:
        print(f"=== {model} ===")
        failures_in_a_row = 0
        for tier in tiers:
            t0 = time.time()
            try:
                with telemetry_context(run_id=run_dir.name, duty="battery",
                                       role="junior",
                                       persona=nickname_for(
                                           os.environ.get("ATLAS_PROVIDER"),
                                           model)):
                    summary = run_tier(
                        model, tier, run_dir / model.replace("/", "_")
                        .replace(":", "_"), mode=args.mode,
                        repair_rounds=args.repair,
                        budget=args.budget, senior=args.senior,
                        module=module, module_mode=args.module_mode,
                        seed_base=args.seed_base)
            except Exception as e:
                summary = {"model": model, "tier": tier,
                           "error": f"{type(e).__name__}: {e}", "passed": False}
                print(f"  T{tier}: ERROR {e}")
            all_summaries.append(summary)
            if summary.get("passed"):
                failures_in_a_row = 0
            else:
                failures_in_a_row += 1
            wall = time.time() - t0
            print(f"  T{tier}: {'PASS' if summary.get('passed') else 'FAIL'} "
                  f"({wall:.0f}s, {summary.get('total_tokens', 0)} tok)")
            if failures_in_a_row >= 2:
                print(f"  Two consecutive failures at T{tier}: stop condition, "
                      f"skipping remaining tiers for {model}")
                break

    report = {"manifest": manifest, "summaries": all_summaries}
    (run_dir / "report.json").write_text(json.dumps(report, indent=2))
    n_pass = sum(1 for s in all_summaries if s.get("passed"))
    total_tokens = sum(s.get("total_tokens", 0) for s in all_summaries)
    print(f"\nDone: {n_pass}/{len(all_summaries)} tier-runs passed, "
          f"{total_tokens} total completion+prompt-adjacent tokens (see telemetry for exact split)")
    print(f"Report: {run_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
