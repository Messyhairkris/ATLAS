"""Assemble the accepted photo_tools modules into the image_convert crate.

    python crew/campaigns/assemble_photo_tools.py [--dest DIR] [--check-only]

Crew output never reaches a project directly: this is the PA's step. It copies the
accepted modules (runs/crew/outbox/workspace/photo_tools/*.rs) into DEST/src, the
specification tests (crew/hidden_tests/rs_photo_tools/hidden_*.rs) and the crew's own
tests (workspace/photo_tools/tests/test_*.rs) into DEST/tests, then runs the mechanical
clean-up (rustfmt, clippy --fix) and keeps it only if every test still passes, then a
release build. lib.rs, main.rs, Cargo.toml and README.md in DEST are the PA's and are
not touched. CARGO_TARGET_DIR stays on the local disk even when DEST is a share.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "runs" / "crew" / "outbox" / "workspace" / "photo_tools"
HIDDEN = ROOT / "crew" / "hidden_tests" / "rs_photo_tools"
DEST = Path(r"\\WILKINSKNOWSYOU\Users\Public\Documents\image_convert")
TARGET = ROOT / "runs" / "crew" / "rs_target" / "image_convert"
MODULES = ["ascii", "cli", "contour", "despeckle", "dither", "dodge", "effects", "halftone",
           "hatch", "kmeans", "lineart", "luma", "options", "smooth", "sobel", "svg", "vector"]


def cargo(dest: Path, *args: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    env = {**os.environ, "CARGO_TARGET_DIR": str(TARGET), "CARGO_BUILD_JOBS": "2",
           "CARGO_TERM_COLOR": "never"}
    return subprocess.run(["cargo", *args, "--manifest-path", str(dest / "Cargo.toml")],
                          capture_output=True, text=True, env=env, timeout=timeout)


def tests_pass(dest: Path) -> tuple:
    r = cargo(dest, "test", "--all-targets")
    lines = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith("test result:")]
    passed = sum(int(l.split(" passed")[0].split()[-1]) for l in lines)
    failed = sum(int(l.split(" failed")[0].split()[-1]) for l in lines)
    return r.returncode == 0, passed, failed, (r.stdout + r.stderr)[-3000:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(DEST))
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    dest = Path(a.dest)
    missing = [m for m in MODULES if not (WORK / f"{m}.rs").is_file()]
    if missing:
        print("not accepted yet:", ", ".join(missing))
        return 2
    (dest / "src").mkdir(parents=True, exist_ok=True)
    (dest / "tests").mkdir(parents=True, exist_ok=True)
    for m in MODULES:
        shutil.copyfile(WORK / f"{m}.rs", dest / "src" / f"{m}.rs")
    for t in sorted(HIDDEN.glob("hidden_*.rs")):
        shutil.copyfile(t, dest / "tests" / t.name)
    for t in sorted((WORK / "tests").glob("test_*.rs")):
        shutil.copyfile(t, dest / "tests" / t.name)
    ok, passed, failed, tail = tests_pass(dest)
    print(f"as accepted: {'PASS' if ok else 'FAIL'} - {passed} passed, {failed} failed")
    if not ok:
        print(tail)
        return 1
    if a.check_only:
        return 0
    backup = {p: p.read_text(encoding="utf-8") for p in (dest / "src").glob("*.rs")}
    backup.update({p: p.read_text(encoding="utf-8") for p in (dest / "tests").glob("*.rs")})
    fmt = subprocess.run(["rustfmt", "--edition", "2021", *map(str, backup)],
                         capture_output=True, text=True)
    fix = cargo(dest, "clippy", "--fix", "--allow-dirty", "--allow-no-vcs", "--all-targets")
    ok2, passed2, failed2, tail2 = tests_pass(dest)
    if not ok2 or passed2 != passed:
        for p, text in backup.items():
            p.write_text(text, encoding="utf-8")
        print(f"clean-up reverted: tests went to {passed2} passed, {failed2} failed")
    else:
        changed = sum(1 for p, t in backup.items() if p.read_text(encoding="utf-8") != t)
        print(f"rustfmt + clippy --fix kept: {changed} file(s) changed, tests still "
              f"{passed2} passed (rustfmt rc {fmt.returncode}, clippy rc {fix.returncode})")
    lint = cargo(dest, "clippy", "--all-targets")
    warnings = [l for l in lint.stderr.splitlines() if l.startswith("warning:")
                and "generated" not in l]
    print(f"clippy after clean-up: {len(warnings)} warning(s)")
    for w in warnings[:25]:
        print("  " + w)
    rel = cargo(dest, "build", "--release")
    exe = TARGET / "release" / "photo_tools.exe"
    print(f"release build: {'ok' if rel.returncode == 0 else 'FAILED'} -> {exe}")
    if rel.returncode != 0:
        print(rel.stderr[-3000:])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
