"""Do the tests catch seeded defects in a Rust module? The Rust twin of mutants.py.

    python crew/runners/rs_mutants.py --profile photo_tools --module path/to/sobel.rs
        --tests path/to/hidden_sobel.rs [--deps a.rs b.rs] [--max 12]

Each mutant changes ONE code token (never a string or comment): a comparison flipped
(`<` <-> `<=`, `>` <-> `>=`, `==` <-> `!=`), `&&` <-> `||`, a binary `+`/`-` swapped, an
integer literal moved by one, `.round()` -> `.floor()`, `true` <-> `false`. Comparisons
and arithmetic are only mutated when written with spaces around them, so generics
(`Vec<u8>`) are left alone. Each mutant is built and tested by rsrun (same profile,
same caps). A mutant the tests do not kill is a SURVIVOR: either the tests miss a rule,
or the change is equivalent - read each one.
"""

import argparse
import sys
from pathlib import Path

CREW = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CREW))
import rsrun  # noqa: E402  (puts crew/rsharness on the path)
import rs_lex  # noqa: E402

SWAP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "==",
        "&&": "||", "||": "&&", "+": "-", "-": "+", "true": "false", "false": "true"}
SPACED = {"<", "<=", ">", ">=", "==", "!=", "&&", "||", "+", "-"}


def mutants(src: str):
    """(line, description, mutated source) for every candidate, in source order."""
    toks = rs_lex.tokens(src)
    out = []
    for k, t in enumerate(toks):
        a, b = t.start, t.start + len(t.text)
        if t.start < 0:
            continue
        spaced = 0 < a and b < len(src) and src[a - 1] == " " and src[b] == " "
        new = None
        if t.text in SWAP and (t.text not in SPACED or spaced):
            new = SWAP[t.text]
        elif t.kind == "num" and t.text.isdigit():
            new = str(int(t.text) + 1)
        elif (t.kind == "ident" and t.text == "round" and k > 0
              and toks[k - 1].text == "."):
            new = "floor"
        if new is not None:
            out.append((t.line, f"`{t.text}` -> `{new}`", src[:a] + new + src[b:]))
    return out


def spread(items, limit):
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--tests", nargs="+", required=True)
    ap.add_argument("--deps", nargs="*", default=[])
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=30)
    a = ap.parse_args(argv)
    mod = Path(a.module)
    src = mod.read_text(encoding="utf-8")
    deps = {Path(d).name: Path(d).read_text(encoding="utf-8") for d in a.deps}
    tests = {Path(t).name: Path(t).read_text(encoding="utf-8") for t in a.tests}
    base = rsrun.run_cargo_tests(a.profile, {mod.name: src, **deps}, tests, a.timeout)
    if not base["ok"]:
        print(f"{mod.name}: the unmutated module does not pass - fix that first\n"
              + base["summary"])
        return 2
    chosen = spread(mutants(src), a.max)
    killed, built_no, survivors = 0, 0, []
    for line, desc, msrc in chosen:
        res = rsrun.run_cargo_tests(a.profile, {mod.name: msrc, **deps}, tests, a.timeout)
        if res["stage"] == "compile":
            built_no += 1
        elif res["ok"]:
            survivors.append(f"line {line}: {desc}")
        else:
            killed += 1
    tested = len(chosen) - built_no
    print(f"{mod.name}: {len(chosen)} mutants, {built_no} did not compile, "
          f"{killed}/{tested} killed by the tests")
    for s in survivors:
        print(f"  SURVIVED {s}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
