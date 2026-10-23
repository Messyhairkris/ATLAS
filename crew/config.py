"""Crew configuration: crew/config.json, overridable by CREW_CONFIG /
CREW_HOME for tests and second machines."""

import fnmatch
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

CREW_DIR = Path(__file__).resolve().parent
REPO_ROOT = CREW_DIR.parent


class CrewError(Exception):
    """A request the crew refuses (bad spec, out-of-bounds path, bad state)."""


def benched_members(bench_until: dict, now: Optional[datetime] = None) -> List[str]:
    """Members whose bench has not yet run out.

    config.json `bench_until` maps a member name to a local ISO time, e.g.
    {"Gordon": "2026-09-29T15:39"}. Until then the member is denied like a
    deny_models entry (by name for "@post" routing, by model for direct calls);
    after it the entry is ignored, so nobody has to remember to lift it.
    """
    now = now or datetime.now()
    return [name for name, until in bench_until.items()
            if not name.startswith("comment") and datetime.fromisoformat(until) > now]


def _member_model(member: str) -> Optional[str]:
    """The model id personnel.json gives a member, or None."""
    try:
        staff = json.loads((CREW_DIR / "personnel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return staff.get("members", {}).get(member, {}).get("model")


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
        self.benched = benched_members(data.get("bench_until", {}))
        self.deny_models = self.deny_models + [
            name for member in self.benched for name in (member, _member_model(member))
            if name and name not in self.deny_models]
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
