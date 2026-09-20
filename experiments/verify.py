"""Godot verification ladder for the ATLAS API harness experiment battery.

Three rungs, in escalating trust/cost order:

1. structural-tscn — pure Python .tscn sanity check (no Godot, no execution).
   Safe to run on the host for every tier.
2. check-only     — godot --headless --check-only per .gd file. Compiles
   scripts without instantiating scenes. Host-safe.
3. wsb-run        — full headless project load inside Windows Sandbox. The
   ONLY path where agent-authored GDScript is allowed to execute; runs in a
   disposable VM with networking disabled and the Godot folder mapped
   read-only. Host polls for the log, then kills the sandbox.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

GODOT_EXE = os.environ.get(
    "GODOT_EXE", r"C:\Godot\Godot_v4.6.1-stable_win64_console.exe")
WSB_SHARE_ROOT = Path(os.environ.get("ATLAS_WSB_SHARE", r"C:\ATLAS-wsb"))
WSB_DESKTOP = r"C:\Users\WDAGUtilityAccount\Desktop"


# --- Rung 1: structural .tscn check ------------------------------------------

TSCN_NODE = re.compile(r'\[node\s+[^]]*type="(?P<type>[A-Za-z0-9]+)"[^]]*\]')
GDSCRIPT_HINT = re.compile(r"extends\s+\w+|@export|func\s+_ready")
FABRICATED_RESOURCE = re.compile(r"=\s*[A-Z][A-Za-z0-9_]*\s*\{")
COLOR_3ARG = re.compile(r"Color\(\s*[-\d.]+\s*,\s*[-\d.]+\s*,\s*[-\d.]+\s*\)")
EXT_RES = re.compile(r'\[ext_resource[^]]*type="(?P<type>[A-Za-z0-9]+)"[^]]*id\s*=\s*"?(?P<id>[A-Za-z0-9_.]+)"?[^]]*\]')
NODE_INSTANCE = re.compile(r'instance=ExtResource\(\s*"(?P<id>[^"]+)"\s*\)')


def structural_check(path: Path) -> Tuple[bool, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    errors: List[str] = []
    if not text.startswith("[gd_scene") and not text.startswith("[gd_resource"):
        errors.append("missing [gd_scene]/[gd_resource] header")
        return False, "; ".join(errors)
    if "[node" in text:
        node_types = TSCN_NODE.findall(text)
        if not node_types:
            errors.append("node sections present but unparseable")
    for line in text.splitlines():
        if line.startswith("[gd_scene"):
            if "format=3" not in line:
                errors.append("gd_scene header missing format=3 (Godot 4)")
        if line.startswith("[node") and "type=" not in line \
                and "instance=" not in line:
            errors.append(f"node section without type: {line[:80]}")
        if FABRICATED_RESOURCE.search(line):
            errors.append(
                f"fabricated GDScript-brace syntax in scene (not valid "
                f"TSCN): {line.strip()[:80]}; declare resources as "
                f"[sub_resource] blocks and reference with SubResource(\"id\")")
            break
        if COLOR_3ARG.search(line):
            errors.append(
                f"3-arg Color constructor in scene (Godot 4 TSCN needs "
                f"Color(r, g, b, a) = 4 args): {line.strip()[:80]}")
            break
    script_ids = {m.group("id") for m in EXT_RES.finditer(text)
                  if m.group("type") == "Script"}
    bad_instance = [m.group("id") for m in NODE_INSTANCE.finditer(text)
                    if m.group("id") in script_ids]
    if bad_instance:
        errors.append(
            f"instance=ExtResource points at a Script (id {', '.join(sorted(set(bad_instance)))}); "
            f"only PackedScene resources can be instanced - declare the node "
            f"with type= and attach the script as `script = ExtResource(...)`")
    declared = set()
    NODE_HDR = re.compile(r'\[node\s+name="(?P<name>[^"]+)"'
                          r'(?:[^]]*parent="(?P<parent>[^"]*)")?[^]]*\]')
    root_seen = False
    for m in NODE_HDR.finditer(text):
        name, parent = m.group("name"), m.group("parent")
        if not root_seen:
            if parent:
                errors.append(f"root node '{name}' must not have a parent")
            root_seen = True
            continue
        if parent in (None, "."):
            declared.add(name)
        else:
            if parent not in declared:
                errors.append(
                    f"node '{name}' has parent=\"{parent}\" but no such "
                    f"declared ancestor; children of the scene root use "
                    f"parent=\".\" (silently vanishes at instantiate)")
            declared.add(parent + "/" + name)
    return (not errors), "; ".join(errors) or "ok"


# --- Rung 1b: project.godot config check -----------------------------------

MAIN_SCENE_RE = re.compile(r'run/main_scene\s*=\s*"(?P<path>[^"]+)"')


def project_config_check(work: Path) -> Tuple[bool, str]:
    proj = work / "project.godot"
    text = proj.read_text(encoding="utf-8", errors="replace")
    m = MAIN_SCENE_RE.search(text)
    if not m:
        return False, ("project.godot has no run/main_scene under "
                       "[application]: Godot loads nothing and the run "
                       "hangs. Add run/main_scene=\"res://main.tscn\" "
                       "(or the tier's required main scene).")
    target = m.group("path").removeprefix("res://")
    if target and not (work / target).exists():
        return False, (f"run/main_scene points at {m.group('path')} but "
                       f"{target} was not emitted; every res:// path must "
                       f"exist.")
    return True, "ok"


# --- Rung 2: godot --check-only (host-safe: compile, no execution) ------------

def check_only_script(script_path: Path, project_dir: Path = None) -> Tuple[bool, str]:
    if not Path(GODOT_EXE).exists():
        return False, f"godot exe not found at {GODOT_EXE}"
    # --path anchors res:// to the verify work dir. Without it Godot roots at
    # CWD, res:// preloads resolve against the wrong project (false fails)
    # and project-less runs can surface host GUI dialogs instead of errors.
    project_dir = (project_dir or script_path.parent).resolve()
    args = [GODOT_EXE, "--headless", "--path", str(project_dir),
            "--check-only", "--script", str(script_path.resolve())]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=60,
                              cwd=str(project_dir))
    except subprocess.TimeoutExpired:
        return False, "check-only timed out (60s)"
    combined = (proc.stdout or "") + (proc.stderr or "")
    failed = proc.returncode != 0 or "Parse Error" in combined or "SCRIPT ERROR" in combined
    excerpt = "\n".join(combined.splitlines()[:12]).strip()
    return (not failed), excerpt or "ok"


# --- Rung 3: Windows Sandbox full run -----------------------------------------
#
# The sandbox sees exactly three folders:
#   Desktop\<run_id>  this run only (read-write): proj copy, job.json, logs
#   Desktop\Godot     the Godot install (read-only)
#   Desktop\sandbox   harness tools: runner.ps1, debloat, probe (read-only)
# Agent code can no longer see or alter other runs or the harness itself.
# experiments/sandbox/runner.ps1 shows a status window inside the sandbox,
# trims Windows per debloat_profile.json, runs Godot, and writes
# runner_done.txt; its own log is kept only when the run fails.

SANDBOX_TOOLS = Path(__file__).resolve().parent / "sandbox"
WSB_MEMORY_MB = int(os.environ.get("ATLAS_WSB_MEMORY_MB", "3072"))
WSB_LINGER_S = int(os.environ.get("ATLAS_WSB_LINGER_S", "4"))

WSB_TEMPLATE = """<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <PrinterRedirection>Disable</PrinterRedirection>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MemoryInMB>{memory_mb}</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{run_dir}</HostFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{godot_dir}</HostFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{tools_dir}</HostFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{desktop}\\{tools_name}\\runner.ps1" -JobDir "{desktop}\\{run_id}" -ToolsDir "{desktop}\\{tools_name}"</Command>
  </LogonCommand>
</Configuration>
"""


def build_wsb_config(run_dir: Path, godot_dir: Path,
                     tools_dir: Path = SANDBOX_TOOLS,
                     memory_mb: int = WSB_MEMORY_MB) -> str:
    return WSB_TEMPLATE.format(
        memory_mb=memory_mb, run_dir=str(run_dir), godot_dir=str(godot_dir),
        tools_dir=str(tools_dir), desktop=WSB_DESKTOP,
        tools_name=tools_dir.name, run_id=run_dir.name)


def inject_probe(proj_dir: Path, nonce: str) -> None:
    """Install the harness probe as an autoload in a sandbox COPY of the
    project (never in the agent's own tree)."""
    probe = (SANDBOX_TOOLS / "harness_probe.gd").read_text(encoding="utf-8")
    (proj_dir / "harness_probe.gd").write_text(
        probe.replace("__NONCE__", nonce), encoding="utf-8")
    cfg = proj_dir / "project.godot"
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    line = 'HarnessProbe="*res://harness_probe.gd"'
    if re.search(r"^\[autoload\]\s*$", text, re.MULTILINE):
        text = re.sub(r"^\[autoload\]\s*$", "[autoload]\n\n" + line, text,
                      count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + "\n\n[autoload]\n\n" + line + "\n"
    cfg.write_text(text, encoding="utf-8")


def probe_status(log_text: str, nonce: str) -> str:
    """'scene_loaded' | 'no_scene' | 'boot_only' | 'absent' for this nonce."""
    tag = f"HARNESS_PROBE {nonce} "
    if tag + "SCENE_LOADED" in log_text:
        return "scene_loaded"
    if tag + "NO_SCENE" in log_text:
        return "no_scene"
    if tag + "BOOT" in log_text:
        return "boot_only"
    return "absent"


def run_in_windows_sandbox(project_dir: Path, run_seconds: int = 8,
                           timeout_s: int = 180, keep: bool = False,
                           markers: tuple = ("T4_SCENE_READY",
                                             "LEVEL_COMPLETE"),
                           title: str = "", debloat: bool = True,
                           probe: bool = True) -> Tuple[bool, str]:
    """Copy the project into its own WSB run folder, boot a disposable
    sandbox, and wait for the in-sandbox runner to finish. Returns
    (passed, log_text). Passed = a positive marker present, no SCRIPT/Parse
    errors, and (probe on) the harness probe saw the main scene load.
    The run folder is deleted on a pass and KEPT on a failure (godot.log,
    runner.log, job.json) so failures are always inspectable."""
    run_id = f"run-{int(time.time())}"
    run_dir = (WSB_SHARE_ROOT / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project_dir, run_dir / "proj")
    nonce = secrets.token_hex(6) if probe else ""
    if probe:
        inject_probe(run_dir / "proj", nonce)

    godot_dir = Path(GODOT_EXE).parent
    job = {
        "run_id": run_id,
        "title": title or f"Godot run of {Path(project_dir).name}",
        "godot_dir": f"{WSB_DESKTOP}\\{godot_dir.name}",
        "godot_exe": Path(GODOT_EXE).name,
        "args": ["--headless", "--path", "proj", "--quit-after",
                 str(run_seconds), "--", "--autopilot"],
        "markers": list(markers),
        "probe_nonce": nonce,
        # In-sandbox hard kill leaves time for boot + debloat + write-back.
        "timeout_s": max(30, timeout_s - 60),
        "debloat": debloat,
        "linger_s": WSB_LINGER_S,
    }
    (run_dir / "job.json").write_text(json.dumps(job, indent=2),
                                      encoding="utf-8")
    wsb_path = run_dir / f"{run_id}.wsb"
    wsb_path.write_text(build_wsb_config(run_dir, godot_dir),
                        encoding="utf-8")

    done_path = run_dir / "runner_done.txt"
    log_path = run_dir / "godot.log"
    attempts = 2  # dated-system rule: cold-boot slow starts are expected;
    # never fail a sandbox run without one warm retry (Kris, 2026-09-17)
    finished = False
    for attempt in range(1, attempts + 1):
        subprocess.Popen(["cmd", "/c", "start", "", str(wsb_path)],
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if done_path.exists():
                finished = True
                break
            time.sleep(2)
        if finished:
            time.sleep(WSB_LINGER_S)  # let a watching human read the verdict
            break
        _kill_sandbox()
        if log_path.exists() or (run_dir / "runner.log").exists():
            break  # the runner started: a real failure, not a cold boot
        if attempt < attempts:
            print(f"  [wsb] attempt {attempt} produced nothing "
                  f"(cold boot?): warm retrying once...", flush=True)
    _kill_sandbox()

    log_text = log_path.read_text(encoding="utf-8", errors="replace") \
        if log_path.exists() else ""
    if not finished:
        log_text += (f"\n[harness] sandbox runner never finished "
                     f"({attempts} boots x {timeout_s}s)")
    status = probe_status(log_text, nonce) if probe else "off"
    ok = (finished and any(m in log_text for m in markers)
          and "SCRIPT ERROR" not in log_text and "Parse Error" not in log_text
          and (not probe or status == "scene_loaded"))
    log_text += f"\n[harness] probe={status}"
    if ok and not keep:
        shutil.rmtree(run_dir, ignore_errors=True)
    elif not ok:
        log_text += f"\n[harness] failure artifacts kept at {run_dir}"
        print(f"  [wsb] FAIL: artifacts kept at {run_dir}", flush=True)
    return ok, log_text


def wsb_selftest(timeout_s: int = 120) -> Tuple[bool, str]:
    """Minimal lifecycle check: does a WSB LogonCommand write into the share?
    Separates 'sandbox broken' from 'godot inside sandbox broken'."""
    share = WSB_SHARE_ROOT
    run_id = f"selftest-{int(time.time())}"
    run_dir = share / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.cmd").write_text(
        "@echo off\necho SANDBOX_ALIVE > \""
        f"{WSB_DESKTOP}\\{share.name}\\{run_id}\\alive.txt\"\n",
        encoding="ascii")
    wsb_path = run_dir / f"{run_id}.wsb"
    wsb_path.write_text(
        "<Configuration>\n  <Networking>Disable</Networking>\n"
        "  <MappedFolders><MappedFolder>\n"
        f"    <HostFolder>{share}</HostFolder>\n"
        "    <ReadOnly>false</ReadOnly>\n"
        "  </MappedFolder></MappedFolders>\n"
        "  <LogonCommand>\n"
        f"    <Command>cmd.exe /c \"{WSB_DESKTOP}\\{share.name}\\{run_id}\\run.cmd\"</Command>\n"
        "  </LogonCommand>\n</Configuration>\n",
        encoding="utf-8")
    alive = run_dir / "alive.txt"
    for attempt in range(1, 3):  # dated-system rule: one warm retry before failing
        subprocess.Popen(["cmd", "/c", "start", "", str(wsb_path)])
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if alive.exists():
                _kill_sandbox()
                shutil.rmtree(run_dir, ignore_errors=True)
                return True, (f"sandbox booted, LogonCommand ran, share writable "
                              f"(attempt {attempt})")
            time.sleep(2)
        _kill_sandbox()
        if attempt == 1:
            print("  [wsb] selftest attempt 1 timed out (cold boot?): "
                  "warm retrying once...", flush=True)
    return False, ("no alive.txt after 2 attempts — Windows Sandbox not "
                   "functional on this boot")


def _kill_sandbox() -> None:
    for proc in ("WindowsSandbox.exe", "WindowsSandboxClient.exe",
                 "WindowsSandboxRemoteSession.exe"):
        subprocess.run(["taskkill", "/IM", proc, "/F"],
                       capture_output=True, check=False)


# --- Orchestrator -------------------------------------------------------------

def verify_tier(tier: int, files: Dict[str, str], work: Path,
                run_seconds: int = 8) -> Dict:
    """Verify one tier's generated file set. files: {relative path: content}."""
    work = work.resolve()  # Godot --path rejects relative project paths
    work.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    for rel, content in files.items():
        dest = work / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(rel)

    report: Dict = {"tier": tier, "files": written, "steps": []}

    tscns = [w for w in written if w.endswith(".tscn")]
    for rel in tscns:
        ok, detail = structural_check(work / rel)
        report["steps"].append({"rung": "structural", "file": rel,
                                "ok": ok, "detail": detail})

    if "project.godot" in written:
        ok, detail = project_config_check(work)
        report["steps"].append({"rung": "project-config",
                                "file": "project.godot",
                                "ok": ok, "detail": detail})

    scripts = [w for w in written if w.endswith(".gd")]
    proj = work / "project.godot"
    if not proj.exists():
        # Verify shell: gives --path a project root so res:// resolves.
        # Deliberately NO run/main_scene here — check-only doesn't need one,
        # and T4's main-scene completeness is the MODEL's responsibility.
        proj.write_text(
            'config_version=5\n[application]\nconfig/name="verify-shell"\n',
            encoding="utf-8")
    for rel in scripts:
        ok, detail = check_only_script(work / rel, project_dir=work)
        report["steps"].append({"rung": "check-only", "file": rel,
                                "ok": ok, "detail": detail})

    host_ok = bool([s for s in report["steps"]]) and \
        all(s["ok"] for s in report["steps"])
    if tier >= 4 and host_ok:
        # Sandbox minutes are the priciest rung; gate on host success.
        ok, log = run_in_windows_sandbox(work, run_seconds=run_seconds)
        report["steps"].append({"rung": "wsb-run", "ok": ok,
                                "detail": log[-2000:]})
    elif tier >= 4:
        report["steps"].append({"rung": "wsb-run", "ok": False,
                                "detail": "skipped: host rungs already failed "
                                          "or no tscn present"})

    rungs = [s for s in report["steps"]]
    host_rungs = [s for s in rungs if s["rung"] != "wsb-run"]
    report["passed"] = bool(host_rungs) and all(s["ok"] for s in host_rungs) and (
        tier < 4 or any(s["ok"] for s in rungs if s["rung"] == "wsb-run"))
    return report


if __name__ == "__main__":
    if sys.argv[1] == "selftest":
        ok, detail = wsb_selftest()
    elif sys.argv[1] == "demo":
        # Watchable end-to-end check of the sandbox runner on the known-good
        # reference project (harness-authored, not agent code). Keeps the
        # run folder so the logs can be inspected either way.
        ok, detail = run_in_windows_sandbox(
            Path(__file__).resolve().parent / "modules" / "godot"
            / "examples" / "side_scroller_mini",
            run_seconds=8, timeout_s=300, keep=True,
            markers=("MAIN_SCENE_READY", "LEVEL_COMPLETE"),
            title="Demo: reference side-scroller (harness-authored)")
    else:
        target = Path(sys.argv[1])
        if target.suffix == ".gd":
            ok, detail = check_only_script(target)
        elif target.is_dir():
            ok, detail = run_in_windows_sandbox(target)
        else:
            ok, detail = structural_check(target)
    print(("PASS" if ok else "FAIL") + ": " + detail)
    sys.exit(0 if ok else 1)
