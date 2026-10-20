"""Tell Rust code from comments, strings and character literals.

Every check above this one asks "is this word code?", and a wrong answer in one
direction hides code from the safety scan. So the lexer follows rustc's own rules
for the cases that matter: nested block comments, raw strings with any number of
hashes, byte/C string prefixes, and the char-versus-lifetime question after `'`.
When it cannot finish a literal or comment it says so (kind "error"), and the
scan refuses the file rather than guess.

Tokens are (kind, text, line) with kind one of: ident, lifetime, char, str, num,
punct, error. Comments and whitespace are dropped; doc comments are comments.
"""

from typing import List, NamedTuple


class Token(NamedTuple):
    kind: str
    text: str
    line: int
    start: int = -1          # offset in the source (used by rs_mutants.py)


# Longest first: only `::`, `->`, `=>`, `!=` and `..` matter to the checks, the rest
# keep tokens honest (so `!=` is never read as a macro's `!`).
PUNCTS = ("<<=", ">>=", "...", "..=", "::", "->", "=>", "==", "!=", "<=", ">=", "&&",
          "||", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|=", "<<", ">>", "..")
STRING_PREFIXES = ("br", "cr", "b", "c", "r")


def _ident_start(c: str) -> bool:
    return c == "_" or c.isalpha()


def _ident_char(c: str) -> bool:
    return c == "_" or c.isalnum()


class _Lexer:
    def __init__(self, src: str):
        self.s = src
        self.i = 0
        self.line = 1
        self.out: List[Token] = []

    def peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < len(self.s) else ""

    def emit(self, kind: str, start: int, line: int) -> None:
        self.out.append(Token(kind, self.s[start:self.i], line, start))

    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            if self.i < len(self.s):
                if self.s[self.i] == "\n":
                    self.line += 1
                self.i += 1

    def fail(self, start: int, line: int, why: str) -> None:
        self.out.append(Token("error", why, line))
        self.i = len(self.s)

    # -- pieces -------------------------------------------------------------------
    def block_comment(self) -> bool:
        start, line, depth = self.i, self.line, 0
        while self.i < len(self.s):
            if self.peek() == "/" and self.peek(1) == "*":
                depth += 1
                self.advance(2)
            elif self.peek() == "*" and self.peek(1) == "/":
                depth -= 1
                self.advance(2)
                if depth == 0:
                    return True
            else:
                self.advance()
        self.fail(start, line, "unterminated block comment")
        return False

    def quoted(self, quote: str, kind: str, start: int, line: int) -> None:
        """From the opening quote: a string or char body with backslash escapes."""
        self.advance()
        while self.i < len(self.s):
            c = self.peek()
            if c == "\\":
                self.advance(2)
            elif c == quote:
                self.advance()
                self.emit(kind, start, line)
                return
            else:
                self.advance()
        self.fail(start, line, f"unterminated {kind} literal")

    def raw_string(self, start: int, line: int) -> None:
        """From the `r`: r"..." or r#"..."# with any number of hashes."""
        self.advance()                          # r
        hashes = 0
        while self.peek() == "#":
            hashes += 1
            self.advance()
        if self.peek() != '"':
            self.fail(start, line, "malformed raw string")
            return
        self.advance()
        closing = '"' + "#" * hashes
        end = self.s.find(closing, self.i)
        if end < 0:
            self.fail(start, line, "unterminated raw string")
            return
        self.advance(end + len(closing) - self.i)
        self.emit("str", start, line)

    def string_with_prefix(self) -> bool:
        """b"..", c"..", r"..", r#".."#, br.., cr.. and b'x'. False if not one."""
        for p in STRING_PREFIXES:
            if not self.s.startswith(p, self.i):
                continue
            after = self.peek(len(p))
            start, line = self.i, self.line
            if p.endswith("r") and (after == '"' or (after == "#" and self._raw_ahead(len(p)))):
                self.advance(len(p) - 1)
                self.raw_string(start, line)
                return True
            if after == '"' and not p.endswith("r"):
                self.advance(len(p))
                self.quoted('"', "str", start, line)
                return True
            if p == "b" and after == "'":
                self.advance(1)
                self.quoted("'", "char", start, line)
                return True
        return False

    def _raw_ahead(self, k: int) -> bool:
        """After r and some hashes, is there a quote (raw string), not an ident (r#name)?"""
        j = self.i + k
        while j < len(self.s) and self.s[j] == "#":
            j += 1
        return j < len(self.s) and self.s[j] == '"'

    def quote(self) -> None:
        """At `'`: a char literal ('x', '\\n', '\\u{..}') or a lifetime/label ('a)."""
        start, line = self.i, self.line
        nxt, after = self.peek(1), self.peek(2)
        if nxt == "\\":
            self.quoted("'", "char", start, line)
        elif nxt and nxt != "'" and after == "'":
            self.advance(3)
            self.emit("char", start, line)
        elif _ident_start(nxt):
            self.advance()
            while _ident_char(self.peek()):
                self.advance()
            self.emit("lifetime", start, line)
        else:
            self.fail(start, line, "a quote that is neither a char literal nor a lifetime")

    def number(self) -> None:
        start, line = self.i, self.line
        while _ident_char(self.peek()):
            self.advance()
        text = self.s[start:self.i].lower()
        if not text.startswith(("0x", "0b", "0o")):
            if self.peek() == "." and self.peek(1).isdigit():
                self.advance()
                while _ident_char(self.peek()):
                    self.advance()
            body = self.s[start:self.i].lower()
            if body.endswith("e") and self.peek() in "+-" and self.peek(1).isdigit():
                self.advance()
                while _ident_char(self.peek()):
                    self.advance()
            elif self.peek() == "." and not (self.peek(1) == "." or _ident_start(self.peek(1))):
                self.advance()                    # `1.` is a float literal
        self.emit("num", start, line)

    # -- the loop -------------------------------------------------------------------
    def run(self) -> List[Token]:
        while self.i < len(self.s):
            c = self.peek()
            if c in " \t\r\n\f\v":
                self.advance()
            elif c == "/" and self.peek(1) == "/":
                while self.i < len(self.s) and self.peek() != "\n":
                    self.advance()
            elif c == "/" and self.peek(1) == "*":
                if not self.block_comment():
                    break
            elif c == '"':
                self.quoted('"', "str", self.i, self.line)
            elif c == "'":
                self.quote()
            elif self.string_with_prefix():
                pass
            elif c == "r" and self.peek(1) == "#" and _ident_start(self.peek(2)):
                start, line = self.i, self.line
                self.advance(2)
                while _ident_char(self.peek()):
                    self.advance()
                self.out.append(Token("ident", self.s[start + 2:self.i], line, start + 2))
            elif _ident_start(c):
                start, line = self.i, self.line
                while _ident_char(self.peek()):
                    self.advance()
                self.emit("ident", start, line)
            elif c.isdigit():
                self.number()
            else:
                start, line = self.i, self.line
                for p in PUNCTS:
                    if self.s.startswith(p, self.i):
                        self.advance(len(p))
                        break
                else:
                    self.advance()
                self.emit("punct", start, line)
        return self.out


def tokens(src: str) -> List[Token]:
    """All tokens of `src`, comments and whitespace removed."""
    return _Lexer(src).run()


def code_only(src: str) -> str:
    """The code tokens joined by spaces: strings, chars and comments blanked out."""
    return " ".join('""' if t.kind == "str" else "' '" if t.kind == "char" else t.text
                    for t in tokens(src))


def errors(src: str) -> List[Token]:
    return [t for t in tokens(src) if t.kind == "error"]
