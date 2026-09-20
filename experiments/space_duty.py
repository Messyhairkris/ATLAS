"""Space duty executor — "SIGNAL LOST" tutorial build (plan: experiments/plans/space_tutorial.md).

Runs parts P1-P5 against prompts/space_tutorial/p*.md with a live 2h wall
clock, per-part token budgets, host verification after every part, and a
final Windows-Sandbox playthrough whose log markers decide the verdict.
P0 scaffold = template autoinstall (zero tokens) + deterministic input
actions appended to project.godot.

    python experiments/space_duty.py --model Hoss --wall 7200
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import time
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

from godot_battery import DEFAULT_SYSTEM, extract_files  # noqa: E402
from attempts import AttemptTracker, failing_files, merge_carry  # noqa: E402
from providers.telemetry import context as telemetry_context  # noqa: E402
from providers.registry import resolve_alias  # noqa: E402
from stages.llm_client import chat_completion  # noqa: E402
import modules as module_loader  # noqa: E402
import verify as verify_mod  # noqa: E402

PARTS_SPEC = Path(__file__).resolve().parent / "plans" / "space_parts.json"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts" / "space_tutorial"
TEMPLATE_DIR = (Path(__file__).resolve().parent / "modules" / "godot"
                / "template")
TEMPERATURE = 0.2
MAX_TOKENS = 8192

INPUT_ACTIONS = {
    "move_left": 65, "move_right": 68, "move_up": 87, "move_down": 83,
    # arrows: LEFT/UP/RIGHT/DOWN
    "move_left_alt": 4194319, "move_up_alt": 4194320,
    "move_right_alt": 4194321, "move_down_alt": 4194322,
}


def _input_section() -> str:
    grouped = {"move_left": [65, 4194319], "move_right": [68, 4194321],
               "move_up": [87, 4194320], "move_down": [83, 4194322]}
    blocks = ["\n[input]\n"]
    for action, codes in grouped.items():
        events = ",".join(
            'Object(InputEventKey,"resource_local_to_scene":false,'
            '"resource_name":"","device":-1,"window_id":0,"alt_pressed":false'
            ',"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false'
            ',"pressed":false,"keycode":0,"physical_keycode":%d,'
            '"key_label":0,"unicode":0,"location":0,"echo":false,'
            '"script":null)' % code for code in codes)
        blocks.append(f'{action}={{\n"deadzone": 0.2,\n'
                      f'"events": [{events}]\n}}\n')
    return "\n".join(blocks)


def install_scaffold(work: Path) -> None:
    for f in TEMPLATE_DIR.glob("*"):
        dest = work / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f, dest)
    proj = work / "project.godot"
    text = proj.read_text(encoding="utf-8")
    if "[input]" not in text:
        proj.write_text(text.rstrip() + "\n" + _input_section(),
                        encoding="utf-8")


def part_gates(part: dict, files: dict, work: Path) -> list:
    """Gate one part's files. ``work`` must be a disposable STAGE copy of
    the project: files are written into it before the gates run."""
    steps = []
    for rel in part["required"]:
        ok = rel in files
        steps.append({"rung": "coverage", "file": rel, "ok": ok,
                      "detail": "ok" if ok else "file not emitted"})
    for rel in sorted(files):
        dest = work / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(files[rel], encoding="utf-8")
    for rel, needles in part.get("must_contain", {}).items():
        text = files.get(rel, "")
        missing = [n for n in needles if n not in text]
        steps.append({"rung": "contract", "file": rel, "ok": not missing,
                      "detail": ("missing constructs: " + ", ".join(missing))
                      if missing else "ok"})
    for rel, forbidden in part.get("must_not_contain", {}).items():
        text = files.get(rel, "")
        found = [n for n in forbidden if n in text]
        steps.append({"rung": "contract", "file": rel, "ok": not found,
                      "detail": ("forbidden constructs: " + ", ".join(found))
                      if found else "ok"})
    for rel in part["required"]:
        if rel not in files:
            continue
        p = work / rel
        if rel.endswith(".tscn"):
            ok, detail = verify_mod.structural_check(p)
            steps.append({"rung": "structural", "file": rel, "ok": ok,
                          "detail": detail})
        elif rel.endswith(".gd"):
            ok, detail = verify_mod.check_only_script(p, project_dir=work)
            steps.append({"rung": "check-only", "file": rel, "ok": ok,
                          "detail": detail})
    if part["id"].startswith("p4"):
        ok, detail = verify_mod.project_config_check(work)
        steps.append({"rung": "project-config", "file": "project.godot",
                      "ok": ok, "detail": detail})
    return steps


def _errors(steps: list) -> str:
    return "\n".join(f"[{s['rung']}] {s.get('file','')}: {s['detail']}"
                     for s in steps if not s["ok"]) or "unknown failure"


def run(model: str, senior: str, repair: int, budget_per_part: int,
        wall_s: int, out_dir: Path, spec_path: Path = None,
        prompts_dir: Path = None, work: Path = None,
        skip_scaffold: bool = False) -> dict:
    model = resolve_alias(os.environ.get("ATLAS_PROVIDER"), model)
    module = module_loader.load_module("godot")
    system = DEFAULT_SYSTEM + "\n\n" + module.knowledge_for_system()
    os.environ["ATLAS_CHAT_MODEL"] = model

    t0 = time.time()
    work = work or (out_dir / "project")
    work.mkdir(parents=True, exist_ok=True)
    if not skip_scaffold:
        install_scaffold(work)
    spec = json.loads((spec_path or PARTS_SPEC).read_text("utf-8"))["parts"]
    prompts_dir = prompts_dir or PROMPTS_DIR

    results, totals = [], 0
    consecutive_fail = 0
    aborted = False
    for part in spec:
        elapsed = time.time() - t0
        if elapsed > wall_s:
            aborted = True
            results.append({"part": part["id"], "passed": False,
                            "aborted": "wall clock %.0fs > %ds"
                            % (elapsed, wall_s)})
            break
        prompt = (prompts_dir / (part["id"] + ".md")).read_text("utf-8")
        system_prompt = system + (
            "\n\nProject so far (relative paths of files already installed:"
            " DO NOT re-emit them, they exist on disk): "
            + ", ".join(sorted(str(p.relative_to(work).as_posix())
                               for p in work.rglob("*") if p.is_file())))
        tokens = 0
        tracker = AttemptTracker()
        part_dir = out_dir / part["id"]
        for attempt in range(1 + repair):
            messages = [{"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}]
            best = tracker.best
            if attempt and best:
                # Repair from the BEST attempt so far, not the latest, and
                # ask only for the files that failed: the rest are carried.
                redo = failing_files(best["steps"]) or part["required"]
                messages += [{"role": "assistant", "content": best["content"]},
                             {"role": "user", "content":
                              "Previous part output FAILED verification:\n"
                              + _errors(best["steps"])
                              + "\nFix ONLY the reported problems. Re-emit "
                              "ONLY these files, complete: "
                              + ", ".join(redo) + ". Every other file of "
                              "this part is kept exactly as you last "
                              "emitted it."}]
            with telemetry_context(task_id=part["id"], attempt=attempt):
                res = chat_completion("", messages=messages,
                                      temperature=TEMPERATURE,
                                      max_tokens=MAX_TOKENS,
                                      seed=7000 + attempt, timeout=900.0)
            content = res["content"]
            usage = (res.get("raw") or {}).get("usage") or {}
            tokens += usage.get("total_tokens", 0) or 0
            files = extract_files(content)
            if best:
                files = merge_carry(best["files"], files)
            # Transactional: gate inside a disposable copy of the project;
            # the live project only changes when a whole part passes.
            stage = part_dir / f"stage{attempt}"
            if stage.exists():
                shutil.rmtree(stage)
            shutil.copytree(work, stage)
            steps = part_gates(part, files, stage)
            passed = bool(steps) and all(s["ok"] for s in steps)
            part_dir.mkdir(parents=True, exist_ok=True)
            (part_dir / ("reply.txt" if not attempt
                         else f"repair{attempt}.txt")).write_text(
                content, encoding="utf-8")
            if not tracker.add(attempt, files, steps, passed,
                               content=content):
                break
            if tokens >= budget_per_part:
                tracker.stop_reason = "budget"
                break
        best = tracker.best
        passed = bool(best and best["passed"])
        steps = best["steps"] if best else []
        if passed:
            for rel, text in best["files"].items():
                dest = work / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
        senior_review = None
        if not passed and senior:
            import senior_review as senior_mod
            senior_review = senior_mod.review_failure(
                0, prompt, {"model": model, "coverage": {},
                            "verify": {"steps": steps},
                            "attempts": [{"attempt": r["attempt"],
                                          "passed": r["passed"]}
                                         for r in tracker.history],
                            "total_tokens": tokens,
                            "budget_cap": budget_per_part,
                            "failure_class": "part_gates"},
                best["content"] if best else "", senior, part_dir, "")
        totals += tokens
        consecutive_fail = 0 if passed else consecutive_fail + 1
        results.append({"part": part["id"], "passed": passed,
                        "tokens": tokens,
                        "elapsed_s": round(time.time() - t0, 1),
                        "senior": bool(senior_review),
                        "committed": passed,
                        **tracker.summary(),
                        "fail_steps": [s for s in steps if not s["ok"]]})
        print(f"  {part['id']}: {'PASS' if passed else 'FAIL'} "
              f"({tokens} tok, {time.time() - t0:.0f}s wall)", flush=True)
        if consecutive_fail >= 2:
            aborted = True
            results.append({"part": "stop", "passed": False,
                            "aborted": "2 consecutive part failures"})
            break

    wsb = None
    markers = {}
    if not aborted and all(r.get("passed") for r in results):
        ok, log = verify_mod.run_in_windows_sandbox(
            work, run_seconds=90, timeout_s=420,
            markers=("TUTORIAL_READY", "TUTORIAL_COMPLETE"))
        wsb = {"passed": ok, "log_tail": log[-2000:]}
        for m in ("TUTORIAL_READY", "ORE_COLLECTED", "DEBRIS_COLLECTED",
                  "STAGE_1_COMPLETE", "STAGE_2_COMPLETE", "STAGE_3_COMPLETE",
                  "STAGE_4_COMPLETE", "PLOT_ENVOY", "PLOT_REFINERY",
                  "PLOT_BEACON_DENIAL", "TUTORIAL_COMPLETE",
                  "WATCHDOG_TIMEOUT"):
            markers[m] = m in log
        print(f"  wsb: {'PASS' if ok else 'FAIL'} markers="
              f"{[k for k, v in markers.items() if v]}", flush=True)

    summary = {"duty": "space-tutorial", "model": model,
               "ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "total_tokens": totals,
               "wall_s": round(time.time() - t0, 1),
               "parts": results, "wsb": wsb, "markers": markers,
               "passed": bool(wsb and wsb["passed"])}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "duty_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Hoss")
    ap.add_argument("--senior", default="")
    ap.add_argument("--repair", type=int, default=1)
    ap.add_argument("--budget-per-part", type=int, default=20000)
    ap.add_argument("--wall", type=int, default=7200)
    ap.add_argument("--spec", default="",
                    help="alternate parts spec json (default: space_parts)")
    ap.add_argument("--prompts-dir", default="",
                    help="alternate prompts dir")
    ap.add_argument("--workdir", default="",
                    help="existing project to modify (polish passes)")
    ap.add_argument("--skip-scaffold", action="store_true")
    args = ap.parse_args()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = REPO_ROOT / "runs" / f"space-tutorial-{stamp}"
    print(f"Space duty out: {out_dir}")
    with telemetry_context(run_id=out_dir.name, duty="space-tutorial",
                           role="junior", persona=args.model):
        summary = run(args.model, args.senior, args.repair,
                      args.budget_per_part, args.wall, out_dir,
                      spec_path=Path(args.spec) if args.spec else None,
                      prompts_dir=(Path(args.prompts_dir)
                                   if args.prompts_dir else None),
                      work=Path(args.workdir) if args.workdir else None,
                      skip_scaffold=args.skip_scaffold)
    print(json.dumps({"passed": summary["passed"],
                      "tokens": summary["total_tokens"],
                      "wall_s": summary["wall_s"],
                      "markers": summary["markers"]}, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
