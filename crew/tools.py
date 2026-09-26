"""Read-only tools for crew members, plus the evidence ledger.

Members can look, never touch: list_dir, read_file, search, and (when the
config allowlists domains) fetch_url. Every path is resolved and checked
against the job's read roots and the deny globs, so symlinks and ".." cannot
escape. Every successful observation is recorded as EVIDENCE: the gates later
require that claims and citations in the output come from text the member
actually saw during this job (state-bound evidence), not from memory.
"""

import html
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config

TEXT_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".py", ".gd", ".tscn",
                 ".godot", ".cfg", ".ini", ".yaml", ".yml", ".toml", ".csv",
                 ".ps1", ".cmd", ".bat", ".go", ".js", ".ts", ".html", ".css",
                 ".ahk", ".xml", ".log", ".rst", ""}
MAX_FILE_BYTES = 2_000_000
MAX_SEARCH_FILES = 4000
GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


class ToolError(Exception):
    pass


class Evidence:
    """What the member has seen: resolved path/url -> concatenated text."""

    def __init__(self):
        self.seen: Dict[str, str] = {}
        self.opened: set = set()   # read by the member itself, not excerpted

    def add(self, key: str, text: str, opened: bool = True) -> None:
        self.seen[key] = self.seen.get(key, "") + "\n" + text
        if opened:
            self.opened.add(key)

    def text_for(self, key: str) -> str:
        return self.seen.get(key, "")

    def keys(self) -> List[str]:
        return sorted(self.seen)


class Toolbox:
    def __init__(self, cfg: Config, read_roots: List[Path], evidence: Evidence,
                 obs_chars: int = 6000, lsp=None):
        self.cfg = cfg
        self.roots = [Path(r).resolve() for r in read_roots]
        self.evidence = evidence
        self.obs_chars = obs_chars
        self.lsp = lsp     # an lsp.LspPool when the job enables language servers

    # -- path handling ---------------------------------------------------------
    def resolve(self, raw: str) -> Path:
        if not raw or not isinstance(raw, str):
            raise ToolError("path is required")
        p = Path(raw.strip().strip('"'))
        if not p.is_absolute():
            p = self.roots[0] / p
        p = p.resolve()
        if not self.cfg.readable(p, self.roots):
            raise ToolError(f"{raw}: outside this job's read roots or denied")
        return p

    def display(self, p: Path) -> str:
        for r in self.roots:
            if p == r or r in p.parents:
                rel = p.relative_to(r).as_posix()
                return rel if r == self.roots[0] else f"{r.as_posix()}/{rel}"
        return p.as_posix()

    def _clip(self, text: str) -> str:
        if len(text) <= self.obs_chars:
            return text
        return text[:self.obs_chars] + (
            f"\n...[clipped at {self.obs_chars} chars; use read_file with "
            f"start/lines to see more]")

    # -- tools -----------------------------------------------------------------
    def list_dir(self, path: str = ".") -> str:
        p = self.resolve(path)
        if not p.is_dir():
            raise ToolError(f"{path}: not a directory")
        rows = []
        for child in sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
            if self.cfg.denied(child.resolve()):
                continue
            if child.is_dir():
                rows.append(f"[dir]  {child.name}/")
            else:
                rows.append(f"[file] {child.name}  ({child.stat().st_size} B)")
        listing = "\n".join(rows) or "(empty)"
        self.evidence.add(p.as_posix(), listing)
        return self._clip(f"{self.display(p)}/\n{listing}")

    def read_file(self, path: str, start: int = 1, lines: int = 200) -> str:
        p = self.resolve(path)
        if not p.is_file():
            raise ToolError(f"{path}: not a file")
        if p.suffix.lower() not in TEXT_SUFFIXES:
            raise ToolError(f"{path}: not a text file type the crew reads")
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ToolError(f"{path}: larger than {MAX_FILE_BYTES} bytes")
        all_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(start or 1))
        lines = max(1, min(int(lines or 200), 400))
        chunk = all_lines[start - 1:start - 1 + lines]
        self.evidence.add(p.as_posix(), "\n".join(chunk))
        body = "\n".join(f"{start + i:>5}| {l}" for i, l in enumerate(chunk))
        more = start - 1 + lines < len(all_lines)
        tail = (f"\n[lines {start}-{start + len(chunk) - 1} of {len(all_lines)}"
                + ("; more below]" if more else "]"))
        return self._clip(f"{self.display(p)}\n{body}{tail}")

    def search(self, pattern: str, path: str = ".", max_hits: int = 30) -> str:
        if not pattern:
            raise ToolError("pattern is required")
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ToolError(f"bad regex: {e}")
        base = self.resolve(path)
        files = [base] if base.is_file() else base.rglob("*")
        hits, scanned = [], 0
        max_hits = max(1, min(int(max_hits or 30), 100))
        for f in files:
            if scanned >= MAX_SEARCH_FILES or len(hits) >= max_hits:
                break
            if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES:
                continue
            fr = f.resolve()
            if self.cfg.denied(fr) or f.stat().st_size > MAX_FILE_BYTES:
                continue
            scanned += 1
            try:
                for n, line in enumerate(fr.read_text(
                        encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{self.display(fr)}:{n}: {line.strip()[:200]}")
                        self.evidence.add(fr.as_posix(), line)
                        if len(hits) >= max_hits:
                            break
            except OSError:
                continue
        return self._clip("\n".join(hits) or f"no matches in {scanned} files")

    def fetch_url(self, url: str, start: int = 1, lines: int = 120,
                  pattern: str = "") -> str:
        """A page as numbered lines, a window at a time - or the lines matching
        `pattern`, so a long document can be searched instead of scrolled."""
        text = self._page(url)
        all_lines = text.splitlines()
        if pattern:
            try:
                rx = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                raise ToolError(f"bad regex: {e}")
            hits = [f"{n:>5}| {line.strip()[:200]}"
                    for n, line in enumerate(all_lines, 1) if rx.search(line)][:40]
            body = "\n".join(hits) or "no matching lines"
            return self._clip(f"{url}\n{body}\n[{len(hits)} matching line(s) of "
                              f"{len(all_lines)}; read around one with start=N]")
        start = max(1, int(start or 1))
        lines = max(1, min(int(lines or 120), 400))
        chunk = all_lines[start - 1:start - 1 + lines]
        body = "\n".join(f"{start + i:>5}| {line}" for i, line in enumerate(chunk))
        more = start - 1 + lines < len(all_lines)
        tail = (f"\n[lines {start}-{start + len(chunk) - 1} of {len(all_lines)}"
                + ("; more below: fetch again with start=N, or pattern=...]"
                   if more else "]"))
        return self._clip(f"{url}\n{body}{tail}")

    def _page(self, url: str) -> str:
        """Fetch once per task; paging through a page must not cost a download
        each time."""
        cache = self.__dict__.setdefault("_pages", {})
        if url in cache:
            return cache[url]
        host = urllib.parse.urlparse(url or "").hostname or ""
        allowed = any(host == d or host.endswith("." + d)
                      for d in self.cfg.fetch_allowlist)
        if not allowed:
            raise ToolError(f"fetch disabled for {host or url!r}: not in the "
                            f"crew fetch allowlist")
        fetch, headers = url, {"User-Agent": "atlas-crew/0.1"}
        m = GITHUB_REPO.match(url)
        if m:
            # A repo page is mostly navigation chrome; its README is the
            # content. GitHub's API serves it raw whatever the branch/filename.
            fetch = f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/readme"
            headers["Accept"] = "application/vnd.github.raw"
        req = urllib.request.Request(fetch, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(1_000_000).decode("utf-8", errors="replace")
        text = html.unescape(re.sub(r"<[^>]+>", " ",
                                    re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)))
        text = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()
        self.evidence.add(url, text)
        cache[url] = text
        return text

    # -- language-server tools (only when the job sets spec.lsp) ----------------
    #
    # Ported from Crush-lite's read-only profile (lsp_symbols, lsp_definition,
    # lsp_references, lsp_diagnostics). Positions are the awkward part of LSP
    # for a small model, so members name a SYMBOL and the harness finds it in
    # the file. Results outside the read roots are counted, never shown.

    def _lsp_file(self, path: str):
        if not self.lsp:
            raise ToolError("language-server tools are not enabled for this task")
        p = self.resolve(path)
        if not p.is_file():
            raise ToolError(f"{path}: not a file")
        lang = self.lsp.language_for(p)
        if not lang:
            raise ToolError(f"{path}: no language server for {p.suffix or 'this'} files")
        return p, lang

    def _lsp_call(self, fn):
        from .lsp import LspError
        try:
            return fn()
        except LspError as e:
            raise ToolError(str(e))

    def _position_of(self, p: Path, name: str):
        if not name or not re.fullmatch(r"[A-Za-z_][\w.]*", name):
            raise ToolError("name must be an identifier, e.g. parse or Box.size")
        word = name.rsplit(".", 1)[-1]
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        # a bare name first (foo), then as an attribute (mod.foo)
        for rx in (re.compile(rf"(?<![\w.]){re.escape(word)}\b"),
                   re.compile(rf"\b{re.escape(word)}\b")):
            for n, line in enumerate(lines):
                m = rx.search(line.split("#", 1)[0])
                if m:
                    return n, m.start()
        raise ToolError(f"{name!r} does not appear in {self.display(p)}")

    def _show_locations(self, locs: List[dict], limit: int = 30) -> str:
        from .lsp import uri_to_path
        rows, hidden, cache = [], 0, {}
        for loc in locs:
            q = uri_to_path(loc["uri"])
            if not self.cfg.readable(q, self.roots):
                hidden += 1
                continue
            if q not in cache:
                cache[q] = q.read_text(encoding="utf-8", errors="replace").splitlines()
            lines = cache[q]
            text = lines[loc["line"]].strip() if loc["line"] < len(lines) else ""
            self.evidence.add(q.as_posix(), text)
            rows.append(f"{self.display(q)}:{loc['line'] + 1}: {text[:200]}")
            if len(rows) >= limit:
                break
        if hidden:
            rows.append(f"({hidden} location(s) outside this job's read roots, "
                        f"not shown)")
        return "\n".join(rows) or "no locations found"

    def symbols(self, path: str) -> str:
        from .lsp import flatten_symbols
        p, lang = self._lsp_file(path)
        client = self._lsp_call(lambda: self.lsp.client(lang))
        uri = client.open(p, language_id=lang)
        rows = self._lsp_call(lambda: flatten_symbols(client.symbols(uri)))
        body = "\n".join(f"{'  ' * d}L{line} {kind} {name}" for d, kind, name, line in rows)
        self.evidence.add(p.as_posix(), body)
        return self._clip(f"{self.display(p)} (outline)\n{body or '(no symbols)'}")

    def definition(self, path: str, name: str) -> str:
        p, lang = self._lsp_file(path)
        line, char = self._position_of(p, name)
        client = self._lsp_call(lambda: self.lsp.client(lang))
        uri = client.open(p, language_id=lang)
        locs = self._lsp_call(lambda: client.definition(uri, line, char))
        return self._clip(f"definition of {name} (as used at "
                          f"{self.display(p)}:{line + 1}):\n" + self._show_locations(locs))

    def references(self, path: str, name: str) -> str:
        p, lang = self._lsp_file(path)
        line, char = self._position_of(p, name)
        client = self._lsp_call(lambda: self.lsp.client(lang))
        uri = client.open(p, language_id=lang)
        locs = self._lsp_call(lambda: client.references(uri, line, char))
        return self._clip(f"references to {name}:\n" + self._show_locations(locs))

    def diagnostics(self, path: str) -> str:
        from .lsp import format_diagnostics
        p, lang = self._lsp_file(path)
        client = self._lsp_call(lambda: self.lsp.client(lang, diagnostics=True))
        uri = client.open(p, language_id=lang)
        rows = format_diagnostics(self._lsp_call(lambda: client.diagnostics(uri)))
        body = "\n".join(rows) or "no errors or warnings"
        self.evidence.add(p.as_posix(), body)
        return self._clip(f"{self.display(p)} (diagnostics)\n{body}")

    def call(self, name: str, args: Optional[dict]) -> str:
        args = args or {}
        tools = {"list_dir": self.list_dir, "read_file": self.read_file,
                 "search": self.search, "fetch_url": self.fetch_url}
        if self.lsp:
            tools.update(symbols=self.symbols, definition=self.definition,
                         references=self.references, diagnostics=self.diagnostics)
        fn = tools.get(name)
        if fn is None:
            raise ToolError(f"unknown tool {name!r}; tools: {', '.join(tools)}")
        try:
            return fn(**args)
        except TypeError as e:
            raise ToolError(f"bad arguments for {name}: {e}")

    def evidence_key(self, cited: str, opened_only: bool = False) -> Optional[str]:
        """Map a citation (relative path, absolute path, url, wikilink
        target) onto an evidence key, or None if never observed (or, with
        opened_only, never opened by the member itself)."""
        key = self._evidence_key(cited)
        if key and opened_only and key not in self.evidence.opened:
            return None
        return key

    def _evidence_key(self, cited: str) -> Optional[str]:
        cited = cited.strip()
        if cited.startswith(("http://", "https://")):
            return cited if cited in self.evidence.seen else None
        candidates = [cited, cited + ".md"] if not cited.endswith(".md") else [cited]
        for c in candidates:
            p = Path(c)
            for base in ([p] if p.is_absolute() else [r / p for r in self.roots]):
                key = base.resolve().as_posix()
                if key in self.evidence.seen:
                    return key
        # Obsidian wikilinks may name a note by basename only.
        stem = Path(cited).name.removesuffix(".md").lower()
        for key in self.evidence.seen:
            if Path(key).stem.lower() == stem:
                return key
        return None
