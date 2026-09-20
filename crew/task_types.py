"""Task types the crew accepts. Adding a type = a playbook file + an entry
here (spec normalization, preloaded context, gates, apply).

Preloading is deliberate (Agentless, arXiv 2407.01489): the harness gathers
the obvious context for free before the member starts, so the member spends
its request budget only on what the harness could not predict.
"""

import re
from pathlib import Path
from typing import Callable, Dict, List

from . import gates
from .config import Config, CrewError

EXCERPT_LINES = 6


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or "digest")[:60]


def _vault_root(cfg: Config, near: Path = None):
    for r in cfg.read_roots:
        if (r / ".obsidian").exists() and (near is None or r == near or r in near.parents):
            return r
    return None


def _folder(spec: dict, cfg: Config) -> Path:
    raw = spec.get("folder")
    if not raw:
        raise CrewError("spec.folder is required for this task type")
    p = Path(raw).resolve()
    if not p.is_dir() or not cfg.readable(p):
        raise CrewError(f"folder {raw} is not a readable directory in the crew's read roots")
    return p


def _md_notes(folder: Path, cfg: Config, skip: List[str]) -> List[Path]:
    return [p for p in sorted(folder.rglob("*.md"))
            if not cfg.denied(p.resolve())
            and p.relative_to(folder).as_posix() not in skip]


# -- vault_index --------------------------------------------------------------------

def vault_index_normalize(spec: dict, cfg: Config) -> dict:
    folder = _folder(spec, cfg)
    out_file = spec.get("output_file", "INDEX.md")
    if not cfg.writable(folder / out_file):
        raise CrewError(f"{folder / out_file} is outside the crew's write roots")
    spec["read_roots"] = [str(folder)]
    spec["output"] = {"root": str(folder), "files": [out_file]}
    spec.setdefault("exclude", [])
    return spec


def vault_index_preload(spec: dict, cfg: Config, toolbox) -> str:
    folder = Path(spec["folder"])
    out_file = spec["output"]["files"][0]
    notes = _md_notes(folder, cfg, [out_file] + spec["exclude"])
    parts, required = [], []
    for p in notes:
        rel = p.relative_to(folder).as_posix()
        required.append(rel.removesuffix(".md"))
        lines = [l for l in p.read_text(encoding="utf-8", errors="replace")
                 .splitlines() if l.strip()][:EXCERPT_LINES]
        toolbox.evidence.add(p.resolve().as_posix(), "\n".join(lines), opened=False)
        parts.append(f"--- {rel} ---\n" + "\n".join(lines))
    spec["_required_links"] = required
    return (f"FOLDER: {folder.as_posix()}\nOUTPUT FILE: {out_file}\n"
            f"NOTES YOU MUST LINK ({len(required)}): "
            + ", ".join(f"[[{r}]]" for r in required)
            + "\n\nINVENTORY (first lines of each note):\n\n" + "\n\n".join(parts))


def vault_index_gates(files: Dict[str, str], spec: dict, cfg: Config, toolbox) -> List[dict]:
    folder = Path(spec["folder"])
    out_file = spec["output"]["files"][0]
    steps = [gates.output_paths(files, spec["output"]["files"], folder, cfg.writable)]
    text = files.get(out_file, "")
    if text:
        steps += [gates.frontmatter(text, ("title", "tags", "last_updated"), out_file),
                  gates.wikilinks_resolve(text, folder, None, out_file),
                  gates.coverage(text, spec.get("_required_links", []), out_file),
                  gates.grounded(text, toolbox, out_file)]
        steps += gates.acceptance(text, spec, toolbox, out_file)
    return steps


# -- research_digest ----------------------------------------------------------------

def research_digest_normalize(spec: dict, cfg: Config) -> dict:
    if not (spec.get("instructions") or "").strip():
        raise CrewError("research_digest needs instructions (the question to answer)")
    roots = spec.get("read_roots") or [str(r) for r in cfg.read_roots]
    for r in roots:
        if not cfg.readable(Path(r)):
            raise CrewError(f"read root {r} is outside the crew's read roots")
    spec["read_roots"] = [str(Path(r).resolve()) for r in roots]
    out = spec.get("output") or {}
    root = Path(out.get("root") or cfg.state_home / "outbox").resolve()
    name = (out.get("files") or [_slug(spec.get("title") or spec["instructions"]) + ".md"])[0]
    if not cfg.writable(root / name):
        raise CrewError(f"{root / name} is outside the crew's write roots")
    spec["output"] = {"root": str(root), "files": [name]}
    return spec


def research_digest_preload(spec: dict, cfg: Config, toolbox) -> str:
    parts = ["READ ROOTS (relative paths resolve against the first):\n"
             + "\n".join(f"- {r}" for r in spec["read_roots"])]
    for raw in spec.get("context_files", []) or []:
        try:
            parts.append("PRELOADED " + toolbox.read_file(raw, 1, 200))
        except Exception as e:  # noqa: BLE001 - reported to the member
            parts.append(f"PRELOADED {raw}: unavailable ({e})")
    return f"OUTPUT FILE: {spec['output']['files'][0]}\n\n" + "\n\n".join(parts)


def research_digest_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    text = files.get(out_file, "")
    if text:
        vault = _vault_root(cfg)
        steps += [gates.frontmatter(text, ("title", "tags"), out_file),
                  gates.cited_lines(text, toolbox, out_file),
                  gates.grounded(text, toolbox, out_file),
                  gates.absence_claims(text, toolbox, out_file),
                  gates.wikilinks_resolve(text, root, vault, out_file)]
        steps += gates.acceptance(text, spec, toolbox, out_file)
    return steps


# -- organize_plan ---------------------------------------------------------------------

def organize_plan_normalize(spec: dict, cfg: Config) -> dict:
    folder = _folder(spec, cfg)
    spec["read_roots"] = [str(folder)]
    spec["output"] = {"root": str((cfg.state_home / "outbox").resolve()),
                      "files": ["plan.json"]}
    return spec


def organize_plan_preload(spec: dict, cfg: Config, toolbox) -> str:
    folder = Path(spec["folder"])
    rows = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not cfg.denied(p.resolve()):
            rows.append(f"{p.relative_to(folder).as_posix()}  ({p.stat().st_size} B)")
    listing = "\n".join(rows[:400])
    toolbox.evidence.add(folder.as_posix(), listing, opened=False)
    return f"FOLDER: {folder.as_posix()}\nOUTPUT FILE: plan.json\n\nFILES:\n{listing}"


def organize_plan_gates(files, spec, cfg, toolbox):
    root = Path(spec["folder"])
    steps = [gates.output_paths(files, ["plan.json"],
                                Path(spec["output"]["root"]), cfg.writable)]
    if "plan.json" in files:
        steps.append(gates.organize_plan(files["plan.json"], root,
                                         lambda p: cfg.readable(p), "plan.json"))
    return steps


# -- test_triage -----------------------------------------------------------------------

def test_triage_normalize(spec: dict, cfg: Config) -> dict:
    root = Path(spec.get("project_root") or "").resolve()
    if not root.is_dir() or not cfg.readable(root):
        raise CrewError("spec.project_root must be a readable directory in the crew's read roots")
    name = spec.get("test_command", "pytest")
    commands = {k: v for k, v in (cfg.data.get("test_commands") or {}).items()
                if isinstance(v, dict)}
    if name not in commands:
        raise CrewError(f"test_command must be one of {sorted(commands)} "
                        f"(the harness runs it; the member cannot choose a command)")
    spec["test_command"] = name
    spec["read_roots"] = [str(root)]
    out = spec.get("output") or {}
    file = (out.get("files") or [f"test-triage-{root.name}.md"])[0]
    out_root = Path(out.get("root") or cfg.state_home / "outbox").resolve()
    if not cfg.writable(out_root / file):
        raise CrewError(f"{out_root / file} is outside the crew's write roots")
    spec["output"] = {"root": str(out_root), "files": [file]}
    return spec


def run_test_command(spec: dict, cfg: Config) -> str:
    """The HARNESS runs the project's own test suite; the member never gets to
    choose or edit the command. Its output is the evidence the report is
    graded against."""
    import subprocess
    import sys as _sys
    entry = (cfg.data.get("test_commands") or {})[spec["test_command"]]
    root = Path(spec["project_root"])
    argv = [a.replace("{python}", _sys.executable)
             .replace("{project_root}", str(root)) for a in entry["argv"]]
    try:
        proc = subprocess.run(argv, cwd=str(root), capture_output=True, text=True,
                              timeout=int(entry.get("timeout_s", 900)),
                              encoding="utf-8", errors="replace")
        out = (proc.stdout or "") + (proc.stderr or "")
        return f"$ {' '.join(argv)}\n(exit {proc.returncode})\n{out}"
    except subprocess.TimeoutExpired:
        return f"$ {' '.join(argv)}\n(TIMEOUT after {entry.get('timeout_s', 900)}s)"
    except OSError as e:
        return f"$ {' '.join(argv)}\n(could not run: {e})"


RUN_LOG_CHARS = 7000   # tail: failures and the summary live at the end


def test_triage_preload(spec: dict, cfg: Config, toolbox) -> str:
    log = run_test_command(spec, cfg)
    jdir = spec.get("_job_dir")
    if jdir:
        Path(jdir, "run_log.txt").write_text(log, encoding="utf-8")
    spec["_run_log"] = log[-RUN_LOG_CHARS:]
    toolbox.evidence.add("run_log", spec["_run_log"])
    return (f"PROJECT: {spec['project_root']}\nOUTPUT FILE: "
            f"{spec['output']['files'][0]}\n\nTEST RUN OUTPUT (the harness ran "
            f"this; it is your evidence — cite it as [src: run_log]):\n\n"
            f"{spec['_run_log']}")


def test_triage_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    text = files.get(out_file, "")
    if text:
        log = spec.get("_run_log", "")
        steps += [gates.frontmatter(text, ("title", "tags"), out_file),
                  gates.reported_failures_exist(text, log, out_file),
                  gates.quotes_the_totals(text, log, out_file),
                  gates.cited_lines(text, toolbox, out_file),
                  gates.grounded(text, toolbox, out_file),
                  gates.absence_claims(text, toolbox, out_file)]
        steps += gates.acceptance(text, spec, toolbox, out_file)
    return steps


# -- ui_sweep --------------------------------------------------------------------------

def ui_sweep_normalize(spec: dict, cfg: Config) -> dict:
    app = Path(spec.get("app") or "").resolve()
    if not app.is_file() or not cfg.readable(app.parent):
        raise CrewError("spec.app must be an executable inside the crew's read roots")
    spec["app"] = str(app)
    if spec.get("watch_log"):
        log = Path(spec["watch_log"]).resolve()
        if not cfg.readable(log.parent):
            raise CrewError("spec.watch_log is outside the crew's read roots")
        spec["watch_log"] = str(log)
    spec["read_roots"] = [str(app.parent.parent if app.parent.name == "dist"
                              else app.parent)]
    out = spec.get("output") or {}
    file = (out.get("files") or [f"ui-sweep-{app.stem}.md"])[0]
    root = Path(out.get("root") or cfg.state_home / "outbox").resolve()
    if not cfg.writable(root / file):
        raise CrewError(f"{root / file} is outside the crew's write roots")
    spec["output"] = {"root": str(root), "files": [file]}
    spec.setdefault("max_controls", 40)
    spec.setdefault("watch_dir", str(Path(spec["app"]).parent))
    spec.setdefault("seed_text", "The quick brown fox jumps over the lazy dog. "
                                 "Don't forget Kris's notes: one, two, three.")
    return spec


SWEEP_LOG_CHARS = 9000


def ui_sweep_preload(spec: dict, cfg: Config, toolbox) -> str:
    """The HARNESS drives the app: every control is highlighted in the test
    color for half a second (so a watching human sees what is coming) and
    then pressed. The member only reads the resulting log."""
    import subprocess
    import sys as _sys
    jdir = Path(spec.get("_job_dir") or ".")
    events = jdir / "sweep.jsonl"
    argv = [_sys.executable, str(Path(__file__).resolve().parent / "runners" / "ui_sweep.py"),
            spec["app"], "--out", str(events), "--max", str(spec["max_controls"]),
            "--pre", str(spec.get("pre_click_seconds", 0.5)),
            "--settle", str(spec.get("settle_seconds", 0.7)),
            # Kris, 2026-09-19: the fixed settle time was too short, so presses
            # landed while the previous window was still opening. These are the
            # readiness bounds, not a guess at how long an action takes.
            "--settle-max", str(spec.get("settle_max_seconds", 12)),
            "--quiet", str(spec.get("quiet_seconds", 0.6)),
            "--launch-wait", str(spec.get("launch_wait_seconds", 90))]
    if spec.get("watch_log"):
        argv += ["--watch-log", spec["watch_log"]]
    if spec.get("watch_dir"):
        argv += ["--watch-dir", spec["watch_dir"]]
    if spec.get("seed_text"):
        # Kris: Save, Copy and the formatting buttons do nothing on an empty
        # document, so the sweep types real content in first.
        argv += ["--seed-text", spec["seed_text"]]
    if spec.get("beep"):
        argv += ["--beep"]
    if spec.get("include_destructive"):
        argv += ["--include-destructive"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=1800,
                              encoding="utf-8", errors="replace")
        log = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        log = "(sweep timed out after 1800s)"
    (jdir / "sweep_log.txt").write_text(log, encoding="utf-8")
    spec["_run_log"] = log[-SWEEP_LOG_CHARS:]
    toolbox.evidence.add("sweep_log", spec["_run_log"])
    return (f"APP: {spec['app']}\nOUTPUT FILE: {spec['output']['files'][0]}\n\n"
            f"UI SWEEP RESULT (the harness pressed each control after showing an "
            f"orange highlight; cite it as [src: sweep_log]):\n\n"
            f"{spec['_run_log']}")


def ui_sweep_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    text = files.get(out_file, "")
    if text:
        log = spec.get("_run_log", "")
        steps += [gates.frontmatter(text, ("title", "tags"), out_file),
                  gates.named_things_exist(text, log, "control", out_file),
                  gates.quotes_the_totals(text, log, out_file),
                  gates.reports_interference(text, log, out_file),
                  gates.reports_stalls(text, log, out_file),
                  gates.cited_lines(text, toolbox, out_file),
                  gates.grounded(text, toolbox, out_file),
                  gates.absence_claims(text, toolbox, out_file)]
        steps += gates.acceptance(text, spec, toolbox, out_file)
    return steps


# -- code_task ---------------------------------------------------------------------------
#
# The first task type whose output is EXECUTED. Everything about it is built
# around that: the contract is written so the module needs nothing from the real
# machine (devices, audio, files are passed in as callables), crew/codetask.py
# refuses to run source that reaches outside a pure function, and the tests that
# decide the outcome are ours and are never shown to the member.

CONTRACT_CHARS = 12000


def _contract_text(spec: dict, cfg: Config) -> str:
    path = Path(spec["contract"]).resolve()
    if not path.is_file() or not cfg.readable(path):
        raise CrewError(f"spec.contract {spec['contract']} is not a readable file "
                        f"in the crew's read roots")
    return path.read_text(encoding="utf-8")[:CONTRACT_CHARS]


def _hidden_tests(spec: dict, cfg: Config) -> Dict[str, str]:
    out = {}
    for raw in spec.get("hidden_tests") or []:
        path = Path(raw).resolve()
        if not path.is_file():
            raise CrewError(f"hidden test {raw} does not exist")
        out[path.name] = path.read_text(encoding="utf-8")
    return out


def _workspace_modules(spec: dict, cfg: Config) -> Dict[str, str]:
    """Modules an earlier task already got accepted, so this one can build on
    them (Kris: the teams should build on each other's actions)."""
    out = {}
    for raw in spec.get("depends_modules") or []:
        path = Path(raw).resolve()
        if not path.is_file() or not cfg.readable(path):
            raise CrewError(f"dependency module {raw} is not readable")
        out[path.name] = path.read_text(encoding="utf-8")
    return out


def code_task_normalize(spec: dict, cfg: Config) -> dict:
    module = (spec.get("module") or "").strip()
    if not module or "/" in module or "\\" in module or not module.endswith(".py"):
        raise CrewError("spec.module must be a single .py file name, e.g. devices.py")
    if not spec.get("contract"):
        raise CrewError("spec.contract is required: the file stating the API and behavior")
    _contract_text(spec, cfg)                     # validate now, not at run time
    _hidden_tests(spec, cfg)
    _workspace_modules(spec, cfg)
    spec["api"] = [str(a) for a in (spec.get("api") or [])]
    if not spec["api"]:
        raise CrewError("spec.api must list the public names the module must define")
    spec["read_roots"] = [str(Path(spec["contract"]).resolve().parent)]
    for raw in spec.get("depends_modules") or []:
        spec["read_roots"].append(str(Path(raw).resolve().parent))
    root = Path((spec.get("output") or {}).get("root")
                or cfg.state_home / "outbox" / "workspace").resolve()
    if not cfg.writable(root / module):
        raise CrewError(f"{root / module} is outside the crew's write roots")
    spec["output"] = {"root": str(root), "files": [module]}
    spec.setdefault("test_timeout_s", 180)
    return spec


def code_task_preload(spec: dict, cfg: Config, toolbox) -> str:
    contract = _contract_text(spec, cfg)
    toolbox.evidence.add("contract", contract)
    deps = _workspace_modules(spec, cfg)
    parts = [f"OUTPUT FILE: {spec['output']['files'][0]}",
             "",
             "CONTRACT (this is the specification; satisfy it exactly. Cite it as "
             "[src: contract] if you explain a decision):",
             "",
             contract]
    if deps:
        parts += ["", "ALREADY ACCEPTED MODULES you may import by name (they are "
                      "on the path when your code is tested; do not rewrite them):"]
        for name, src in deps.items():
            toolbox.evidence.add(f"module:{name}", src)
            parts += ["", f"----- {name} -----", src[:6000]]
    parts += ["", "HOW YOUR WORK IS JUDGED: the harness runs tests you never see "
                  "against your module, in a throwaway directory. Your source is "
                  "checked first and REFUSED if it imports anything outside the "
                  "contract's allowlist, calls eval/exec/open, or reaches the "
                  "filesystem, network or registry. Anything external is passed "
                  "into your functions as an argument - that is what makes the "
                  "module testable. Write the whole file every time; no diffs, no "
                  "placeholders, no TODOs."]
    return "\n".join(parts)


def code_task_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    source = files.get(out_file, "")
    if source:
        deps = _workspace_modules(spec, cfg)
        dep_names = sorted(n[:-3] for n in deps)
        steps += [gates.ascii_only(source, out_file),
                  gates.module_is_safe(source, out_file, dep_names),
                  gates.defines_api(source, spec["api"], out_file),
                  gates.not_stubbed(source, spec["api"], out_file)]
        if all(st["ok"] for st in steps):
            hidden = _hidden_tests(spec, cfg)
            if hidden:
                steps.append(gates.hidden_tests_pass(
                    {out_file: source, **deps}, hidden,
                    int(spec["test_timeout_s"]), out_file, dep_names))
    return steps


# -- code_tests --------------------------------------------------------------------------

def code_tests_normalize(spec: dict, cfg: Config) -> dict:
    name = (spec.get("test_file") or "").strip()
    if not name.startswith("test_") or not name.endswith(".py") or "/" in name:
        raise CrewError("spec.test_file must be a single file named test_*.py")
    if not spec.get("contract"):
        raise CrewError("spec.contract is required")
    _contract_text(spec, cfg)
    mods = _workspace_modules(spec, cfg)
    if not mods:
        raise CrewError("spec.depends_modules must name the accepted module(s) "
                        "these tests run against")
    spec["read_roots"] = [str(Path(spec["contract"]).resolve().parent)]
    spec.setdefault("min_tests", 6)
    spec.setdefault("test_timeout_s", 180)
    root = Path((spec.get("output") or {}).get("root")
                or cfg.state_home / "outbox" / "workspace" / "tests").resolve()
    if not cfg.writable(root / name):
        raise CrewError(f"{root / name} is outside the crew's write roots")
    spec["output"] = {"root": str(root), "files": [name]}
    return spec


def code_tests_preload(spec: dict, cfg: Config, toolbox) -> str:
    contract = _contract_text(spec, cfg)
    toolbox.evidence.add("contract", contract)
    mods = _workspace_modules(spec, cfg)
    names = ", ".join(sorted(m[:-3] for m in mods))
    parts = [f"OUTPUT FILE: {spec['output']['files'][0]}", "",
             f"You are the TESTER. Another crew member wrote the module; you write "
             f"tests for it from the CONTRACT, not from their code. You are not "
             f"shown their source on purpose: tests written by reading an "
             f"implementation only prove the implementation agrees with itself.",
             "", f"Import it as: import {names}", "",
             "CONTRACT:", "", contract, "",
             f"RULES: at least {spec['min_tests']} test functions named test_*; "
             f"pure asserts; no imports beyond pytest and the module; no network, "
             f"no files, no sleeping; each test states in its name or docstring "
             f"which contract rule it checks. The harness runs your tests against "
             f"the real module. If they fail, either the module is wrong or your "
             f"test is - both are reported, and a senior decides."]
    return "\n".join(parts)


def code_tests_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    source = files.get(out_file, "")
    if source:
        mods = _workspace_modules(spec, cfg)
        mod_names = sorted(n[:-3] for n in mods)
        steps += [gates.ascii_only(source, out_file),
                  gates.test_file_is_safe(source, out_file, mod_names),
                  gates.enough_tests(source, int(spec["min_tests"]), out_file)]
        if all(st["ok"] for st in steps):
            steps.append(gates.tests_run_green(
                mods, {out_file: source}, int(spec["test_timeout_s"]), out_file,
                mod_names))
    return steps


TASK_TYPES: Dict[str, Dict[str, object]] = {
    "code_task": {
        "description": "Write one self-contained Python module against a contract. The harness executes it against tests the member never sees, after refusing any source that reaches outside a pure function.",
        "spec": {"module": "required: the file to write, e.g. devices.py",
                 "contract": "required: path to the contract file stating the API and behavior",
                 "api": "required: list of public names the module must define",
                 "hidden_tests": "optional: paths to test files the member never sees; they decide the outcome",
                 "depends_modules": "optional: paths to already-accepted modules this one may import",
                 "test_timeout_s": "optional, default 180",
                 "instructions": "optional: emphasis for this attempt"},
        "gates": "output path, ASCII only, the safety scan, the contract's API exists, no stubs, hidden tests pass",
        "apply": "writes the module into the crew workspace (never into a real project)",
        "normalize": code_task_normalize, "preload": code_task_preload,
        "gates_fn": code_task_gates,
    },
    "code_tests": {
        "description": "Write tests for another member's accepted module, from the contract alone, without being shown the implementation.",
        "spec": {"test_file": "required: test_*.py to write",
                 "contract": "required: the same contract the author worked from",
                 "depends_modules": "required: the accepted module(s) under test",
                 "min_tests": "optional, default 6",
                 "instructions": "optional"},
        "gates": "output path, ASCII only, the safety scan, enough test functions, the tests run green against the real module",
        "apply": "writes the test file into the crew workspace",
        "normalize": code_tests_normalize, "preload": code_tests_preload,
        "gates_fn": code_tests_gates,
    },
    "ui_sweep": {
        "description": "The harness launches a Windows app and presses every control (each highlighted in orange for half a second first, so a human can watch); the member reports what broke, what did nothing, and what it could not reach.",
        "spec": {"app": "required: the .exe to sweep (inside a crew read root)",
                 "watch_log": "optional: the app's log file, so errors it writes are attributed to the control that caused them",
                 "max_controls": "optional, default 40",
                 "settle_max_seconds": "optional, default 12: how long to wait for the app to answer and the desktop to stop changing after each press before calling it stalled",
                 "seed_text": "optional: text typed into the app's first editable control before the sweep, so Save/Copy/formatting act on real content (a default is provided)",
                 "include_destructive": "optional: also press Delete/Clear/Exit-style controls (sandbox only)",
                 "instructions": "optional: what to focus on"},
        "gates": "output path, frontmatter, no invented control names, the sweep's summary line quoted verbatim, interference and stalls reported, every item cited, numbers grounded, absence claims evidenced",
        "apply": "writes the sweep report to the output root",
        "normalize": ui_sweep_normalize, "preload": ui_sweep_preload,
        "gates_fn": ui_sweep_gates,
    },

    "test_triage": {
        "description": "The harness runs a project's own test suite; the member turns the output into a triage report (what failed, grouped, with a likely cause and the code it points at).",
        "spec": {"project_root": "required: the project to test (a crew read root)",
                 "test_command": "optional: a key from config test_commands (default pytest)",
                 "instructions": "optional: what to focus on",
                 "output": "optional {root, files:[name.md]}; default runs/crew/outbox"},
        "gates": "output path, frontmatter, no invented test names, the run's summary line quoted verbatim, every item cited, numbers grounded in the run output or files read",
        "apply": "writes the triage report to the output root",
        "normalize": test_triage_normalize, "preload": test_triage_preload,
        "gates_fn": test_triage_gates,
    },
    "vault_index": {
        "description": "Build/refresh a Map-of-Content note (INDEX.md) for one vault folder.",
        "spec": {"folder": "required: folder to index (inside a write root)",
                 "output_file": "optional, default INDEX.md",
                 "exclude": "optional: note paths (relative) to leave out"},
        "gates": "output path, frontmatter, wikilinks resolve, every note linked, numbers grounded in what was read",
        "apply": "writes the index into the folder (previous version backed up in the job folder)",
        "normalize": vault_index_normalize, "preload": vault_index_preload,
        "gates_fn": vault_index_gates,
    },
    "research_digest": {
        "description": "Answer a question from workspace files (and allowlisted web pages) as a cited digest other agents can use.",
        "spec": {"instructions": "required: the question and what the digest is for",
                 "read_roots": "optional: subset of crew read roots to search",
                 "context_files": "optional: files to preload (saves requests)",
                 "output": "optional {root, files:[name.md]}; default runs/crew/outbox",
                 "acceptance": "optional {must_mention: [...]}"},
        "gates": "output path, frontmatter, every item cited, citations were actually opened, numbers grounded in cited text, wikilinks resolve",
        "apply": "writes the digest to the output root",
        "normalize": research_digest_normalize, "preload": research_digest_preload,
        "gates_fn": research_digest_gates,
    },
    "organize_plan": {
        "description": "Propose (never perform) moves/renames/tags for one folder as plan.json.",
        "spec": {"folder": "required: folder to organize",
                 "instructions": "optional: what 'organized' means here"},
        "gates": "plan schema, sources exist, targets stay inside and do not collide",
        "apply": "saves the approved plan to the outbox; moves are NOT executed in v1 (a later deterministic mover will)",
        "normalize": organize_plan_normalize, "preload": organize_plan_preload,
        "gates_fn": organize_plan_gates,
    },
}


def get(task_type: str) -> Dict[str, object]:
    if task_type not in TASK_TYPES:
        raise CrewError(f"unknown task_type {task_type!r}; known: {', '.join(TASK_TYPES)}")
    return TASK_TYPES[task_type]


def public_catalog() -> List[dict]:
    return [{"task_type": k, **{f: v[f] for f in ("description", "spec", "gates", "apply")}}
            for k, v in TASK_TYPES.items()]


PreloadFn = Callable[[dict, Config, object], str]
