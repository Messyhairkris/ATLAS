"""Local tools for special teams: read the workspace, stage files, check them.

Kris, 2026-09-25: give Kimi bigger tasks, near Claude's - designing a campaign,
checking Claude's work. Those need files, not a browser. This provider looks
like an MCP client to crew/special_teams.py (tools() / call()), so the same
guard, budgets, credit cap and quote grading apply.

- list_dir / read_file / search: the crew's own read-only Toolbox, confined to
  the mission's read roots; deny globs (secrets, hidden tests, campaigns) win.
- stage_file: writes ONLY into the mission's staging folder - never a real
  project. The PA reviews and moves anything worth keeping.
- check_staged: runs the crew's airlock on staged Python (import allowlist,
  banned names) and then the staged tests against the staged module, in a
  throwaway directory - the same gates a crew code job gets.
"""

from pathlib import Path, PurePosixPath

from . import gates
from .config import load_config
from .tools import Evidence, Toolbox, ToolError

MAX_STAGED_BYTES = 200_000


def _schema(props: dict, required: list) -> dict:
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


TOOLS = [
    {"name": "list_dir", "description": "List a folder inside the mission's read roots.",
     "inputSchema": _schema({"path": {"type": "string"}}, [])},
    {"name": "read_file", "description": "Read a text file as numbered lines (max 400 per call).",
     "inputSchema": _schema({"path": {"type": "string"}, "start": {"type": "integer"},
                             "lines": {"type": "integer"}}, ["path"])},
    {"name": "search", "description": "Regex search (case-insensitive) in file contents under a path.",
     "inputSchema": _schema({"pattern": {"type": "string"}, "path": {"type": "string"},
                             "max_hits": {"type": "integer"}}, ["pattern"])},
    {"name": "stage_file", "description": "Write one output file into the mission's staging "
     "folder (a relative path like contract.md or tests/test_x.py). Replaces an earlier "
     "version of the same file. Nothing outside the staging folder can be written.",
     "inputSchema": _schema({"path": {"type": "string"}, "content": {"type": "string"}},
                            ["path", "content"])},
    {"name": "check_staged", "description": "Run the crew's safety scan on a staged Python "
     "module and its staged pytest file, then run the tests against the module in a "
     "throwaway directory. Use it before you finish.",
     "inputSchema": _schema({"module": {"type": "string"}, "tests": {"type": "string"}},
                            ["module", "tests"])},
]


class LocalProvider:
    def __init__(self, read_roots, staging: Path, allowed_tools=None):
        self.cfg = load_config()
        self.toolbox = Toolbox(self.cfg, [Path(r) for r in read_roots], Evidence(), 12000)
        self.staging = Path(staging).resolve()
        self.staging.mkdir(parents=True, exist_ok=True)
        self.allowed = set(allowed_tools or [t["name"] for t in TOOLS])
        self.checks = []                      # every check_staged verdict, for grading

    def tools(self):
        return [t for t in TOOLS if t["name"] in self.allowed]

    def _staged_path(self, rel: str) -> Path:
        p = PurePosixPath(str(rel).replace("\\", "/"))
        if not rel or p.is_absolute() or ".." in p.parts or ":" in str(rel):
            raise ToolError("path must be relative, inside the staging folder, without ..")
        return self.staging / Path(*p.parts)

    def call(self, name: str, args: dict) -> dict:
        try:
            if name in ("list_dir", "read_file", "search"):
                return {"ok": True, "text": self.toolbox.call(name, args), "images": 0}
            if name == "stage_file":
                content = args.get("content", "")
                if len(content.encode("utf-8")) > MAX_STAGED_BYTES:
                    raise ToolError(f"file larger than {MAX_STAGED_BYTES} bytes")
                dest = self._staged_path(args.get("path", ""))
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
                return {"ok": True, "text": f"staged {dest.relative_to(self.staging).as_posix()} "
                        f"({len(content)} chars)", "images": 0}
            if name == "check_staged":
                return self._check(args)
            raise ToolError(f"unknown tool {name}")
        except ToolError as e:
            return {"ok": False, "text": f"TOOL ERROR: {e}", "images": 0}
        except OSError as e:
            return {"ok": False, "text": f"TOOL ERROR: {type(e).__name__}: {e}", "images": 0}

    def _check(self, args: dict) -> dict:
        mod_path = self._staged_path(args["module"])
        test_path = self._staged_path(args["tests"])
        if not mod_path.is_file() or not test_path.is_file():
            raise ToolError("stage the module and the tests first")
        src = mod_path.read_text(encoding="utf-8")
        tests = test_path.read_text(encoding="utf-8")
        name = mod_path.stem
        # The crew's fixed import allowlist, never widened by the member: an
        # "allowed_imports" argument here would let a model pass ["os",
        # "subprocess"] and have the harness run its code (caught in review,
        # 2026-09-25, before it ever shipped).
        steps = [gates.module_is_safe(src, mod_path.name),
                 gates.test_file_is_safe(tests, test_path.name, [name])]
        if all(s["ok"] for s in steps):
            steps.append(gates.tests_run_green({mod_path.name: src}, {test_path.name: tests},
                                               180, test_path.name, [name]))
        ok = all(s["ok"] for s in steps)
        self.checks.append({"module": args["module"], "tests": args["tests"], "ok": ok,
                            "steps": steps})
        text = "\n".join(f"[{'ok' if s['ok'] else 'FAIL'}] {s['rung']}: {s['detail']}"
                         for s in steps)
        return {"ok": ok, "text": ("ALL CHECKS PASS\n" if ok else "CHECKS FAILED\n") + text,
                "images": 0}

    def close(self):
        pass
