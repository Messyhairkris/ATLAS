"""Running code a crew member wrote, without trusting it.

The crew's other task types never execute member output: a report cannot hurt
you. A coding task must run, which is a different risk, so this module is the
airlock:

  1. `scan()` reads the submitted source as an AST and refuses anything that
     could reach outside a pure function - no imports beyond an allowlist, no
     eval/exec/compile/__import__, no open(), no attribute that names a way to
     touch the filesystem, the network, the registry or another process, and no
     dunder escapes (`__globals__`, `__subclasses__`).
  2. only then does `run_tests()` execute it, in a throwaway directory, as a
     separate process, with a timeout.

Contracts are written so this is easy to satisfy: anything that needs the real
machine (enumerating audio devices, speaking) is passed IN as a callable, and
the member writes the logic around it. That is also what makes the module
testable at all.

Residual risk, stated plainly: an AST allowlist is not a sandbox. It stops the
obvious and the careless, not a determined attacker. The mitigations that matter
are that members are cheap models working from our contracts, the code runs
against our own tests in a temp directory, and nothing reaches the real project
until a human moves it there.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

# Modules a pure-logic module may import. Anything that touches the world is
# injected by the caller instead.
ALLOWED_IMPORTS = {
    "dataclasses", "typing", "enum", "re", "math", "json", "collections",
    "itertools", "functools", "abc", "types", "string", "unicodedata",
    "statistics", "bisect", "copy", "heapq", "operator", "textwrap", "numbers",
    "fractions", "decimal", "datetime", "warnings", "threading", "queue",
    "contextlib", "__future__", "configparser", "hashlib",
    # struct packs numbers into bytes and back; it reads and writes nothing
    # outside the program. Added for the OpenGL std140 packer, 2026-09-21.
    "struct",
}
# `logging` is deliberately absent: logging.basicConfig(filename=...) writes a
# file, and no contract needs logging inside a pure module.
BANNED_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input", "breakpoint",
    "globals", "locals", "vars", "memoryview",
}
# Attributes that are either an escape from the sandbox of a pure function, or
# a way out of the import allowlist. This list is deliberately SHORT: because
# imports are allowlisted, os/subprocess/socket/pathlib are unreachable, so
# banning ordinary method names here only breaks honest code. str.replace,
# list.remove, queue.send and the like are fine and must stay allowed.
BANNED_ATTRS = {
    # named escapes from an object back to the interpreter
    "__globals__", "__subclasses__", "__builtins__", "__code__", "__bases__",
    "__mro__", "__getattribute__", "__reduce__", "__reduce_ex__", "__loader__",
    "__spec__", "__init_subclass__",
    # dangerous even though the import that provides them is already blocked:
    # a member could receive such an object as an argument from a test double
    "system", "popen", "startfile", "urlopen", "Popen", "check_output",
    "check_call", "execv", "execve", "fork", "rmtree", "FileHandler",
    "basicConfig",
    # configparser is allowed so a module can PARSE ini text, but .read() and
    # .read_file() open files, which is the one thing it must not do. read_string
    # is the parsing entry point and stays allowed.
    "read", "read_file",
}
MAX_SOURCE_BYTES = 200_000


def scan(source: str, filename: str = "<submitted>",
         extra_imports=()) -> List[str]:
    """Return a list of reasons the source may not be executed. Empty = safe to
    run under our tests.

    `extra_imports` names modules that are legitimately on the path for this
    task: the crew's own already-accepted modules, and pytest for a test file.
    Nothing else is ever importable, so a member cannot widen this itself.
    """
    allowed = set(ALLOWED_IMPORTS) | {str(x) for x in extra_imports}
    problems: List[str] = []
    if len(source.encode("utf-8", "replace")) > MAX_SOURCE_BYTES:
        return [f"{filename}: source is larger than {MAX_SOURCE_BYTES} bytes"]
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [f"{filename}: does not parse: line {e.lineno}: {e.msg}"]

    def note(node, msg: str) -> None:
        problems.append(f"{filename}:{getattr(node, 'lineno', '?')}: {msg}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in allowed:
                    note(node, f"import of {alias.name!r} is not allowed; the "
                               f"contract passes anything external in as an "
                               f"argument")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level:                      # relative import
                note(node, "relative imports are not allowed in a single-file module")
            elif root not in allowed:
                note(node, f"import from {node.module!r} is not allowed")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in BANNED_NAMES:
                note(node, f"{node.id}() is not allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr in BANNED_ATTRS:
                note(node, f"attribute .{node.attr} is not allowed")
    return problems


def public_names(source: str) -> List[str]:
    """Top-level functions, classes and assignments, so a gate can check that
    the contract's API actually exists."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
        elif isinstance(node, ast.Assign):
            out.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.append(node.target.id)
    return out


def stubbed(source: str, required: List[str]) -> List[str]:
    """Required functions that are present but empty: `pass`, `...`, or
    `raise NotImplementedError`. A stub passes an import check and fails the
    user, so it is not an implementation."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return list(required)
    empty = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in required:
            continue
        body = [s for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str))]      # drop docstring
        if not body:
            empty.append(node.name)
            continue
        if len(body) == 1:
            only = body[0]
            if isinstance(only, ast.Pass):
                empty.append(node.name)
            elif isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant) \
                    and only.value.value is Ellipsis:
                empty.append(node.name)
            elif isinstance(only, ast.Raise):
                name = getattr(only.exc, "id", None) or getattr(
                    getattr(only.exc, "func", None), "id", None)
                if name == "NotImplementedError":
                    empty.append(node.name)
    return empty


def run_tests(modules: Dict[str, str], test_files: Dict[str, str],
              timeout_s: int = 180, python: str = "",
              extra_imports=()) -> Tuple[bool, str, dict]:
    """Execute test files against submitted modules in a throwaway directory.

    `modules` and `test_files` are {filename: source}. Returns
    (passed, combined output, details). The caller must have run scan() on every
    module first; this function refuses to run if it finds a problem, so a bad
    call cannot skip the airlock.
    """
    # Every module in the run may import every other module in the run: they
    # were all accepted through this same airlock.
    on_path = set(extra_imports) | {n[:-3] for n in modules if n.endswith(".py")}
    blocked: List[str] = []
    for name, src in modules.items():
        blocked += scan(src, name, extra_imports=on_path)
    if blocked:
        return False, "REFUSED to execute:\n" + "\n".join(blocked), {"blocked": blocked}

    with tempfile.TemporaryDirectory(prefix="crew-code-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        for name, src in {**modules, **test_files}.items():
            dest = work / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src, encoding="utf-8")
        argv = [python or sys.executable, "-m", "pytest", "-q", "--no-header",
                "-p", "no:cacheprovider", *sorted(test_files)]
        env = {k: v for k, v in os.environ.items()
               if k in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP",
                        "PATHEXT", "WINDIR", "NUMBER_OF_PROCESSORS")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(work)
        try:
            proc = subprocess.run(argv, cwd=str(work), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout_s, env=env)
            out = (proc.stdout or "") + (proc.stderr or "")
            passed = proc.returncode == 0
            code = proc.returncode
        except subprocess.TimeoutExpired:
            out = (f"TIMEOUT: the tests did not finish in {timeout_s}s. An "
                   f"infinite loop counts as a failure.")
            passed, code = False, -9
        leftovers = sorted(p.name for p in work.iterdir()
                           if p.name not in modules and p.name not in test_files
                           and p.name != "__pycache__")
    return passed, out[-8000:], {"returncode": code, "unexpected_files": leftovers}


def summarize(output: str) -> str:
    """The pytest tail a member needs, small enough to paste into feedback."""
    lines = [l for l in output.splitlines() if l.strip()]
    keep = [l for l in lines if l.startswith(("FAILED", "ERROR", "E  ", "E "))
            or " passed" in l or " failed" in l or "assert" in l]
    return "\n".join((keep or lines)[-40:])


if __name__ == "__main__":       # tiny self-check: python -m crew.codetask file.py
    for path in sys.argv[1:]:
        src = Path(path).read_text(encoding="utf-8")
        print(json.dumps({"file": path, "problems": scan(src, path),
                          "public": public_names(src)}, indent=2))
