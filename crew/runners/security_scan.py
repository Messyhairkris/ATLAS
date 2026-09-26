"""Pre-flight secret scan for a folder BEFORE it becomes a crew read root.

Kris, 2026-09-22: "many of the projects we will archive... will have keys in
their files... I am all for added security steps... perhaps this can be a
request that should be called out by a Human when the task is assigned...
if the human forgets and security notices it, educates them what happened
and the pitfalls." This is that step. It runs BEFORE any folder is added to
`crew/config.json`'s read_roots, never after - a deny_glob gap caught once a
member can already read the folder is a near-miss, not a safeguard
(`config/octofriend/keys.json5` was caught by a human scan first, 2026-09-22,
which is the whole reason this tool exists rather than trusting the fixed
glob list alone).

Deliberately NOT a crew member's job: judging whether text IS a secret means
reading its value, and an LLM that reads a secret to decide it's a secret has
already leaked it to a third-party API. This stays plain, deterministic
Python - pattern and filename matching only - and the report never prints a
matched secret's actual text, only which pattern matched and where.

Two passes:
1. FILENAME heuristics - broader than crew/config.json's fixed deny_globs,
   catching names a human would recognize as credential-shaped even if no
   existing rule does (this is exactly the keys.json5 gap).
2. CONTENT patterns - well-known secret SHAPES (AWS keys, GitHub/Slack/OpenAI
   tokens, PEM private key headers, JWTs, a generic "key/token/secret ="
   assignment with a long opaque value) in text files under a size cap.

Every finding is checked against the existing deny_globs; only gaps - things
NOT already covered - are called out as needing a decision, exactly the
"educates them" step Kris asked for.

    python crew/runners/security_scan.py "C:/Users/user/Vocto"
    python crew/runners/security_scan.py "C:/Users/user/Vocto" --suggest-globs
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

MAX_CONTENT_BYTES = 2_000_000     # skip anything bigger; not where secrets live
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv",
            "venv", ".pytest_cache", ".next", "target", ".turbo", ".cache"}

# -- filename heuristics: broader than the fixed deny_globs -------------------

_NAME_PATTERNS = [re.compile(p, re.I) for p in (
    r".*secret.*", r".*token.*", r".*credential.*", r".*password.*",
    r".*passwd.*", r".*\bapi[_-]?key.*", r".*\bauth\b.*", r"^\.env(\..+)?$",
    r".*\.pem$", r".*\.key$", r".*\.p12$", r".*\.pfx$", r".*\.jks$",
    r".*\.keystore$", r"^id_rsa.*", r"^id_ed25519.*", r"^id_dsa.*",
    r"^id_ecdsa.*", r"^\.npmrc$", r"^\.pypirc$", r"^\.netrc$",
    r"^\.git-credentials$", r".*\.docker/config\.json$", r".*kubeconfig.*",
    r".*service[_-]?account.*\.json$", r".*\.htpasswd$", r"^keys\.json.*",
    r".*\.json5$", r".*wallet.*",
)]

# -- content patterns: known secret SHAPES, never the fixed value -------------

_CONTENT_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("PEM private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("JWT-shaped token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("generic key/token/secret assignment",
     re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*"
               r"['\"][A-Za-z0-9_\-/+=]{16,}['\"]")),
]


def _load_deny_globs() -> List[str]:
    cfg_path = REPO_ROOT / "crew" / "config.json"
    if not cfg_path.is_file():
        return []
    return json.loads(cfg_path.read_text(encoding="utf-8")).get("deny_globs", [])


def _already_denied(path: Path, deny_globs: List[str]) -> Optional[str]:
    posix = path.as_posix()
    for pat in deny_globs:
        if fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch("/" + posix, pat):
            return pat
    return None


def _looks_like_text(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(4096)
        return b"\x00" not in chunk
    except OSError:
        return False


def _walk_files(root: Path):
    """os.walk with SKIP_DIRS pruned IN PLACE before descending - unlike
    Path.rglob, which yields every node_modules/dist descendant and only lets
    you discard them after the fact. The first run of this scanner against
    Vocto (node_modules present) timed out at 120s before this fix."""
    import os
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def scan(root: Path) -> dict:
    deny_globs = _load_deny_globs()
    findings = []
    for p in _walk_files(root):
        rel = p.relative_to(root).as_posix()
        name_hit = next((pat.pattern for pat in _NAME_PATTERNS if pat.match(p.name)), None)
        if name_hit:
            findings.append({"path": rel, "kind": "filename", "pattern": name_hit,
                             "denied_by": _already_denied(p, deny_globs)})
            continue                          # don't also content-scan an
                                              # already-flagged credential file
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size == 0 or size > MAX_CONTENT_BYTES or not _looks_like_text(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pat in _CONTENT_PATTERNS:
            if pat.search(text):
                findings.append({"path": rel, "kind": "content", "pattern": label,
                                 "denied_by": _already_denied(p, deny_globs)})
                break                          # one hit per file is enough to flag it
    gaps = [f for f in findings if not f["denied_by"]]
    covered = [f for f in findings if f["denied_by"]]
    return {"root": str(root), "findings": findings, "gaps": gaps, "covered": covered}


_RISK_NOTE = {
    "filename": "a file named like this commonly holds credentials; if this "
               "folder becomes crew-readable without a deny rule for it, its "
               "contents would be sent to a third-party LLM API (Synthetic) "
               "the moment any member opens it",
    "content": "this file's CONTENT matched a known secret shape; the value "
              "itself is not printed here, but reading this file (even by a "
              "human, even in this scan's own byte check) means it exists "
              "unprotected on disk - the fix is a deny rule, not just caution",
}


def report(result: dict, suggest_globs: bool) -> str:
    lines = [f"Security scan: {result['root']}", ""]
    if not result["findings"]:
        lines.append("No credential-shaped files or content found.")
        return "\n".join(lines)
    if result["gaps"]:
        lines.append(f"GAPS - {len(result['gaps'])} finding(s) NOT covered by "
                     f"any existing deny_glob (crew/config.json). These need a "
                     f"decision before this folder is a crew read root:")
        for f in result["gaps"]:
            lines.append(f"  - {f['path']}  [{f['kind']}: {f['pattern']}]")
            lines.append(f"      why it matters: {_RISK_NOTE[f['kind']]}")
        lines.append("")
    if result["covered"]:
        lines.append(f"Already covered by an existing deny rule "
                     f"({len(result['covered'])} finding(s), no action needed):")
        for f in result["covered"]:
            lines.append(f"  - {f['path']}  (denied by {f['denied_by']})")
        lines.append("")
    if suggest_globs and result["gaps"]:
        lines.append("Suggested additions to crew/config.json deny_globs "
                     "(review before adding - these are broad on purpose):")
        seen = set()
        for f in result["gaps"]:
            name = Path(f["path"]).name
            glob = f"**/{name}" if f["kind"] == "filename" else f"**/{f['path']}"
            if glob not in seen:
                seen.add(glob)
                lines.append(f'    "{glob}",')
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--suggest-globs", action="store_true")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    root = Path(args.folder).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    result = scan(root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(report(result, args.suggest_globs))
    return 1 if result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
