"""Does a Rust file define the contract's API, and is any of it a stub?

API entries are either a plain name, matched by `pub <kind> Name` at any depth
(fn, struct, enum, const, static, type, trait, mod, or `pub use .. as Name`), or
`Type::method`, matched by `fn method` inside an `impl` block whose self type is
`Type` (an inherent impl or `impl Trait for Type`). The hidden tests are the real
check; this one exists so a missing or renamed item gets a clear sentence instead
of forty lines of compiler output.
"""

from typing import List, Optional, Tuple

from rs_lex import Token, tokens

ITEM_KINDS = {"fn", "struct", "enum", "const", "static", "type", "trait", "mod"}
FN_QUALIFIERS = {"const", "async", "unsafe"}
STUB_MACROS = {"todo", "unimplemented", "unreachable", "panic"}
ALWAYS_STUB = {"todo", "unimplemented"}


def _match(toks: List[Token], i: int) -> int:
    """Index of the bracket closing the one at i (or len(toks))."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    open_, close = toks[i].text, pairs[toks[i].text]
    depth = 0
    for k in range(i, len(toks)):
        if toks[k].kind != "punct":
            continue
        if toks[k].text == open_:
            depth += 1
        elif toks[k].text == close:
            depth -= 1
            if depth == 0:
                return k
    return len(toks)


def _pub_items(toks: List[Token]) -> List[str]:
    names = []
    for i, t in enumerate(toks):
        if t.kind != "ident" or t.text != "pub":
            continue
        k = i + 1
        if k < len(toks) and toks[k].text == "(":            # pub(crate)
            k = _match(toks, k) + 1
        while k < len(toks) and toks[k].text in FN_QUALIFIERS and \
                k + 1 < len(toks) and toks[k + 1].text in ITEM_KINDS | FN_QUALIFIERS:
            k += 1
        if k + 1 < len(toks) and toks[k].text in ITEM_KINDS and toks[k + 1].kind == "ident":
            names.append(toks[k + 1].text)
        elif k < len(toks) and toks[k].text == "use":
            j = k
            while j < len(toks) and toks[j].text != ";":
                if toks[j].text == "as" and j + 1 < len(toks):
                    names.append(toks[j + 1].text)
                j += 1
            if j - 1 > k and toks[j - 1].kind == "ident":
                names.append(toks[j - 1].text)
    return names


def _impl_self_type(toks: List[Token], i: int) -> Tuple[Optional[str], int]:
    """For `impl` at i: (last ident of the self type, index of its `{`)."""
    k = i + 1
    if k < len(toks) and toks[k].text == "<":                 # impl<T>
        depth = 0
        while k < len(toks):
            depth += {"<": 1, ">": -1, ">>": -2}.get(toks[k].text, 0)
            k += 1
            if depth <= 0:
                break
    last, depth = None, 0
    while k < len(toks) and not (toks[k].text == "{" and depth == 0):
        tx = toks[k].text
        if tx == "<":
            depth += 1
        elif tx in (">", ">>"):
            depth -= 1 if tx == ">" else 2
        elif tx == "for" and depth == 0:
            last = None
        elif tx == "where" and depth == 0:
            while k < len(toks) and toks[k].text != "{":
                k += 1
            break
        elif toks[k].kind == "ident" and depth == 0:
            last = tx
        k += 1
    return last, k


def _impl_methods(toks: List[Token]) -> List[str]:
    out = []
    for i, t in enumerate(toks):
        if t.kind != "ident" or t.text != "impl":
            continue
        ty, brace = _impl_self_type(toks, i)
        if ty is None or brace >= len(toks):
            continue
        end = _match(toks, brace)
        depth = 0
        for k in range(brace + 1, end):
            tx = toks[k].text
            if tx == "{":
                depth += 1
            elif tx == "}":
                depth -= 1
            elif depth == 0 and tx == "fn" and k + 1 < end and toks[k + 1].kind == "ident":
                out.append(f"{ty}::{toks[k + 1].text}")
    return out


def missing_api(source: str, api: List[str]) -> List[str]:
    toks = tokens(source)
    have = set(_pub_items(toks)) | set(_impl_methods(toks))
    return [name for name in api if name not in have]


def _fn_bodies(toks: List[Token]):
    """(name, body tokens) for every fn with a body."""
    for i, t in enumerate(toks):
        if (t.kind != "ident" or t.text != "fn" or i + 1 >= len(toks)
                or toks[i + 1].kind != "ident"):
            continue                                    # `fn(u8) -> u8` is a type
        name = toks[i + 1].text
        k = i + 2
        while k < len(toks) and toks[k].text not in ("{", ";"):
            if toks[k].text in ("(", "["):
                k = _match(toks, k)
            k += 1
        if k < len(toks) and toks[k].text == "{":
            yield name, toks[k + 1:_match(toks, k)]


def stubs(source: str) -> List[str]:
    """Functions that do nothing: an empty body, a body that is only todo!(),
    unimplemented!(), unreachable!() or panic!(), and any todo!/unimplemented!."""
    toks = tokens(source)
    out = []
    for name, body in _fn_bodies(toks):
        if not body:
            out.append(name)
        elif (body[0].kind == "ident" and body[0].text in STUB_MACROS
              and len(body) > 2 and body[1].text == "!" and body[2].text in "([{"
              and _match(body, 2) >= len(body) - 2):
            out.append(name)
    for i, t in enumerate(toks):
        if (t.kind == "ident" and t.text in ALWAYS_STUB and i + 1 < len(toks)
                and toks[i + 1].text == "!"):
            out.append(f"{t.text}!() at line {t.line}")
    return sorted(set(out))


def count_tests(source: str) -> int:
    """`#[test]` attributes in code (not in comments or strings)."""
    toks = tokens(source)
    return sum(1 for i in range(len(toks) - 3)
               if toks[i].text == "#" and toks[i + 1].text == "["
               and toks[i + 2].text == "test" and toks[i + 3].text == "]")
