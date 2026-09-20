"""Domain module loader for the ATLAS API harness.

A module is a folder under experiments/modules/<name>/ with a module.json
manifest describing three knowledge assets: a knowledge pack (markdown),
a starter template (files that must exist and keep working), and reference
examples (known-good mini-projects models may steal patterns from).

Delivery modes:
    off       — module ignored (raw baseline)
    prompted  — knowledge pack into system prompt, template + examples
                appended to the user prompt
    frontload — knowledge pack into system prompt, template files merged
                UNDER model output at verification (model wins conflicts)
    both      — everything
"""

import json
from pathlib import Path

MODULES_ROOT = Path(__file__).resolve().parent / "modules"

MODES = ("off", "prompted", "frontload", "both")


class ModuleError(Exception):
    pass


class Module:
    def __init__(self, root: Path, manifest: dict):
        self.root = root
        self.manifest = manifest
        self.name = manifest["name"]
        self.knowledge_text = ""
        self.template_files = {}
        self.example_files = {}
        knowledge_rel = manifest.get("knowledge")
        if knowledge_rel:
            self.knowledge_text = (root / knowledge_rel).read_text(
                encoding="utf-8")
        for rel, src in (manifest.get("template") or {}).items():
            self.template_files[rel] = (root / src).read_text(encoding="utf-8")
        for ex_name, files in (manifest.get("examples") or {}).items():
            for rel in files:
                content = (root / "examples" / ex_name / rel).read_text(
                    encoding="utf-8")
                self.example_files[f"{ex_name}/{rel}"] = content

    def knowledge_for_system(self) -> str:
        return self.knowledge_text

    def prompt_appendix(self) -> str:
        parts = []
        if self.template_files:
            parts.append("STARTER SKELETON (already-working minimum; your "
                         "output must keep it working and extend it):")
            parts += self._fenced(self.template_files)
        if self.example_files:
            parts.append("REFERENCE EXAMPLE (known-good; steal these "
                         "patterns, do not copy the file names blindly):")
            parts += self._fenced(self.example_files)
        return "\n\n".join(parts)

    @staticmethod
    def _fenced(files: dict) -> list:
        return [f"```{rel}\n{content.rstrip()}\n```"
                for rel, content in files.items()]


def load_module(name: str) -> Module:
    root = MODULES_ROOT / name
    manifest_path = root / "module.json"
    if not manifest_path.exists():
        available = [p.name for p in MODULES_ROOT.iterdir() if p.is_dir()] \
            if MODULES_ROOT.exists() else []
        raise ModuleError(f"module '{name}' not found at {manifest_path}; "
                          f"available: {available or 'none'}")
    return Module(root, json.loads(manifest_path.read_text("utf-8")))


def list_modules() -> list:
    if not MODULES_ROOT.exists():
        return []
    return sorted(p.name for p in MODULES_ROOT.iterdir()
                  if (p / "module.json").exists())
