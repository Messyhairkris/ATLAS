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


# -- clerks: scout, log_clerk, completion_audit -----------------------------------------
#
# Crush-lite's bounded read-only workers (.crush/lite/workers), moved into the
# crew on 2026-09-25 so they run under a request budget and gates instead of
# as open-ended Crush sessions. Each answers ONE question, judges nothing, and
# its output is Shadow Knowledge: attributable, non-authoritative.

def _report_output(spec: dict, cfg: Config, default_name: str) -> dict:
    out = spec.get("output") or {}
    root = Path(out.get("root") or cfg.state_home / "outbox").resolve()
    name = (out.get("files") or [default_name])[0]
    if not cfg.writable(root / name):
        raise CrewError(f"{root / name} is outside the crew's write roots")
    return {"root": str(root), "files": [name]}


def _readable_file(raw: str, cfg: Config, what: str) -> Path:
    p = Path(raw or "").resolve()
    if not raw or not p.is_file() or not cfg.readable(p):
        raise CrewError(f"{what} {raw!r} is not a readable file in the crew's read roots")
    return p


def scout_normalize(spec: dict, cfg: Config) -> dict:
    if not (spec.get("instructions") or "").strip():
        raise CrewError("scout needs instructions: what to locate")
    roots = spec.get("read_roots") or [str(r) for r in cfg.read_roots]
    for r in roots:
        if not cfg.readable(Path(r)):
            raise CrewError(f"read root {r} is outside the crew's read roots")
    spec["read_roots"] = [str(Path(r).resolve()) for r in roots]
    spec["output"] = _report_output(
        spec, cfg, "scout-" + _slug(spec.get("title") or spec["instructions"]) + ".md")
    return spec


def scout_preload(spec: dict, cfg: Config, toolbox) -> str:
    return research_digest_preload(spec, cfg, toolbox)


def scout_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    steps = [gates.output_paths(files, spec["output"]["files"],
                                Path(spec["output"]["root"]), cfg.writable)]
    text = files.get(out_file, "")
    if text:
        steps += [gates.frontmatter(text, ("title", "tags"), out_file),
                  gates.required_sections(text, ("Findings", "Unknowns"), out_file),
                  gates.cited_lines(text, toolbox, out_file),
                  gates.findings_quoted(text, "findings", out_file),
                  gates.quotes_verbatim(text, toolbox, out_file, inline=False),
                  gates.locators_in_range(text, toolbox, out_file),
                  gates.grounded(text, toolbox, out_file),
                  gates.absence_claims(text, toolbox, out_file)]
        steps += gates.acceptance(text, spec, toolbox, out_file)
    return steps


LOG_HEAD_CHARS, LOG_TAIL_CHARS = 3000, 5000


def log_clerk_normalize(spec: dict, cfg: Config) -> dict:
    log = _readable_file(spec.get("log_file"), cfg, "spec.log_file")
    spec["log_file"] = str(log)
    spec["read_roots"] = [str(log.parent)]
    spec["output"] = _report_output(spec, cfg, f"log-clerk-{_slug(log.stem)}.md")
    return spec


def log_clerk_preload(spec: dict, cfg: Config, toolbox) -> str:
    """The head AND the tail: the first failure is usually the load-bearing one
    and lives near the top; the exit code and summary live at the end."""
    log = Path(spec["log_file"]).read_text(encoding="utf-8", errors="replace")
    if len(log) > LOG_HEAD_CHARS + LOG_TAIL_CHARS:
        n = log.count("\n", 0, len(log) - LOG_TAIL_CHARS) + 1
        shown = (log[:LOG_HEAD_CHARS] + f"\n...[middle omitted; the tail starts "
                 f"near line {n}; read_file the log for the middle]...\n"
                 + log[-LOG_TAIL_CHARS:])
    else:
        shown = log
    spec["_run_log"] = log
    toolbox.evidence.add("log", shown)
    return (f"LOG FILE: {Path(spec['log_file']).name} (in your first read root)\n"
            f"OUTPUT FILE: {spec['output']['files'][0]}\n\nLOG (cite it as "
            f"[src: log]; if you read_file more of it, cite the file name):\n\n{shown}")


def log_clerk_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    steps = [gates.output_paths(files, spec["output"]["files"],
                                Path(spec["output"]["root"]), cfg.writable)]
    text = files.get(out_file, "")
    if text:
        steps += [gates.frontmatter(text, ("title", "tags"), out_file),
                  gates.required_sections(text, ("Exit codes", "Failures"), out_file),
                  gates.cited_lines(text, toolbox, out_file),
                  gates.quotes_verbatim(text, toolbox, out_file),
                  gates.failures_in_order(text, spec.get("_run_log", ""), "failures",
                                          out_file),
                  gates.grounded(text, toolbox, out_file)]
        steps += gates.acceptance(text, spec, toolbox, out_file)
    return steps


def completion_audit_normalize(spec: dict, cfg: Config) -> dict:
    if not (spec.get("claim") or "").strip():
        raise CrewError("completion_audit needs claim: the work claimed complete")
    expected = spec.get("expected") or []
    if not expected or not all(isinstance(e, dict) and e.get("artifact") for e in expected):
        raise CrewError("completion_audit needs expected: [{artifact, path?}, ...]")
    roots = spec.get("read_roots") or []
    if not roots:
        raise CrewError("completion_audit needs read_roots: the project to inspect")
    for r in roots:
        if not cfg.readable(Path(r)):
            raise CrewError(f"read root {r} is outside the crew's read roots")
    spec["read_roots"] = [str(Path(r).resolve()) for r in roots]
    base = Path(spec["read_roots"][0])
    for e in expected:
        if e.get("path"):
            p = Path(e["path"])
            p = (p if p.is_absolute() else base / p).resolve()
            if not cfg.readable(p.parent if not p.exists() else p):
                raise CrewError(f"expected path {e['path']} is outside the read roots")
            e["path"] = str(p)
    spec["expected"] = expected
    spec["output"] = _report_output(
        spec, cfg, "completion-" + _slug(spec.get("title") or spec["claim"]) + ".md")
    return spec


def completion_audit_preload(spec: dict, cfg: Config, toolbox) -> str:
    """The harness checks existence itself - a mechanical fact is never left
    to a model. The member judges what existence cannot: YES vs PARTIAL, and
    where an artifact with no given path is."""
    rows = []
    for e in spec["expected"]:
        if e.get("path"):
            p = Path(e["path"])
            e["exists"] = p.exists()
            size = (f"{p.stat().st_size} B" if p.is_file() else "directory") \
                if p.exists() else "NOT FOUND"
            rows.append(f"- {e['artifact']}: {toolbox.display(p)} - {size}")
        else:
            e["exists"] = None
            rows.append(f"- {e['artifact']}: (no path given - find it, or UNKNOWN)")
    inventory = "\n".join(rows)
    toolbox.evidence.add("inventory", inventory)
    return (f"OUTPUT FILE: {spec['output']['files'][0]}\n\nCLAIMED WORK:\n"
            f"{spec['claim'].strip()}\n\nINVENTORY (the harness checked these paths; "
            f"cite it as [src: inventory]):\n{inventory}\n\nREAD ROOTS:\n"
            + "\n".join(f"- {r}" for r in spec["read_roots"]))


def completion_audit_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    steps = [gates.output_paths(files, spec["output"]["files"],
                                Path(spec["output"]["root"]), cfg.writable)]
    text = files.get(out_file, "")
    if text:
        steps += [gates.frontmatter(text, ("title", "tags"), out_file),
                  gates.completion_inventory(text, spec["expected"], toolbox, out_file),
                  gates.cited_lines(text, toolbox, out_file),
                  gates.quotes_verbatim(text, toolbox, out_file)]
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
                  gates.reported_failures_exist(text, log, out_file, toolbox),
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


HOUSE_STYLE = Path(__file__).resolve().parent / "contracts" / "HOUSE_STYLE.md"
JS_HOUSE_STYLE = HOUSE_STYLE.with_name("JS_HOUSE_STYLE.md")


def _contract_text(spec: dict, cfg: Config) -> str:
    """The contract, with the house style appended.

    The first campaign produced correct code with 64 lint findings, and every one
    of them was something nobody had asked for in writing. So the style block
    travels with every contract now, rather than living in a file members cannot
    see.
    """
    path = Path(spec["contract"]).resolve()
    if not path.is_file() or not cfg.readable(path):
        raise CrewError(f"spec.contract {spec['contract']} is not a readable file "
                        f"in the crew's read roots")
    text = path.read_text(encoding="utf-8")[:CONTRACT_CHARS]
    style = JS_HOUSE_STYLE if spec.get("task_type", "").startswith("js_") else HOUSE_STYLE
    if style.is_file():
        text += "\n\n---\n\n" + style.read_text(encoding="utf-8")
    return text


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


def _lsp_step(spec: dict, cfg: Config, modules: Dict[str, str], out_file: str,
              steps: List[dict]) -> List[dict]:
    """The language-server rung, only when the job asked for it (spec.lsp) and
    only once the cheaper structural gates pass - a module the safety scan
    refused is not worth starting a server for."""
    if not spec.get("lsp") or not all(st["ok"] for st in steps):
        return []
    lsp_cfg = cfg.data.get("lsp") or {}
    lang = next((k for k, v in lsp_cfg.items() if isinstance(v, dict)
                 and Path(out_file).suffix in v.get("extensions", [])), None)
    return [gates.lsp_clean(lsp_cfg, lang, modules, out_file, out_file)] if lang else []


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
        steps += _lsp_step(spec, cfg, {out_file: source, **deps}, out_file, steps)
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
        steps += _lsp_step(spec, cfg, {out_file: source, **mods}, out_file, steps)
        if all(st["ok"] for st in steps):
            steps.append(gates.tests_run_green(
                mods, {out_file: source}, int(spec["test_timeout_s"]), out_file,
                mod_names))
    return steps


# -- js_code_task / js_code_tests ---------------------------------------------------------
#
# The same contract-and-hidden-tests loop as code_task, for JavaScript ES modules. The
# judging is done by crew/jsharness/ - gates the crew itself built and had checked by
# hidden tests (js-harness campaign, 2026-09-21) - and Node runs sandboxed by its own
# permission model. See crew/jsrun.py.

_JS_TEST_CALL = re.compile(r"(?<![\w$.])(?:test|it)\s*\(")


def _js_step(verdict: dict, file: str) -> dict:
    ok = verdict["verdict"] == "accepted"
    if ok:
        return gates.step("js gate", True, "the hidden tests pass", file)
    detail = f"{verdict['verdict']}: " + "; ".join(verdict["problems"][:8])
    if verdict["verdict"] == "tests_failed":
        detail += ("\nThe hidden tests fail. This is the evidence; fix the module, "
                   "do not argue with it.")
    return gates.step("js gate", False, detail, file)


def js_code_task_normalize(spec: dict, cfg: Config) -> dict:
    module = (spec.get("module") or "").strip()
    if not module or "/" in module or "\\" in module or not module.endswith(".js"):
        raise CrewError("spec.module must be a single .js file name, e.g. inline.js")
    spec["task_type"] = "js_code_task"
    if not spec.get("contract"):
        raise CrewError("spec.contract is required: the file stating the API and behavior")
    _contract_text(spec, cfg)
    if not _hidden_tests(spec, cfg):
        raise CrewError("js_code_task needs hidden_tests (*.test.mjs): nothing else "
                        "can decide the outcome")
    _workspace_modules(spec, cfg)
    spec["api"] = [str(a) for a in (spec.get("api") or [])]
    if not spec["api"]:
        raise CrewError("spec.api must list the names the module must export")
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


def js_code_task_preload(spec: dict, cfg: Config, toolbox) -> str:
    text = code_task_preload(spec, cfg, toolbox)
    return text.replace(
        "Your source is checked first and REFUSED if it imports anything outside the "
        "contract's allowlist, calls eval/exec/open, or reaches the filesystem, "
        "network or registry.",
        "This is a JavaScript ES module: use `export`, never `module.exports`. Your "
        "source is checked first and REFUSED if it imports anything outside the "
        "contract's allowlist (accepted modules are imported as \"./name.js\") or "
        "uses eval, Function, process, require, fetch, XMLHttpRequest, WebSocket, "
        "Worker, globalThis, window or document outside a string. Node then runs "
        "the tests with no file, network or process access.")


def js_code_task_gates(files, spec, cfg, toolbox):
    from . import jsrun
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    source = files.get(out_file, "")
    if source:
        steps.append(gates.ascii_only(source, out_file))
        if all(st["ok"] for st in steps):
            verdict = jsrun.judge_module(source, spec["api"],
                                         _workspace_modules(spec, cfg),
                                         _hidden_tests(spec, cfg), out_file,
                                         int(spec["test_timeout_s"]))
            steps.append(_js_step(verdict, out_file))
    return steps


def js_code_tests_normalize(spec: dict, cfg: Config) -> dict:
    name = (spec.get("test_file") or "").strip()
    if not name.endswith(".test.mjs") or "/" in name or "\\" in name:
        raise CrewError("spec.test_file must be a single file named *.test.mjs")
    spec["task_type"] = "js_code_tests"
    if not spec.get("contract"):
        raise CrewError("spec.contract is required")
    _contract_text(spec, cfg)
    if not _workspace_modules(spec, cfg):
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


def js_code_tests_preload(spec: dict, cfg: Config, toolbox) -> str:
    contract = _contract_text(spec, cfg)
    toolbox.evidence.add("contract", contract)
    names = ", ".join(f'"./{m}"' for m in sorted(_workspace_modules(spec, cfg)))
    return "\n".join([
        f"OUTPUT FILE: {spec['output']['files'][0]}", "",
        "You are the TESTER. Another crew member wrote the module; you write tests "
        "for it from the CONTRACT, not from their code. You are not shown their "
        "source on purpose: tests written by reading an implementation only prove "
        "the implementation agrees with itself.", "",
        f"Import it as an ES module from {names}. Use only `node:test` and "
        f"`node:assert/strict`: `import test from \"node:test\";` and "
        f"`import assert from \"node:assert/strict\";`.", "",
        "CONTRACT:", "", contract, "",
        f"RULES: at least {spec['min_tests']} test(...) calls; use assert.throws for "
        f"errors, never try/catch with assert.fail; no other imports; no files, "
        f"network, timers or process access; each test's name says which contract "
        f"rule it checks. The harness runs your tests against the real module under "
        f"Node. If they fail, either the module is wrong or your test is - both are "
        f"reported, and a senior decides."])


def js_code_tests_gates(files, spec, cfg, toolbox):
    from . import jsrun
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    source = files.get(out_file, "")
    if source:
        mods = _workspace_modules(spec, cfg)
        problems = jsrun.scan_test_file(source, mods)
        count = len(_JS_TEST_CALL.findall(jsrun.js_imports.code_only(source)))
        steps += [gates.ascii_only(source, out_file),
                  gates.step("safety", not problems,
                             "the test file may not be executed: "
                             + "; ".join(problems[:6]), out_file),
                  gates.step("test count", count >= int(spec["min_tests"]),
                             f"{count} test(...) calls; the contract asks for at "
                             f"least {spec['min_tests']}", out_file)]
        if all(st["ok"] for st in steps):
            ok, tap, detail = jsrun.run_node_tests(mods, {out_file: source},
                                                   int(spec["test_timeout_s"]))
            if ok and detail["unexpected_files"]:
                ok, why = False, ("the run left files behind: "
                                  + ", ".join(detail["unexpected_files"]))
            else:
                why = "the tests fail against the real module:\n" + jsrun.summarize(tap)
            steps.append(gates.step("tests run", ok, why, out_file))
    return steps


# -- AutoHotkey v1: static gate on the host, tests only in Windows Sandbox ----------

_AHK_TEST_CALL = re.compile(r"^\s*(?:Is|Ok)\(", re.MULTILINE | re.IGNORECASE)
AHK_TOLD = ("This is an AutoHotkey v1 (1.1.x) file of PURE functions: text or numbers "
            "in, a value out. Expression syntax (:=), no legacy commands. It is REFUSED "
            "before running if it uses a directive (#...), a hotkey or hotstring (::), a "
            "label, '%' dynamic references, or any banned command - Run, Send, Click, "
            "Win*, File*, Reg*, DllCall, MsgBox, Sleep, ExitApp and the rest - unless the "
            "contract grants it. Code outside functions may only be NAME := value. It "
            "then runs, with the tests, inside a disposable Windows Sandbox.")


def _ahk_grants(spec: dict) -> list:
    from .ahkrun import GRANTABLE
    grants = [str(g) for g in (spec.get("grants") or [])]
    unknown = [g for g in grants if g not in GRANTABLE]
    if unknown:
        raise CrewError(f"unknown grant(s) {unknown}; grantable: {sorted(GRANTABLE)}")
    return grants


def ahk_code_task_normalize(spec: dict, cfg: Config) -> dict:
    module = (spec.get("module") or "").strip()
    if not module or "/" in module or "\\" in module or not module.endswith(".ahk"):
        raise CrewError("spec.module must be a single .ahk file name")
    spec["task_type"] = "ahk_code_task"
    if not spec.get("contract"):
        raise CrewError("spec.contract is required")
    _contract_text(spec, cfg)
    if not _hidden_tests(spec, cfg):
        raise CrewError("ahk_code_task needs hidden_tests (test_*.ahk)")
    _workspace_modules(spec, cfg)
    spec["grants"] = _ahk_grants(spec)
    spec["api"] = [str(a) for a in (spec.get("api") or [])]
    if not spec["api"]:
        raise CrewError("spec.api must list the functions the file must define")
    spec["read_roots"] = [str(Path(spec["contract"]).resolve().parent)]
    root = Path((spec.get("output") or {}).get("root")
                or cfg.state_home / "outbox" / "workspace").resolve()
    if not cfg.writable(root / module):
        raise CrewError(f"{root / module} is outside the crew's write roots")
    spec["output"] = {"root": str(root), "files": [module]}
    return spec


def ahk_code_task_preload(spec: dict, cfg: Config, toolbox) -> str:
    text = code_task_preload(spec, cfg, toolbox)
    return text.replace(
        "Your source is checked first and REFUSED if it imports anything outside the "
        "contract's allowlist, calls eval/exec/open, or reaches the filesystem, "
        "network or registry.", AHK_TOLD)


def _ahk_static(source: str, name: str, spec: dict, includes=()) -> list:
    """The crew-built checks, with the task's grants applied."""
    from . import ahkrun
    return ahkrun.static_problems({} if includes else {name: source},
                                  {name: source} if includes else {},
                                  spec.get("grants") or ())


def _ahk_run(modules: dict, tests: dict, spec: dict, file: str) -> dict:
    from . import ahkrun
    result = ahkrun.run_ahk_tests(modules, tests, title=spec.get("title", ""),
                                  grants=spec.get("grants") or ())
    if result["ok"]:
        return gates.step("sandbox tests", True, result["summary"], file)
    why = result["summary"] + ("\n" + "\n".join(result["problems"][:6])
                               if result["problems"] else "")
    fails = [l for l in result["log"].splitlines() if l.startswith("not ok")][:8]
    if fails:
        why += "\n" + "\n".join(fails)
    return gates.step("sandbox tests", False, why, file)


def ahk_code_task_gates(files, spec, cfg, toolbox):
    from . import ahkrun  # noqa: F401 - puts the crew-built AHK gate on sys.path
    import ahk_api
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    source = files.get(out_file, "")
    if source:
        problems = _ahk_static(source, out_file, spec)
        missing = ahk_api.missing(source, spec["api"])
        stubs = ahk_api.stubs(source)
        loose = ahk_api.top_level(source)
        steps += [gates.step("safety", not problems, "; ".join(problems[:8]), out_file),
                  gates.step("api", not missing, "the contract requires these "
                             "functions, which are missing: " + ", ".join(missing),
                             out_file),
                  gates.step("no stubs", not stubs, "these do nothing: "
                             + ", ".join(stubs), out_file),
                  gates.step("no loose code", not loose, "code outside a function "
                             "runs the moment the file is included - lines "
                             + ", ".join(map(str, loose[:10])), out_file)]
        if all(st["ok"] for st in steps):
            mods = {**_workspace_modules(spec, cfg), out_file: source}
            steps.append(_ahk_run(mods, _hidden_tests(spec, cfg), spec, out_file))
    return steps


def ahk_code_tests_normalize(spec: dict, cfg: Config) -> dict:
    name = (spec.get("test_file") or "").strip()
    if not (name.startswith("test_") and name.endswith(".ahk")) or "/" in name:
        raise CrewError("spec.test_file must be a single file named test_*.ahk")
    spec["task_type"] = "ahk_code_tests"
    if not spec.get("contract"):
        raise CrewError("spec.contract is required")
    _contract_text(spec, cfg)
    if not _workspace_modules(spec, cfg):
        raise CrewError("spec.depends_modules must name the accepted module(s)")
    spec["grants"] = _ahk_grants(spec)
    spec["read_roots"] = [str(Path(spec["contract"]).resolve().parent)]
    spec.setdefault("min_tests", 6)
    root = Path((spec.get("output") or {}).get("root")
                or cfg.state_home / "outbox" / "workspace" / "tests").resolve()
    if not cfg.writable(root / name):
        raise CrewError(f"{root / name} is outside the crew's write roots")
    spec["output"] = {"root": str(root), "files": [name]}
    return spec


def ahk_code_tests_preload(spec: dict, cfg: Config, toolbox) -> str:
    contract = _contract_text(spec, cfg)
    toolbox.evidence.add("contract", contract)
    mods = sorted(_workspace_modules(spec, cfg))
    return "\n".join([
        f"OUTPUT FILE: {spec['output']['files'][0]}", "",
        "You are the TESTER. Write AutoHotkey v1 tests for another member's module "
        "from the CONTRACT, not from their code.", "",
        "The file must start with exactly these lines, then the checks, then Done():",
        "#Include tap.ahk", *[f"#Include {m}" for m in mods], "",
        "Checks: Is(got, want, \"which contract rule\") compares with ==, and "
        "Ok(condition, \"which contract rule\"). End with Done(). Nothing else from "
        "the outside world; no labels, hotkeys or '%'.", "",
        "CONTRACT:", "", contract, "",
        f"RULES: at least {spec['min_tests']} Is/Ok checks. The tests run in a "
        f"Windows Sandbox against the real module."])


def ahk_code_tests_gates(files, spec, cfg, toolbox):
    out_file = spec["output"]["files"][0]
    root = Path(spec["output"]["root"])
    steps = [gates.output_paths(files, spec["output"]["files"], root, cfg.writable)]
    source = files.get(out_file, "")
    if source:
        mods = _workspace_modules(spec, cfg)
        from . import ahkrun
        problems = ahkrun.static_problems(mods, {out_file: source},
                                          spec.get("grants") or ())
        count = len(_AHK_TEST_CALL.findall(source))
        steps += [gates.step("safety", not problems, "; ".join(problems[:8]), out_file),
                  gates.step("test count", count >= int(spec["min_tests"]),
                             f"{count} Is/Ok checks; the contract asks for at least "
                             f"{spec['min_tests']}", out_file)]
        if all(st["ok"] for st in steps):
            steps.append(_ahk_run(mods, {out_file: source}, spec, out_file))
    return steps


TASK_TYPES: Dict[str, Dict[str, object]] = {
    "ahk_code_task": {
        "description": "Write one AutoHotkey v1 file of pure functions against a contract. Judged by the crew-built static gate (safety, API, stubs, no loose code), then by hidden tests run only inside Windows Sandbox.",
        "spec": {"module": "required: the .ahk file to write",
                 "contract": "required: path to the contract file",
                 "api": "required: functions the file must define",
                 "hidden_tests": "required: test_*.ahk files the member never sees",
                 "grants": "optional: permissions from ahkrun.GRANTABLE, e.g. [\"clipboard\"]",
                 "instructions": "optional"},
        "gates": "output path, ahk_scan safety, ahk_api (api, stubs, loose code), then the hidden tests in Windows Sandbox",
        "apply": "writes the module into the crew workspace (never into a real project)",
        "normalize": ahk_code_task_normalize, "preload": ahk_code_task_preload,
        "gates_fn": ahk_code_task_gates,
    },
    "ahk_code_tests": {
        "description": "Write AutoHotkey v1 tests (tap.ahk Is/Ok checks) for another member's accepted module, from the contract alone; run in Windows Sandbox.",
        "spec": {"test_file": "required: test_*.ahk to write",
                 "contract": "required: the same contract the author worked from",
                 "depends_modules": "required: the accepted module(s) under test",
                 "grants": "optional: as for ahk_code_task",
                 "min_tests": "optional, default 6"},
        "gates": "output path, safety scan, enough Is/Ok checks, the tests pass in Windows Sandbox",
        "apply": "writes the test file into the crew workspace",
        "normalize": ahk_code_tests_normalize, "preload": ahk_code_tests_preload,
        "gates_fn": ahk_code_tests_gates,
    },
    "js_code_task": {
        "description": "Write one JavaScript ES module against a contract. Judged by the crew-built JS harness (lexer, import allowlist, forbidden globals, API, stubs) and then by hidden node:test tests run under Node's permission sandbox.",
        "spec": {"module": "required: the .js file to write",
                 "contract": "required: path to the contract file",
                 "api": "required: names the module must export",
                 "hidden_tests": "required: *.test.mjs files the member never sees",
                 "depends_modules": "optional: accepted .js modules it may import as ./name.js",
                 "test_timeout_s": "optional, default 180",
                 "instructions": "optional"},
        "gates": "output path, ASCII only, then js_gate: safety, API, stubs, hidden tests",
        "apply": "writes the module into the crew workspace (never into a real project)",
        "normalize": js_code_task_normalize, "preload": js_code_task_preload,
        "gates_fn": js_code_task_gates,
    },
    "js_code_tests": {
        "description": "Write node:test tests for another member's accepted JavaScript module, from the contract alone.",
        "spec": {"test_file": "required: *.test.mjs to write",
                 "contract": "required: the same contract the author worked from",
                 "depends_modules": "required: the accepted module(s) under test",
                 "min_tests": "optional, default 6",
                 "instructions": "optional"},
        "gates": "output path, ASCII only, safety scan, enough test() calls, the tests pass against the real module",
        "apply": "writes the test file into the crew workspace",
        "normalize": js_code_tests_normalize, "preload": js_code_tests_preload,
        "gates_fn": js_code_tests_gates,
    },
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
    "scout": {
        "description": "Locate where information lives: exact paths, line numbers and verbatim quotes, plus what could not be found. Judges nothing (ported from Crush-lite's scout).",
        "spec": {"instructions": "required: what to locate",
                 "read_roots": "optional: subset of crew read roots to search",
                 "context_files": "optional: files to preload (saves requests)",
                 "lsp": "optional: true gives symbols/definition/references/diagnostics tools",
                 "output": "optional {root, files:[name.md]}; default runs/crew/outbox"},
        "gates": "output path, frontmatter, Findings/Unknowns sections, every item cited, quotes verbatim, line numbers exist in the cited file, numbers grounded, absence claims evidenced",
        "apply": "writes the scout report to the output root",
        "normalize": scout_normalize, "preload": scout_preload, "gates_fn": scout_gates,
    },
    "log_clerk": {
        "description": "Say what literally happened in a build/test/terminal log: exit codes, failures quoted verbatim earliest first, warnings. No diagnosis (ported from Crush-lite's log-clerk).",
        "spec": {"log_file": "required: the log (a text file inside the crew's read roots)",
                 "instructions": "optional: what to focus on",
                 "output": "optional {root, files:[name.md]}; default runs/crew/outbox"},
        "gates": "output path, frontmatter, Exit codes/Failures sections, every item cited, quotes verbatim from the log, failures in log order, numbers grounded",
        "apply": "writes the log report to the output root",
        "normalize": log_clerk_normalize, "preload": log_clerk_preload,
        "gates_fn": log_clerk_gates,
    },
    "completion_audit": {
        "description": "Check claimed work against expected artifacts: YES/NO/PARTIAL/UNKNOWN per artifact and a conclusion. The harness checks existence itself; the member judges completeness. Not an approval (ported from Crush-lite's completion-auditor).",
        "spec": {"claim": "required: the work claimed complete",
                 "expected": "required: [{artifact: 'test file', path: 'tests/test_x.py'}, ...]; path optional",
                 "read_roots": "required: the project to inspect",
                 "output": "optional {root, files:[name.md]}; default runs/crew/outbox"},
        "gates": "output path, frontmatter, one row per artifact whose state agrees with what exists on disk, existing artifacts opened before judged, conclusion consistent with the states, every item cited",
        "apply": "writes the audit to the output root",
        "normalize": completion_audit_normalize, "preload": completion_audit_preload,
        "gates_fn": completion_audit_gates,
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
