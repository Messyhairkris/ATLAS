"""Fixers for a build whose checks failed: the mechanical repairs a run may take itself.

Kris, 2026-10-29: "syntax, formatting and style mistakes can all be corrected automatically
once they are known patterns a model follows. A run must never die over a predictable
misplaced symbol; it should be corrected, and the run saved."

Each fixer answers one question - did I change anything - and says what it did in a short
sentence, or nothing at all. Part 2 (`pa_build`) calls `run_fixers` when a round's checks
fail; this module knows how to repair, never when to.

The rules that make it safe to run unattended:

* never reformat - no fixer runs a formatter, and `normalise_newlines` and `ruff_fix`
  touch only the files they are handed (this round's changed files), never a glob;
* names are checked, not guessed - a fixer only opens a file named in the failure text or
  in the changed list, and never leaves the worktree;
* `failure_text` decides who tries - a fixer whose shape is absent does not run at all;
* never raise - a missing tool, a missing file or a non-zero exit becomes a sentence and
  the run carries on.

"Known pattern" is the point of the whole thing: a file that is already valid is left
byte-for-byte alone, so a fixer can never quietly rewrite working code.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"
CARGO_TIMEOUT = 600
TOOL_TIMEOUT = 300

# What each fixer is known to repair. The failure text is the checks' own output (pa_build
# quotes the command it ran), so a failure no fixer recognises returns [] and nothing runs.
CARGO_SIGNS = re.compile(
    r"\bcargo\b|\brustc\b|error\[E\d{3,4}\]|could not compile|warning: unused|"
    r"^\s*--> .+\.rs:\d+", re.I | re.M)
NEWLINE_SIGNS = re.compile(
    r"\bCRLF\b|line[ _-]?endings?|byte[ _-]?order[ _-]?mark|\bBOM\b|mixed newlines", re.I)
JSON_TOML_SIGNS = re.compile(
    r"\bjson\b|\btoml\b|Expecting|Extra data|Invalid control character|Unclosed|"
    r"trailing comma|delimiter", re.I)
RUFF_SIGNS = re.compile(r"\bruff\b|\b[A-Z]{1,4}\d{3,4}\b")

# A path the failure text or the changed list can name. Deliberately narrow: a fixer only
# ever opens one of these, and never searches the tree for a match.
PATH_IN_TEXT = re.compile(
    r"(?<![\w])([\w][\w./\\-]*\."
    r"(?:jsonc|json|toml|py|rs|mjs|js|tsx|ts|jsx|txt|md|cfg|ini|ya?ml))\b",
    re.I)

# A `git status --short` line: the status column, whitespace, then the path.
GIT_STATUS_PREFIX = re.compile(r"^[ MADRCU?!]{1,2}\s+")


def _inside(worktree: Path, name) -> "Path | None":
    """`name` read as a path inside `worktree`, or None when it is empty or escapes it.

    A name from the failure text is untrusted, and a fixer must never touch a file it was
    not handed: anything that resolves outside the worktree is refused, never followed.
    """
    text = str(name or "").strip().strip('"').strip("'")
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = Path(worktree) / path
    try:
        path = path.resolve()
        root = Path(worktree).resolve()
    except OSError:
        return None
    got, base = os.path.normcase(str(path)), os.path.normcase(str(root))
    if got == base or got.startswith(base + os.sep):
        return path
    return None


def _shown(worktree: Path, path: Path) -> str:
    """The file as the caller knows it, so a sentence names a file the caller recognises."""
    try:
        return path.relative_to(worktree).as_posix()
    except ValueError:
        return path.name


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _write(path: Path, data: bytes) -> bool:
    try:
        path.write_bytes(data)
        return True
    except OSError:
        return False


def _decode(raw: bytes) -> "str | None":
    """UTF-8 text with a leading byte-order mark removed, or None when it is not UTF-8."""
    if raw.startswith(BOM):
        raw = raw[len(BOM):]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _toml():
    """The TOML parser: the stdlib one (3.11+), `tomli` when it is installed, else None."""
    try:
        import tomllib
        return tomllib
    except ImportError:
        pass
    try:
        import tomli
        return tomli
    except ImportError:
        return None


def _parses(suffix: str, text: str) -> bool:
    """Whether `text` is valid in the format `suffix` names."""
    if suffix == ".json":
        try:
            json.loads(text)
            return True
        except ValueError:
            return False
    parser = _toml()
    if parser is None:
        return False                      # no parser here: never write a TOML file blind
    try:
        parser.loads(text)
        return True
    except Exception:                     # noqa: BLE001 - any parse failure means "not fixed"
        return False


def _strip_trailing_commas(text: str) -> str:
    """Drop a comma that only precedes a closing brace or bracket.

    A regex would also rewrite a `,}` that sits inside a string - real data - so this walks
    the text and only strips a comma that is outside one. That keeps the repair mechanical
    and never lossy.
    """
    out = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j < len(text) and text[j] in "}]":
                i += 1                    # the comma before a closer: dropped
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _clean_name(item) -> str:
    """One entry of the changed list as a path name, whatever shape it arrived in.

    A caller may pass bare names, paths, or the lines of `git status --short`; all three
    mean the same file. Anything else becomes an empty name and is ignored.
    """
    if isinstance(item, dict):
        item = item.get("path") or item.get("file") or ""
    name = str(item or "").strip()
    if len(name) > 1 and name[0] == name[-1] and name[0] in "\"'":
        name = name[1:-1].strip()
    return GIT_STATUS_PREFIX.sub("", name, count=1).strip()


def _named_paths(text: str) -> list:
    """The file names the failure text itself contains, in the order it names them."""
    seen, out = set(), []
    for match in PATH_IN_TEXT.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _ruff_command() -> "list | None":
    """How to invoke ruff here: the executable, the module, or None when it is absent."""
    exe = shutil.which("ruff")
    if exe:
        return [exe]
    try:
        if importlib.util.find_spec("ruff") is not None:
            return [sys.executable, "-m", "ruff"]
    except (ImportError, ValueError):
        pass
    return None


def _git_status(worktree: Path) -> str:
    """`git status --short` for the worktree, or "" when it is not a repository."""
    try:
        done = subprocess.run(["git", "-C", str(worktree), "status", "--short"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def normalise_newlines(worktree: Path, files: list) -> str:
    """Replace CRLF (and a stray CR) with LF and drop a leading BOM in the files handed in.

    ONLY the files handed in are touched - this round's changed files - so a stray CRLF in a
    file the build never wrote is left for its owner. A binary file (a NUL byte) is not a
    newline problem and is skipped, and so is a file that is already correct.
    """
    worktree = Path(worktree)
    done = []
    for name in files or []:
        path = _inside(worktree, name)
        if path is None or not path.is_file():
            continue
        raw = _read(path)
        fixed = raw[len(BOM):] if raw.startswith(BOM) else raw
        fixed = fixed.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if fixed == raw or b"\x00" in fixed:
            continue
        if _write(path, fixed):
            done.append(_shown(worktree, path))
    if not done:
        return ""
    return f"normalise_newlines: rewrote CRLF/BOM in {len(done)} file(s): {', '.join(done)}"


def repair_json_toml(worktree: Path, files: list) -> str:
    """Repair a JSON or TOML file the check NAMED, only where a machine may be sure.

    A file that already parses is never touched. When it does not, the known mistakes are
    tried (a trailing comma before a closing bracket, a byte-order mark) and the result is
    written ONLY if it then parses - which is what keeps this a repair and not a guess.
    Anything still broken is left byte-for-byte alone.
    """
    worktree = Path(worktree)
    done = []
    for name in files or []:
        path = _inside(worktree, name)
        if path is None or not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".json", ".toml"):
            continue
        raw = _read(path)
        text = _decode(raw)
        if text is None:
            continue
        candidate = text
        if not _parses(suffix, text) and suffix == ".json":
            candidate = _strip_trailing_commas(text)
        if not _parses(suffix, candidate):
            continue
        fixed = candidate.encode("utf-8")
        if fixed != raw and _write(path, fixed):
            done.append(_shown(worktree, path))
    if not done:
        return ""
    return f"repair_json_toml: repaired {len(done)} file(s): {', '.join(done)}"


def ruff_fix(worktree: Path, files: list) -> str:
    """`ruff check --fix` over the files handed in - a linter, never a formatter or a glob.

    ruff rewrites only safe, mechanical lint findings and leaves layout alone. The files are
    read before and after, because ruff's exit code says what is LEFT, not what it changed.
    """
    worktree = Path(worktree)
    targets = []
    for name in files or []:
        path = _inside(worktree, name)
        if path is not None and path.is_file() and path.suffix.lower() == ".py":
            targets.append(path)
    if not targets:
        return ""
    command = _ruff_command()
    if command is None:
        return "ruff_fix: no ruff on PATH, so nothing was fixed"
    before = {str(p): _read(p) for p in targets}
    try:
        done = subprocess.run(
            command + ["check", "--fix", "--no-cache", *[str(p) for p in targets]],
            cwd=str(worktree), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TOOL_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"ruff_fix: ruff could not run ({exc.__class__.__name__}), nothing was fixed"
    changed = [_shown(worktree, p) for p in targets if before[str(p)] != _read(p)]
    if changed:
        return f"ruff_fix: ruff fixed {len(changed)} file(s): {', '.join(changed)}"
    if done.returncode not in (0, 1):
        return f"ruff_fix: ruff exited {done.returncode}, nothing was fixed"
    return ""


def cargo_fix(worktree: Path) -> str:
    """`cargo fix --allow-dirty` in the worktree: the compiler's own suggestions, applied.

    cargo fix makes the edits rustc proposed, so a run does not die over an unused import
    or a misplaced `mut`. It only runs when the tool and a cargo project are both there;
    without either it says so and stops.
    """
    worktree = Path(worktree)
    exe = shutil.which("cargo")
    if exe is None:
        return "cargo_fix: no cargo on PATH, so nothing was fixed"
    if not (worktree / "Cargo.toml").is_file():
        return "cargo_fix: no Cargo.toml in this worktree, so nothing was fixed"
    before = _git_status(worktree)
    try:
        done = subprocess.run([exe, "fix", "--allow-dirty"], cwd=str(worktree),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=CARGO_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"cargo_fix: cargo fix could not run ({exc.__class__.__name__}), nothing was fixed"
    after = _git_status(worktree)
    output = (done.stdout or "") + (done.stderr or "")
    if before != after or (not before and not after and re.search(r"\bfixed\b", output, re.I)):
        return "cargo_fix: cargo fix applied the compiler's suggestions (--allow-dirty)"
    if done.returncode != 0:
        return f"cargo_fix: cargo fix exited {done.returncode}, nothing was fixed"
    return ""


def _attempt(fixer, *args) -> str:
    """Call a fixer; a fixer must never raise, and if one does the run carries on."""
    try:
        return fixer(*args) or ""
    except Exception as exc:              # noqa: BLE001 - reported, never raised past here
        return (f"{fixer.__name__}: could not run ({exc.__class__.__name__}), "
                f"nothing was changed")


def run_fixers(worktree: Path, failure_text: str, changed: list) -> list:
    """Run every fixer whose shape the failure names, cheapest first.

    -> the sentences of the fixers that changed something, in the order they ran, and []
    when none did. `failure_text` decides who tries: a failure no fixer recognises returns
    [] at once. `changed` is this round's changed files - the only files a newline or lint
    fixer may touch - and `failure_text` is also read for the file a check NAMED.

    Never raises, whatever it is handed: a fixer that cannot run answers with a sentence
    and the next one still gets its turn.
    """
    try:
        return _run_fixers(worktree, failure_text, changed)
    except Exception:                     # noqa: BLE001 - a fixer must never kill a run
        return []


def _run_fixers(worktree: Path, failure_text: str, changed: list) -> list:
    try:
        root = Path(worktree)
    except TypeError:
        return []
    text = failure_text if isinstance(failure_text, str) else str(failure_text or "")
    items = changed if isinstance(changed, (list, tuple, set)) else []
    files = [n for n in (_clean_name(item) for item in items) if n]
    named = _named_paths(text)
    out = []

    if NEWLINE_SIGNS.search(text):
        sentence = _attempt(normalise_newlines, root, files)
        if sentence:
            out.append(sentence)

    data_files = [n for n in named if n.lower().endswith((".json", ".toml"))]
    if data_files and JSON_TOML_SIGNS.search(text):
        sentence = _attempt(repair_json_toml, root, data_files)
        if sentence:
            out.append(sentence)

    py_files = [n for n in files if n.lower().endswith(".py")]
    if py_files and RUFF_SIGNS.search(text):
        sentence = _attempt(ruff_fix, root, py_files)
        if sentence:
            out.append(sentence)

    if CARGO_SIGNS.search(text):
        sentence = _attempt(cargo_fix, root)
        if sentence:
            out.append(sentence)

    return out
