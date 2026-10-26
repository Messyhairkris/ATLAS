"""Reference for codemap.py: file outlines and a repository map (PA-written)."""

import ast
import re

LANGUAGES = {".py": "python", ".pyw": "python", ".js": "js", ".mjs": "js", ".cjs": "js",
             ".jsx": "js", ".ts": "js", ".tsx": "js", ".rs": "rust", ".ahk": "ahk"}

_N = r"[A-Za-z_$][\w$]*"
JS = [(re.compile(rf"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\b\s*\*?\s*({_N})"),
       "function"),
      (re.compile(rf"^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+({_N})"), "class"),
      (re.compile(rf"^\s*(?:export\s+)?(?:const|let|var)\s+({_N})\s*=\s*(?:async\s+)?"
                  rf"(?:function\b|\([^)]*\)\s*=>|{_N}\s*=>)"), "function"),
      (re.compile(rf"^export\s+(?:const|let|var)\s+({_N})"), "const"),
      (re.compile(rf"^\s*(?:export\s+)?(?:interface|type)\s+({_N})"), "type")]
RS_FN = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?(?:(?:async|const|unsafe|extern(?:\s+"[^"]*")?)'
                   r"\s+)*fn\s+(\w+)")
RS_ITEM = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(struct|enum|trait|mod|type)\s+(\w+)")
RS_IMPL = re.compile(r"^\s*impl\b(?:\s*<[^>]*>)?\s+([^{]+?)\s*(?:\{.*)?$")
AHK_FN = re.compile(r"^([A-Za-z_][\w#@$]*)\(([^()]*)\)\s*(\{)?\s*(?:;.*)?$")
AHK_HOTSTRING = re.compile(r"^(:[^:\s]*:[^:]+)::")
AHK_LABEL = re.compile(r"^([A-Za-z_][\w#@$]*):\s*(?:;.*)?$")
AHK_HOTKEY = re.compile(r"^([^\s;:][^:]*?)::")
AHK_NOT_FUNCTIONS = {"if", "while", "for", "loop", "return", "switch", "else", "catch", "until"}


def language_of(path: str) -> str | None:
    segment = re.split(r"[/\\]", path)[-1]
    if "." not in segment:
        return None
    return LANGUAGES.get(segment[segment.rindex("."):].lower())


def _lines(source: str) -> list[str]:
    return [line[:-1] if line.endswith("\r") else line for line in source.split("\n")]


def _python(source: str) -> list:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        out = []
        for n, line in enumerate(_lines(source), 1):
            m = re.match(r"^\s*(?:async\s+)?def\s+(\w+)", line)
            if m:
                out.append((n, "def", m.group(1)))
                continue
            m = re.match(r"^\s*class\s+(\w+)", line)
            if m:
                out.append((n, "class", m.group(1)))
        return out
    fn = (ast.FunctionDef, ast.AsyncFunctionDef)
    out = []
    for node in tree.body:
        if isinstance(node, fn):
            out.append((node.lineno, "def", node.name))
        elif isinstance(node, ast.ClassDef):
            out.append((node.lineno, "class", node.name))
            out += [(m.lineno, "method", f"{node.name}.{m.name}") for m in node.body
                    if isinstance(m, fn)]
    return out


def _js(source: str) -> list:
    out = []
    for n, line in enumerate(_lines(source), 1):
        for pattern, kind in JS:
            m = pattern.match(line)
            if m:
                out.append((n, kind, m.group(1)))
                break
    return out


def _rust(source: str) -> list:
    out = []
    for n, line in enumerate(_lines(source), 1):
        if m := RS_FN.match(line):
            out.append((n, "fn", m.group(1)))
        elif m := RS_ITEM.match(line):
            out.append((n, m.group(1), m.group(2)))
        elif m := RS_IMPL.match(line):
            out.append((n, "impl", " ".join(m.group(1).split())))
    return out


def _ahk(source: str) -> list:
    lines = _lines(source)
    out = []
    for i, line in enumerate(lines):
        if not line or line[0] in " \t":
            continue
        m = AHK_FN.match(line)
        if m and m.group(1).lower() not in AHK_NOT_FUNCTIONS:
            nxt = next((ln.strip() for ln in lines[i + 1:]
                        if ln.strip() and not ln.strip().startswith(";")), "")
            if m.group(3) or nxt.startswith("{"):
                out.append((i + 1, "function", m.group(1)))
                continue
        for pattern, kind in ((AHK_HOTSTRING, "hotstring"), (AHK_LABEL, "label"),
                              (AHK_HOTKEY, "hotkey")):
            if m := pattern.match(line):
                out.append((i + 1, kind, m.group(1)))
                break
    return out


def outline(source: str, language: str) -> list[tuple[int, str, str]]:
    """The file's definitions as (line, kind, name), in line order."""
    reader = {"python": _python, "js": _js, "rust": _rust, "ahk": _ahk}.get(language)
    if reader is None:
        return []
    found = reader(source)
    return [s for _, s in sorted(enumerate(found), key=lambda p: (p[1][0], p[0]))]


def render_outline(path: str, symbols: list[tuple[int, str, str]], max_lines: int = 80) -> str:
    if not symbols:
        return f"{path}\n  (no symbols found)"
    lines = [path] + [f"  {line:>5}  {kind} {name}" for line, kind, name in symbols[:max_lines]]
    if len(symbols) > max_lines:
        lines.append(f"  ... {len(symbols) - max_lines} more")
    return "\n".join(lines)


def repo_map(files: dict[str, str], max_chars: int = 6000) -> str:
    known = [p for p in sorted(files) if language_of(p)]
    if not known:
        return "(no code files)"
    text = ""
    for i, path in enumerate(known):
        symbols = outline(files[path], language_of(path))
        block = "\n".join([path] + ([f"  {k} {n}" for _, k, n in symbols] or ["  (no symbols)"]))
        candidate = block if not text else f"{text}\n{block}"
        if len(candidate) > max_chars:
            rest = f"... {len(known) - i} more files"
            return f"{text}\n{rest}" if text else rest
        text = candidate
    return text
