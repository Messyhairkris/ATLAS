"""Crew configuration: crew/config.json, overridable by CREW_CONFIG /
CREW_HOME for tests and second machines."""

import fnmatch
import json
import os
from pathlib import Path
from typing import List, Optional

CREW_DIR = Path(__file__).resolve().parent
REPO_ROOT = CREW_DIR.parent


class CrewError(Exception):
    """A request the crew refuses (bad spec, out-of-bounds path, bad state)."""


class Config:
    def __init__(self, data: dict):
        self.data = data
        self.state_home = Path(os.environ.get("CREW_HOME")
                               or data.get("state_home")
                               or REPO_ROOT / "runs" / "crew")
        self.read_roots = [Path(p).resolve() for p in data.get("read_roots", [])]
        self.write_roots = [Path(p).resolve()
                            for p in data.get("write_roots", [])]
        self.deny_globs: List[str] = data.get("deny_globs", [])
        self.fetch_allowlist: List[str] = data.get("fetch_allowlist", [])
        self.deny_models: List[str] = data.get("deny_models", [])
        self.project = data.get("project", "crosstalk")
        self.telemetry_file = data.get("telemetry_file")
        self.defaults = {"assigned_to": "Hoss", "max_requests": 12,
                         "max_tokens": 60000, "max_revisions": 3,
                         "observation_chars": 6000, "lease_seconds": 180,
                         **data.get("defaults", {})}

    # -- path policy ---------------------------------------------------------
    def denied(self, path: Path) -> bool:
        posix = path.as_posix()
        return any(fnmatch.fnmatch(posix, g) or fnmatch.fnmatch(posix + "/", g)
                   for g in self.deny_globs)

    @staticmethod
    def _within(path: Path, roots: List[Path]) -> bool:
        return any(path == r or r in path.parents for r in roots)

    def readable(self, path: Path, roots: Optional[List[Path]] = None) -> bool:
        p = path.resolve()
        return self._within(p, roots or self.read_roots) and not self.denied(p)

    def writable(self, path: Path) -> bool:
        p = path.resolve()
        return self._within(p, self.write_roots) and not self.denied(p)


def load_config(path: Optional[Path] = None) -> Config:
    path = Path(path or os.environ.get("CREW_CONFIG") or CREW_DIR / "config.json")
    return Config(json.loads(path.read_text(encoding="utf-8")))
