"""The Rust safety scan: what a crew-written file may name before it is compiled.

Native code has no permission sandbox like Node's `--permission`, so this scan is
the main wall and it works by ALLOWLIST: the file may use the parts of std that
cannot reach the machine, the crates its profile lists (minus their I/O), its own
crate, and nothing else. Without `unsafe`, `extern`, std's fs/net/process/env/
path/io/os/ffi/thread and the include!/env! macros, safe Rust has no way to touch
files, the network or other processes. A Windows job object (rsrun.py) caps
memory, child processes and time behind it.

A profile (rsharness/profiles/<name>/profile.json) says which crates exist:
  {"crate_name": "photo_tools",
   "crates": {"image": {"banned_paths": ["image::open"], "banned_methods": ["save"],
                        "banned_idents": ["ImageReader"]}}}
banned_paths match a path prefix as written; banned_methods match a name called
after `.` or `::`; banned_idents match the name anywhere in code.

Every problem is a sentence a member can act on, with the line number.
"""

from typing import Dict, List, Optional

from rs_lex import Token, tokens

STD_ROOTS = {"std", "core", "alloc"}
STD_ALLOWED = {
    "any", "array", "ascii", "borrow", "boxed", "cell", "char", "clone", "cmp",
    "collections", "convert", "default", "error", "f32", "f64", "fmt", "hash", "hint",
    "i8", "i16", "i32", "i64", "i128", "isize", "iter", "marker", "mem", "num", "ops",
    "option", "prelude", "primitive", "rc", "result", "slice", "str", "string", "sync",
    "time", "u8", "u16", "u32", "u64", "u128", "usize", "vec"}
LOCAL_ROOTS = {"crate", "self", "super", "Self"}
BANNED_KEYWORDS = {"unsafe": "`unsafe` is not allowed",
                   "extern": "`extern` (FFI or extern crate) is not allowed"}
BANNED_MACROS = {"include", "include_str", "include_bytes", "env", "option_env", "asm",
                 "global_asm", "naked_asm", "macro_rules", "concat_idents",
                 "trace_macros", "log_syntax"}
ALLOWED_ATTRS = {"derive", "cfg", "test", "inline", "must_use", "allow", "warn",
                 "expect", "doc", "non_exhaustive", "repr", "track_caller", "cold",
                 "should_panic", "arg", "command", "value", "default", "rustfmt",
                 "clippy"}
OUTSIDE = "reaches the file system or the outside world; work on values passed in"


class _Scan:
    def __init__(self, toks: List[Token], profile: dict):
        self.t = toks
        self.crates: Dict[str, dict] = dict(profile.get("crates") or {})
        self.own = profile.get("crate_name") or ""
        self.roots = STD_ROOTS | set(self.crates)
        self.problems: List[str] = []

    # -- helpers --------------------------------------------------------------------------
    def add(self, line: int, text: str) -> None:
        msg = f"line {line}: {text}"
        if msg not in self.problems:
            self.problems.append(msg)

    def at(self, i: int) -> Optional[Token]:
        return self.t[i] if 0 <= i < len(self.t) else None

    def is_p(self, i: int, text: str) -> bool:
        tok = self.at(i)
        return tok is not None and tok.kind == "punct" and tok.text == text

    def is_id(self, i: int, text: str = "") -> bool:
        tok = self.at(i)
        return tok is not None and tok.kind == "ident" and (not text or tok.text == text)

    def local(self, root: str) -> bool:
        return root in LOCAL_ROOTS or (bool(self.own) and root == self.own)

    def allowed_list(self) -> str:
        return ", ".join(["std"] + sorted(self.crates))

    # -- judgements ---------------------------------------------------------------------
    def judge_path(self, path: List[str], line: int) -> None:
        """A path as written, e.g. ['std', 'fs', 'read'] or ['image', 'open']."""
        root = path[0]
        if root in STD_ROOTS:
            if len(path) > 1 and path[1] not in STD_ALLOWED:
                self.add(line, f"`{'::'.join(path[:2])}` is outside the allowed part of "
                               f"std (allowed: {', '.join(sorted(STD_ALLOWED))})")
        elif root in self.crates:
            for banned in self.crates[root].get("banned_paths", []):
                if path[:len(banned.split('::'))] == banned.split("::"):
                    self.add(line, f"`{banned}` {OUTSIDE}")

    def judge_name(self, i: int) -> None:
        """Per-name rules: banned macros, banned methods, banned identifiers."""
        tok = self.t[i]
        if self.is_p(i + 1, "!") and tok.text in BANNED_MACROS:
            self.add(tok.line, f"`{tok.text}!` is not allowed")
        after_sep = self.is_p(i - 1, ".") or self.is_p(i - 1, "::")
        for crate in self.crates.values():
            if (after_sep and tok.text in crate.get("banned_methods", [])) or \
                    tok.text in crate.get("banned_idents", []):
                self.add(tok.line, f"`{tok.text}` {OUTSIDE}")

    def judge_use(self, path: List[str], line: int) -> None:
        """One expanded leaf of a `use` tree; '*' marks a glob."""
        root = path[0]
        if path[-1] == "*":
            if not self.local(root):
                self.add(line, f"glob import `{'::'.join(path)}`: import the names you "
                               f"use one by one (only `super::*` and your own crate's "
                               f"modules may be glob-imported)")
            return
        if len(path) == 1 and root in self.roots:
            self.add(line, f"`use {root}` imports a whole crate root; import the items "
                           f"you need by their full path")
        elif not self.local(root) and root not in self.roots:
            self.add(line, f"`use {'::'.join(path)}`: `{root}` is not a crate this task "
                           f"may use (allowed: {self.allowed_list()}, crate::, super::)")
        else:
            self.judge_path(path, line)

    # -- use trees ------------------------------------------------------------------------
    def use_tree(self, i: int, prefix: List[str], line: int) -> int:
        """Expand one use tree from token i; returns the index after it."""
        path = list(prefix)
        if self.is_p(i, "::"):
            i += 1
        while True:
            tok = self.at(i)
            if tok is None:
                return i
            if tok.kind == "ident":
                i += 1
                if tok.text == "self" and path:
                    leaf = path
                else:
                    path.append(tok.text)
                    if self.is_p(i, "::"):
                        i += 1
                        continue
                    leaf = path
                if self.is_id(i, "as"):
                    i += 2                    # an alias is judged by its source path
                self.judge_use(leaf, tok.line)
                return i
            if tok.kind == "punct" and tok.text == "*" and path:
                self.judge_use(path + ["*"], tok.line)
                return i + 1
            if tok.kind == "punct" and tok.text == "{":
                i += 1
                while self.at(i) is not None and not self.is_p(i, "}"):
                    before = i
                    i = self.use_tree(i, path, tok.line)
                    if self.is_p(i, ","):
                        i += 1
                    if i == before:
                        i += 1
                return i + 1
            self.add(tok.line, f"could not read this `use` declaration at `{tok.text}`")
            return i + 1

    # -- paths --------------------------------------------------------------------------
    def path_at(self, i: int) -> int:
        """Collect ident(::ident)* from i, judge it and every crate root inside it."""
        start = i
        while True:
            self.judge_name(i)
            if self.is_p(i + 1, "::") and self.is_id(i + 2):
                i += 2
                continue
            break
        path = [self.t[k].text for k in range(start, i + 1, 2)]
        line = self.t[start].line
        for k, seg in enumerate(path):
            if seg in self.roots:
                self.judge_path(path[k:], line)
        return i + 1

    def attribute(self, i: int) -> None:
        line = self.t[i].line
        if self.is_p(i + 1, "!"):
            self.add(line, "inner attributes (`#![...]`) are not allowed")
            return
        if not self.is_p(i + 1, "["):
            return
        name = self.at(i + 2)
        if name is None or name.kind != "ident" or name.text not in ALLOWED_ATTRS:
            shown = name.text if name is not None else "?"
            self.add(line, f"attribute `#[{shown}]` is not allowed (allowed: "
                           f"{', '.join(sorted(ALLOWED_ATTRS))})")

    # -- the walk -------------------------------------------------------------------------
    def run(self) -> List[str]:
        n = len(self.t)
        i = 0
        while i < n:
            tok = self.t[i]
            if tok.kind == "error":
                self.add(tok.line, f"the file could not be read as Rust: {tok.text}")
                return self.problems
            if tok.kind == "punct" and tok.text == "#":
                self.attribute(i)
            if tok.kind != "ident":
                i += 1
                continue
            if tok.text in BANNED_KEYWORDS:
                self.add(tok.line, BANNED_KEYWORDS[tok.text])
            if tok.text == "use" and not self.is_p(i - 1, "::"):
                self.use_tree(i + 1, [], tok.line)
                while i < n and not self.is_p(i, ";"):
                    i += 1
                i += 1
                continue
            if tok.text == "mod" and self.is_id(i + 1) and self.is_p(i + 2, ";"):
                self.add(tok.line, f"`mod {self.t[i + 1].text};` loads another file; "
                                   f"write everything in this one file")
            if self.is_p(i - 1, "."):
                self.judge_name(i)
                i += 1
            elif self.is_p(i - 1, "::") and tok.text not in self.roots:
                self.judge_name(i)
                i += 1
            else:
                # A path's first segment, or `::std` after anything at all (`> ::std`,
                # `return ::std`): a crate root is judged wherever it appears.
                i = self.path_at(i)
        return self.problems


def scan(source: str, profile: dict) -> List[str]:
    """Problems that stop `source` being compiled; empty means it may be built."""
    return _Scan(tokens(source), profile).run()


def scan_many(files: Dict[str, str], profile: dict) -> List[str]:
    out = []
    for name, src in sorted(files.items()):
        out += [f"{name} {p}" for p in scan(src, profile)]
    return out
