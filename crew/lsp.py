"""A minimal Language Server Protocol client, so crew members can ask a real
language server where things are instead of grepping.

Crush-lite already gives its read-only workers lsp_diagnostics, lsp_symbols,
lsp_definition and lsp_references; this is the same idea without Crush. The
server runs as a child process over stdio. Members never talk to it directly:
the Toolbox asks it narrow questions and returns only locations inside the
job's read roots, as numbered lines, like read_file does.

Configured in config.json under "lsp" (one entry per language, off unless a
job sets spec.lsp). Only Python (pylsp) is wired and measured so far.
"""

import json
import queue
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

ERROR, WARNING = 1, 2
SEVERITY = {1: "error", 2: "warning", 3: "info", 4: "hint"}
SYMBOL_KIND = {5: "class", 6: "method", 9: "constructor", 12: "function",
               13: "variable", 14: "constant", 2: "module", 7: "property",
               8: "field", 10: "enum", 11: "interface", 23: "struct"}


class LspError(Exception):
    pass


def path_to_uri(p: Path) -> str:
    return Path(p).resolve().as_uri()


def uri_to_path(uri: str) -> Path:
    parsed = urllib.parse.urlparse(uri)
    return Path(urllib.request.url2pathname(urllib.parse.unquote(parsed.path))).resolve()


class LspClient:
    """One language server process. Not thread-safe: one job, one client."""

    def __init__(self, argv: List[str], root: Path, settings: Optional[dict] = None,
                 timeout_s: float = 30.0, start_timeout_s: float = 120.0):
        self.argv = argv
        self.root = Path(root).resolve()
        self.settings = settings or {}
        self.timeout_s = timeout_s
        self.start_timeout_s = start_timeout_s
        self.proc: Optional[subprocess.Popen] = None
        self._next_id = 0
        self._responses: Dict[int, "queue.Queue"] = {}
        self._diagnostics: Dict[str, List[dict]] = {}
        self._diag_event = threading.Condition()
        self._opened: Dict[str, int] = {}

    # -- transport -------------------------------------------------------------
    def start(self) -> "LspClient":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL,
                                         cwd=str(self.root), creationflags=flags)
        except OSError as e:
            raise LspError(f"could not start language server {self.argv[0]}: {e}")
        threading.Thread(target=self._read_loop, daemon=True).start()
        # pylsp takes ~23s just to print --help on Kris's i5-6600 (plugin entry
        # points load cold) - the same cold-import race that made Crush's MCP
        # servers time out at 30s (2026-09-24). Startup gets its own ceiling.
        self.request("initialize", timeout_s=self.start_timeout_s, params={
            "processId": None, "rootUri": path_to_uri(self.root),
            "workspaceFolders": [{"uri": path_to_uri(self.root), "name": self.root.name}],
            "capabilities": {"textDocument": {
                "publishDiagnostics": {},
                "documentSymbol": {"hierarchicalDocumentSymbolSupport": True}}},
            "initializationOptions": self.settings})
        self.notify("initialized", {})
        if self.settings:
            self.notify("workspace/didChangeConfiguration", {"settings": self.settings})
        return self

    def _send(self, msg: dict) -> None:
        if not self.proc or self.proc.poll() is not None:
            raise LspError("language server is not running")
        body = json.dumps(msg).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.proc.stdin.flush()

    def _read_loop(self) -> None:
        out = self.proc.stdout
        while True:
            length = None
            while True:
                line = out.readline()
                if not line:
                    return
                line = line.strip()
                if not line:
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":", 1)[1])
            if length is None:
                continue
            try:
                msg = json.loads(out.read(length).decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                q = self._responses.get(msg["id"])
                if q:
                    q.put(msg)
            elif msg.get("method") == "textDocument/publishDiagnostics":
                p = msg.get("params") or {}
                with self._diag_event:
                    self._diagnostics[p.get("uri", "")] = p.get("diagnostics") or []
                    self._diag_event.notify_all()
            elif "id" in msg and "method" in msg:
                # a server->client request (workspace/configuration, ...):
                # answer so the server does not stall waiting on us
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})

    def request(self, method: str, params: dict, timeout_s: Optional[float] = None):
        timeout_s = timeout_s or self.timeout_s
        self._next_id += 1
        rid = self._next_id
        q: "queue.Queue" = queue.Queue()
        self._responses[rid] = q
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout_s)
        except queue.Empty:
            raise LspError(f"{method}: no answer from the language server "
                           f"in {timeout_s:.0f}s")
        finally:
            self._responses.pop(rid, None)
        if "error" in msg:
            raise LspError(f"{method}: {msg['error'].get('message', msg['error'])}")
        return msg.get("result")

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self) -> None:
        if not self.proc:
            return
        try:
            self.request("shutdown", {})
            self.notify("exit", {})
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - best effort; kill below
            pass
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    # -- documents -------------------------------------------------------------
    def open(self, path: Path, text: Optional[str] = None,
             language_id: str = "python") -> str:
        path = Path(path).resolve()
        uri = path_to_uri(path)
        if text is None:
            text = path.read_text(encoding="utf-8", errors="replace")
        with self._diag_event:
            self._diagnostics.pop(uri, None)
        if uri in self._opened:
            self._opened[uri] += 1
            self.notify("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": self._opened[uri]},
                "contentChanges": [{"text": text}]})
        else:
            self._opened[uri] = 1
            self.notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": language_id, "version": 1, "text": text}})
        return uri

    def diagnostics(self, uri: str, wait_s: float = 15.0) -> List[dict]:
        deadline = time.monotonic() + wait_s
        with self._diag_event:
            while uri not in self._diagnostics:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise LspError("the language server published no diagnostics "
                                   f"within {wait_s:.0f}s")
                self._diag_event.wait(left)
            return list(self._diagnostics[uri])

    def symbols(self, uri: str) -> List[dict]:
        return self.request("textDocument/documentSymbol",
                            {"textDocument": {"uri": uri}}) or []

    def definition(self, uri: str, line: int, char: int) -> List[dict]:
        res = self.request("textDocument/definition", {
            "textDocument": {"uri": uri}, "position": {"line": line, "character": char}})
        return _locations(res)

    def references(self, uri: str, line: int, char: int) -> List[dict]:
        res = self.request("textDocument/references", {
            "textDocument": {"uri": uri}, "position": {"line": line, "character": char},
            "context": {"includeDeclaration": True}})
        return _locations(res)


def _locations(res) -> List[dict]:
    if not res:
        return []
    if isinstance(res, dict):
        res = [res]
    out = []
    for loc in res:
        uri = loc.get("uri") or loc.get("targetUri")
        rng = loc.get("range") or loc.get("targetSelectionRange") or {}
        if uri:
            out.append({"uri": uri, "line": rng.get("start", {}).get("line", 0)})
    return out


def flatten_symbols(symbols: List[dict], depth: int = 0) -> List[tuple]:
    """-> [(depth, kind, name, 1-based line)] for either LSP symbol shape."""
    rows = []
    for s in symbols:
        if s.get("kind") == 13 and (depth or s.get("containerName")):
            continue   # a local variable: noise in an outline
        rng = s.get("selectionRange") or s.get("range") \
            or (s.get("location") or {}).get("range") or {}
        line = rng.get("start", {}).get("line", 0) + 1
        rows.append((depth, SYMBOL_KIND.get(s.get("kind"), "symbol"), s.get("name", "?"), line))
        rows += flatten_symbols(s.get("children") or [], depth + 1)
    return rows


def format_diagnostics(diags: List[dict], min_severity: int = WARNING) -> List[str]:
    rows = []
    for d in sorted(diags, key=lambda d: (d.get("range", {}).get("start", {}).get("line", 0))):
        sev = d.get("severity", ERROR)
        if sev > min_severity:
            continue
        line = d.get("range", {}).get("start", {}).get("line", 0) + 1
        code = d.get("code") or d.get("source") or ""
        message = (d.get("message") or "").strip().splitlines()[0:1] or [""]
        rows.append(f"L{line} {SEVERITY.get(sev, sev)}"
                    f"{f' {code}' if code else ''}: {message[0]}")
    return rows


class LspPool:
    """Language servers for one job, started on first use, closed at the end."""

    def __init__(self, lsp_cfg: Dict[str, dict], root: Path):
        self.cfg = {k: v for k, v in (lsp_cfg or {}).items()
                    if isinstance(v, dict) and v.get("command")}
        self.root = root
        self.clients: Dict[str, LspClient] = {}

    def language_for(self, path: Path) -> Optional[str]:
        suffix = Path(path).suffix.lower()
        for lang, c in self.cfg.items():
            if suffix in [e.lower() for e in c.get("extensions", [])]:
                return lang
        return None

    def client(self, lang: str, diagnostics: bool = False) -> LspClient:
        """The navigation server, or with diagnostics=True the language's
        diagnostics server when one is configured separately (Python: pylsp
        navigates, but has no linter plugin installed here; ruff's built-in
        server does the diagnostics)."""
        c = self.cfg[lang]
        argv = c.get("diagnostics_command") if diagnostics else None
        key = f"{lang}:diag" if argv else lang
        if key not in self.clients:
            self.clients[key] = LspClient(list(argv or c["command"]), self.root,
                                          c.get("diagnostics_settings") if argv
                                          else c.get("settings"),
                                          float(c.get("timeout_s", 30)),
                                          float(c.get("start_timeout_s", 120))).start()
        return self.clients[key]

    def close(self) -> None:
        for c in self.clients.values():
            c.close()
        self.clients.clear()


def check_source(lsp_cfg: Dict[str, dict], lang: str, files: Dict[str, str],
                 target: str, workdir: Path) -> List[dict]:
    """Diagnostics for a submitted file that exists only in memory. Writes it
    (and the modules it may import) into workdir, a throwaway directory, so
    the server can resolve imports between them."""
    for name, text in files.items():
        (workdir / name).write_text(text, encoding="utf-8")
    pool = LspPool(lsp_cfg, workdir)
    try:
        client = pool.client(lang, diagnostics=True)
        uri = client.open(workdir / target, files[target], language_id=lang)
        return client.diagnostics(uri)
    finally:
        pool.close()
