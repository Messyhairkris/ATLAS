"""Check an exported VtoT document against the formatting test spec.

Each line of the test document states the formatting it should have. This reads
the saved .html, finds the element containing each line's text, and verifies the
claim. Deterministic and zero tokens: the harness decides pass/fail, and a crew
member only explains the failures.

    python format_check.py <exported.html> [spec.json]

Prints one PASS/FAIL per line plus a pytest-shaped summary, so the crew's
"quote the totals verbatim" gate works unchanged. Exit 1 if any line failed.
"""

import html as html_mod
import json
import re
import sys
import unicodedata
from pathlib import Path

DEFAULT_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "format_test_doc.json"
BLOCK = re.compile(r"<(h[1-6]|p|li|blockquote|pre|div)\b([^>]*)>(.*?)</\1>",
                   re.IGNORECASE | re.DOTALL)
LIST_OPEN = re.compile(r"<(ul|ol)\b", re.IGNORECASE)
LIST_CLOSE = re.compile(r"</(ul|ol)\s*>", re.IGNORECASE)
TAGS = re.compile(r"<[^>]+>")


def normalize(text: str) -> str:
    """Compare on words only: exports differ in entities, spacing and dashes."""
    text = html_mod.unescape(TAGS.sub(" ", text))
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[‐-―]", "-", text)
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def blocks_with_context(html: str) -> list:
    """(normalized text, raw block html, enclosing list tag or '') per block."""
    out = []
    for m in BLOCK.finditer(html):
        tag, attrs, inner = m.group(1).lower(), m.group(2), m.group(3)
        before = html[:m.start()]
        opens = [t.lower() for t in LIST_OPEN.findall(before)]
        closes = [t.lower() for t in LIST_CLOSE.findall(before)]
        parent = ""
        depth = len(opens) - len(closes)
        if depth > 0 and opens:
            parent = opens[-1]
        raw = m.group(0)
        if parent:                      # keep the list tag in the evidence
            idx = before.rfind("<" + parent)
            raw = before[idx:m.start()] + raw
        out.append((normalize(inner), raw, parent))
    return out


def check(html: str, spec: dict) -> list:
    found = blocks_with_context(html)
    results = []
    for line in spec["lines"]:
        want = normalize(line["text"])
        hit = next((b for b in found if want and want in b[0]), None)
        if hit is None:
            results.append((False, line["id"],
                            "line not found in the document at all"))
            continue
        _, raw, parent = hit
        problems = []
        if line.get("parent") and parent != line["parent"]:
            problems.append(f"expected to sit inside <{line['parent']}>, "
                            f"found {'<' + parent + '>' if parent else 'no list'}")
        any_pats = line.get("html_any") or []
        if any_pats and not any(re.search(p, raw, re.IGNORECASE) for p in any_pats):
            problems.append("none of the expected signatures matched: "
                            + " | ".join(any_pats))
        for pat in line.get("html_none") or []:
            if re.search(pat, raw, re.IGNORECASE):
                problems.append(f"formatting that should have been removed is "
                                f"still there: {pat}")
        results.append((not problems, line["id"], "; ".join(problems)))
    return results


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    export = Path(sys.argv[1])
    spec = json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_SPEC)
                      .read_text(encoding="utf-8"))
    html = export.read_text(encoding="utf-8", errors="replace")
    print(f"$ format_check {export.name} against {spec['title']}")
    results = check(html, spec)
    for ok, line_id, detail in results:
        print(("PASS " if ok else "FAIL ") + line_id + ("" if ok else f": {detail}"))
    failed = sum(1 for ok, _, _ in results if not ok)
    passed = len(results) - failed
    print(f"\n{failed} failed, {passed} passed in 0.00s")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
