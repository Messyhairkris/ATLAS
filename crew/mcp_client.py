"""A minimal MCP client over stdio (newline-delimited JSON-RPC 2.0).

The special-teams harness is the MCP client; the member never is. It lists a
server's tools, shows the member only the ones a mission allows, and runs a
call only after the harness has checked it (crew/special_teams.py).
"""

import json
import queue
import subprocess
import threading
from typing import List, Optional


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, argv: List[str], cwd: Optional[str] = None,
                 timeout_s: float = 60.0, start_timeout_s: float = 120.0):
        self.argv, self.cwd = argv, cwd
        self.timeout_s, self.start_timeout_s = timeout_s, start_timeout_s
        self.proc = None
        self._id = 0
        self._waiting = {}

    def start(self) -> "McpClient":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=self.cwd,
                                     creationflags=flags)
        threading.Thread(target=self._reader, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "atlas-crew-special-teams",
                                                   "version": "1"}},
                     timeout_s=self.start_timeout_s)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def _send(self, msg: dict) -> None:
        if not self.proc or self.proc.poll() is not None:
            raise McpError("MCP server is not running")
        self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    MAX_LINE = 20_000_000     # bytes; one JSON-RPC message per line

    def _lines(self):
        """Lines of at most MAX_LINE bytes; an over-long one is skipped whole.
        (Kimi's review, 2026-09-25: an unbounded line - a page-controlled
        snapshot - could exhaust memory before any truncation applies.)"""
        out = self.proc.stdout
        while True:
            raw = out.readline(self.MAX_LINE)
            if not raw:
                return
            if len(raw) >= self.MAX_LINE and not raw.endswith(b"\n"):
                while True:                       # drain the rest of that line
                    more = out.readline(self.MAX_LINE)
                    if not more or more.endswith(b"\n"):
                        break
                continue
            yield raw

    def _reader(self) -> None:
        for raw in self._lines():
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                # Defensive: a non-UTF-8 line falls back to the Windows code page.
                # (Playwright MCP 0.0.78 on Windows sends U+FFFD for some punctuation
                # INSIDE valid UTF-8 - that loss happens in the server, not here;
                # special_teams.py tells the member so it is not reported as a bug.)
                text = raw.decode("cp1252", errors="replace")
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                q = self._waiting.get(msg["id"])
                if q:
                    q.put(msg)
            elif "id" in msg and "method" in msg:
                # server->client request (roots/list, sampling...): decline politely
                self._send({"jsonrpc": "2.0", "id": msg["id"],
                            "error": {"code": -32601, "message": "not supported"}})

    def request(self, method: str, params: dict, timeout_s: Optional[float] = None):
        self._id += 1
        rid, q = self._id, queue.Queue()
        self._waiting[rid] = q
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout_s or self.timeout_s)
        except queue.Empty:
            raise McpError(f"{method}: no answer in {timeout_s or self.timeout_s:.0f}s")
        finally:
            self._waiting.pop(rid, None)
        if "error" in msg:
            raise McpError(f"{method}: {msg['error'].get('message', msg['error'])}")
        return msg.get("result")

    def tools(self) -> List[dict]:
        return (self.request("tools/list", {}) or {}).get("tools", [])

    def call(self, name: str, arguments: dict) -> dict:
        """-> {"ok": bool, "text": str, "images": int}"""
        res = self.request("tools/call", {"name": name, "arguments": arguments}) or {}
        texts, images = [], 0
        for c in res.get("content") or []:
            if c.get("type") == "text":
                texts.append(c.get("text", ""))
            elif c.get("type") == "image":
                images += 1
        return {"ok": not res.get("isError"), "text": "\n".join(texts), "images": images}

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        self.proc = None
