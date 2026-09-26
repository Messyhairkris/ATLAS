"""Turn an archaeology dig into a real archive: cut list -> clean copy ->
post-mortem -> zip. The deterministic back half of the folder-archaeology
tool (crew/runners/archaeology_swarm.py does the research half).

Kris, 2026-09-22: "remove anything that doesn't have potential future use...
organize the remaining files... create the post-mortem... zip the final
resulting folder." This is that stage. Per crew doctrine (automate what can
be automated; mechanical fixes never reach an LLM), the actual file
moving/copying/zipping here is plain deterministic Python, not a crew
member - a member's job stopped at PROPOSING keep/cut verdicts
(archaeology_swarm.py's plan stage, "archive_plan.md" question), this
script's job is APPLYING them, the same read-only-then-a-human-or-script-
applies split crew/task_types.py's organize_plan already uses.

SAFETY, by construction:
- The SOURCE folder is never written to, moved, or deleted. Everything here
  reads from it and writes to a brand new destination.
- A verdict of "cut" never deletes anything either - it just means a file
  does not get copied into the archive. The original is untouched either
  way. Nothing is destructive.
- A hard-exclude list (secrets, .git, node_modules, build output) applies
  REGARDLESS of what any member's cut list says - defense in depth, since
  this script runs outside the crew's own read/write-root gating entirely.
- Defaults to a DRY RUN (--apply is required to actually copy/zip anything)
  so the plan can be reviewed before it touches disk.

    python crew/runners/archive_apply.py --name vocto-tools
    python crew/runners/archive_apply.py --name vocto-tools --apply
    python crew/runners/archive_apply.py --name vocto-tools --apply --dest "C:/Users/user/Archive/vocto-tools"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from crew.config import load_config  # noqa: E402

# -- hard excludes: apply no matter what a member's cut list said -----------

HARD_EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv",
    ".pytest_cache", ".next", "target", ".turbo", ".cache", ".mypy_cache",
}
HARD_EXCLUDE_FILE_PATTERNS = [re.compile(p, re.I) for p in (
    r"^\.env(\..+)?$", r".*secret.*", r".*token.*", r".*credential.*",
    r".*\.pem$", r".*\.key$", r"^id_rsa.*", r"^keys\.json.*", r".*\.json5$",
)]


def _hard_excluded(name: str, is_dir: bool) -> bool:
    if is_dir:
        return name in HARD_EXCLUDE_DIRS
    return any(p.match(name) for p in HARD_EXCLUDE_FILE_PATTERNS)


# -- reading what the crew proposed ------------------------------------------

_JSON_FENCE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict:
    matches = _JSON_FENCE.findall(text)
    for raw in reversed(matches):          # last block wins if more than one
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return {}


def _norm(path: str) -> str:
    return path.strip().strip("/\\").replace("\\", "/")


def merge_cut_lists(plan_files: List[Path]) -> Tuple[Dict[str, dict], List[str]]:
    """path -> {"verdict", "reasons": [...]}. "keep" wins if ANY plan said
    keep for a path - Kris's rule, a wrongly kept file costs disk space, a
    wrongly cut one is a lesson lost for good. Returns (verdicts, sources_used)."""
    votes: Dict[str, list] = {}
    used = []
    for p in plan_files:
        data = _extract_json(p.read_text(encoding="utf-8"))
        entries = data.get("cut_list") or []
        if entries:
            used.append(p.name)
        for entry in entries:
            path = _norm(str(entry.get("path", "")))
            if not path:
                continue
            verdict = "cut" if str(entry.get("verdict", "")).strip().lower() == "cut" else "keep"
            why = str(entry.get("why", "")).strip()
            votes.setdefault(path, []).append((verdict, why, p.stem))
    merged = {}
    for path, entries in votes.items():
        final = "keep" if any(v == "keep" for v, _, _ in entries) else "cut"
        merged[path] = {"verdict": final,
                        "reasons": [f"{src}: {why}" for v, why, src in entries if why]}
    return merged, used


def _verdict_for(rel: str, verdicts: Dict[str, dict]) -> Tuple[str, str]:
    """Exact match first, then the top-level component, then default keep."""
    if rel in verdicts:
        v = verdicts[rel]
        return v["verdict"], "; ".join(v["reasons"]) or "no reason given"
    top = rel.split("/", 1)[0]
    if top in verdicts:
        v = verdicts[top]
        return v["verdict"], f"(via top-level {top}) " + ("; ".join(v["reasons"]) or "no reason given")
    return "keep", "not classified by any plan - kept by default"


# -- walking and copying ------------------------------------------------------

def plan_copy(source: Path, verdicts: Dict[str, dict]) -> dict:
    """Dry-run/real-run shared logic: decide what would be copied. Returns a
    report dict; does not touch disk."""
    kept, cut, hard_excluded, unclassified = [], [], [], []

    def walk(rel_dir: str):
        real = source / rel_dir if rel_dir else source
        for child in sorted(real.iterdir(), key=lambda c: c.name.lower()):
            rel = f"{rel_dir}/{child.name}" if rel_dir else child.name
            if _hard_excluded(child.name, child.is_dir()):
                hard_excluded.append(rel + ("/" if child.is_dir() else ""))
                continue
            verdict, why = _verdict_for(rel, verdicts)
            if "not classified" in why:
                unclassified.append(rel)
            if verdict == "cut":
                cut.append((rel, why))
                continue
            if child.is_dir():
                walk(rel)
            else:
                kept.append((rel, why))

    walk("")
    return {"kept": kept, "cut": cut, "hard_excluded": hard_excluded,
            "unclassified": unclassified}


def do_copy(source: Path, dest: Path, kept: List[Tuple[str, str]]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for rel, _why in kept:
        src = source / rel
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def zip_folder(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(folder).as_posix())


# -- post-mortem, assembled, not written by a model --------------------------

def build_postmortem(name: str, source: Path, report: dict,
                     recon_files: List[Path], plan_files: List[Path],
                     unify_file: Optional[Path]) -> str:
    lines = [f"# Post-mortem: {name}", "",
             f"- Source: `{source}`", f"- Archived: {_today()}",
             f"- Files kept: {len(report['kept'])}  |  "
             f"cut by a plan: {len(report['cut'])}  |  "
             f"hard-excluded (secrets/build/vendor dirs): {len(report['hard_excluded'])}",
             ""]
    if unify_file and unify_file.is_file():
        lines += ["## Senior assessment (Kimi, unified)", "",
                  unify_file.read_text(encoding="utf-8"), ""]
    for label, files in (("Recon digests", recon_files), ("Plan drafts", plan_files)):
        if not files:
            continue
        lines.append(f"## {label}")
        for f in files:
            lines += ["", f"### {f.name}", "", f.read_text(encoding="utf-8")]
        lines.append("")
    lines.append("## What's cut and why")
    lines.append("")
    if report["cut"]:
        for rel, why in report["cut"]:
            lines.append(f"- `{rel}` - {why}")
    else:
        lines.append("(nothing was cut)")
    lines += ["", "## Hard-excluded regardless of any plan "
                  "(secrets, vendor/build directories)", ""]
    lines += [f"- `{rel}`" for rel in report["hard_excluded"]] or ["(none found)"]
    if report["unclassified"]:
        lines += ["", "## Kept by default - no plan classified these "
                      "(review before trusting this archive is complete)", ""]
        lines += [f"- `{rel}`" for rel in report["unclassified"]]
    lines += ["", "## What's in this archive", ""]
    lines += [f"- `{rel}`" for rel, _ in report["kept"]] or ["(nothing kept)"]
    return "\n".join(lines)


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# -- main ----------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="the archaeology run name "
                    "(runs/crew/outbox/archaeology/<name>/)")
    ap.add_argument("--source", default=None, help="override the source folder "
                    "(default: read from the run's SUMMARY.json)")
    ap.add_argument("--dest", default=None, help="where to stage the archive "
                    "(default: C:/Users/user/Archive/<name>)")
    ap.add_argument("--apply", action="store_true", help="actually copy and "
                    "zip; without this, only prints what WOULD happen")
    ap.add_argument("--keep-staging", action="store_true", default=True)
    ap.add_argument("--no-keep-staging", dest="keep_staging", action="store_false",
                    help="delete the unzipped staged copy after zipping")
    args = ap.parse_args(argv)

    run_dir = Path(load_config().state_home) / "outbox" / "archaeology" / args.name
    if not run_dir.is_dir():
        print(f"no archaeology run at {run_dir}", file=sys.stderr)
        return 2
    summary_path = run_dir / "SUMMARY.json"
    source = Path(args.source) if args.source else None
    if not source and summary_path.is_file():
        source = Path(json.loads(summary_path.read_text(encoding="utf-8"))["folder"])
    if not source or not source.is_dir():
        print(f"could not determine a valid source folder (got {source})", file=sys.stderr)
        return 2

    plan_files = sorted(run_dir.glob("plan-*.md"))
    recon_files = sorted(run_dir.glob("recon-*.md"))
    unify_file = run_dir / "UNIFY.md"
    if not plan_files:
        print(f"no plan-*.md in {run_dir} - run archaeology_swarm.py through "
              f"the plan stage first", file=sys.stderr)
        return 2

    verdicts, used = merge_cut_lists(plan_files)
    print(f"cut list merged from {len(used)}/{len(plan_files)} plan file(s) "
          f"that included one: {', '.join(used) or '(none)'}")
    report = plan_copy(source, verdicts)
    print(f"\nsource: {source}")
    print(f"would keep {len(report['kept'])} file(s), cut {len(report['cut'])}, "
          f"hard-exclude {len(report['hard_excluded'])}, "
          f"{len(report['unclassified'])} unclassified (kept by default)")
    if report["cut"]:
        print("\nCUT:")
        for rel, why in report["cut"]:
            print(f"  - {rel}  ({why[:100]})")
    if report["unclassified"]:
        print("\nUNCLASSIFIED (kept by default, review these):")
        for rel in report["unclassified"][:20]:
            print(f"  - {rel}")

    if not args.apply:
        print("\n(dry run - pass --apply to actually copy and zip)")
        return 0

    dest = Path(args.dest) if args.dest else Path(
        f"C:/Users/user/Archive/{args.name}")
    if dest.exists():
        print(f"refusing to overwrite existing {dest}", file=sys.stderr)
        return 2
    print(f"\ncopying {len(report['kept'])} file(s) to {dest} ...")
    do_copy(source, dest, report["kept"])
    postmortem = build_postmortem(args.name, source, report, recon_files,
                                  plan_files, unify_file if unify_file.is_file() else None)
    (dest / "POSTMORTEM.md").write_text(postmortem, encoding="utf-8")
    (dest / "manifest.json").write_text(json.dumps({
        "name": args.name, "source": str(source), "archived": _today(),
        "kept": [r for r, _ in report["kept"]], "cut": report["cut"],
        "hard_excluded": report["hard_excluded"],
        "unclassified_kept": report["unclassified"]}, indent=2), encoding="utf-8")

    zip_path = dest.with_suffix(".zip")
    print(f"zipping {dest} -> {zip_path} ...")
    zip_folder(dest, zip_path)
    kept_bytes = sum((dest / r).stat().st_size for r, _ in report["kept"])
    zip_bytes = zip_path.stat().st_size
    ratio = (1 - zip_bytes / kept_bytes) * 100 if kept_bytes else 0.0
    print(f"\ndone. staged: {dest}  ({kept_bytes:,} bytes)")
    print(f"      zipped: {zip_path}  ({zip_bytes:,} bytes, {ratio:.0f}% smaller)")
    print(f"      source untouched: {source}")
    if not args.keep_staging:
        shutil.rmtree(dest)
        print(f"      staged copy removed (--no-keep-staging); zip is the "
              f"only remaining copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
