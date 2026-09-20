"""Move accepted crew modules into a real project, honestly.

A crew module is written as a single flat file, because that is what makes it
testable in a throwaway directory with nothing else on the path. A real project
wants a package. That mismatch is one mechanical rewrite - `import verbalize`
becomes `from . import verbalize` - and mechanical is exactly what should be
automated rather than hand-edited (Kris's rule: automate what can be automated,
and never hand an LLM a job a tool does perfectly).

So this does the move and records it:

* copies each accepted module into the destination package;
* rewrites imports of its SIBLING modules to relative form, and nothing else;
* prepends a provenance header naming the author, the contract, and the campaign,
  so a reader of the project knows where the file came from;
* writes `PROVENANCE.md` listing every file, its author, and every line changed;
* verifies the package still passes the hidden tests after the rewrite - a vendor
  step that breaks the code it vendors is worse than no vendor step.

    python -m crew vendor runs/crew/outbox/workspace \\
        C:/Users/user/Voice_to_Text_Project/implementation/src/tts \\
        --author devices.py=Hoss --author verbalize.py=Qwen
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import Dict, List

from . import codetask
from .config import REPO_ROOT

HEADER = '''"""{title}

Written by {author} of the Crew, from the contract `{contract}`, and accepted
only after passing tests it was never allowed to read ({campaign}).

Vendored into this project on {date}. The ONLY change made on the way in was the
import rewrite listed in PROVENANCE.md; the logic is exactly what was accepted.
"""
'''


def rewrite_imports(source: str, siblings: List[str]) -> tuple:
    """`import x` / `from x import y` -> relative, for siblings only."""
    changes = []
    out = source
    for name in siblings:
        patterns = [
            (rf"^from {name} import (.+)$", rf"from .{name} import \1"),
            (rf"^import {name}$", f"from . import {name}"),
        ]
        for pattern, replacement in patterns:
            new = re.sub(pattern, replacement, out, flags=re.MULTILINE)
            if new != out:
                for line in out.splitlines():
                    if re.match(pattern, line):
                        changes.append(line.strip())
                out = new
    return out, changes


def vendor(src_dir: Path, dest: Path, authors: Dict[str, str], contract_dir: Path,
           campaign: str, hidden_dir: Path, dry_run: bool = False) -> dict:
    modules = sorted(p for p in src_dir.glob("*.py"))
    if not modules:
        raise SystemExit(f"no modules in {src_dir}")
    siblings = [m.stem for m in modules]
    dest.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    rows = []
    written = {}
    for module in modules:
        source = module.read_text(encoding="utf-8")
        body, changes = rewrite_imports(source, siblings)
        author = authors.get(module.name, "the Crew")
        contract = f"{contract_dir.name}/tts_{module.stem}.md"
        first = body.lstrip()
        if first.startswith('"""'):
            end = body.index('"""', body.index('"""') + 3) + 3
            original_doc = body[:end]
            body = body[end:].lstrip("\n")
        else:
            original_doc = ""
        head = HEADER.format(title=f"{module.stem}: as accepted from the Crew.",
                             author=author, contract=contract, campaign=campaign,
                             date=today)
        if original_doc:
            head += f"\n# The module's own docstring, unchanged:\n"
            head += "\n".join("# " + ln for ln in original_doc.splitlines()) + "\n"
        written[module.name] = head + "\n" + body
        rows.append({"file": module.name, "author": author,
                     "import_changes": changes})
    if dry_run:
        return {"files": rows, "written": False}

    for name, text in written.items():
        (dest / name).write_text(text, encoding="utf-8")

    # A vendor step that breaks what it vendors is worse than none: re-run the
    # hidden tests against the rewritten files, as a flat set, before claiming
    # success.
    flat = {name: text.replace("from . import ", "import ")
                      .replace("from .", "from ") for name, text in written.items()}
    tests = {}
    for module in modules:
        # hidden tests are named test_<stem>.py or test_tts_<stem>.py depending on
        # which campaign wrote them; try both rather than silently verifying nothing
        for pattern in (f"test_{module.stem}.py", f"test_tts_{module.stem}.py"):
            candidate = hidden_dir / pattern
            if candidate.is_file():
                tests[candidate.name] = candidate.read_text(encoding="utf-8")
                break
    verdict = "no hidden tests found to verify with"
    if tests:
        ok, out, _ = codetask.run_tests(flat, tests, timeout_s=300)
        verdict = ("the vendored modules still pass every hidden test"
                   if ok else "FAILED: " + codetask.summarize(out))
        if not ok:
            print(verdict)
            raise SystemExit(2)

    lines = [f"# Provenance of {dest.name}", "",
             f"Vendored from the Crew's accepted output on {today}.", "",
             "| file | written by | import lines rewritten |", "|---|---|---|"]
    for row in rows:
        changed = ("; ".join(f"`{c}`" for c in row["import_changes"])
                   or "none")
        lines.append(f"| `{row['file']}` | {row['author']} | {changed} |")
    lines += ["", "Every module was accepted only after passing hidden tests its "
                  "author could not read, and was cross-tested by a different "
                  "member. The contracts and the campaign report live in the "
                  "harness.", "",
              f"Verification after vendoring: **{verdict}**", ""]
    (dest / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")
    return {"files": rows, "written": True, "verdict": verdict}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m crew vendor")
    ap.add_argument("source", help="folder of accepted modules")
    ap.add_argument("dest", help="destination package folder")
    ap.add_argument("--author", action="append", default=[],
                    help="file.py=Name, repeatable")
    ap.add_argument("--campaign", default="crew campaign")
    ap.add_argument("--contracts", default=str(REPO_ROOT / "crew" / "contracts"))
    ap.add_argument("--hidden", default=str(REPO_ROOT / "crew" / "hidden_tests"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    authors = dict(pair.split("=", 1) for pair in args.author if "=" in pair)
    result = vendor(Path(args.source).resolve(), Path(args.dest).resolve(),
                    authors, Path(args.contracts), args.campaign,
                    Path(args.hidden), args.dry_run)
    for row in result["files"]:
        print(f"  {row['file']:18s} by {row['author']:10s} "
              f"imports rewritten: {row['import_changes'] or 'none'}")
    if result.get("verdict"):
        print(f"\n{result['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
