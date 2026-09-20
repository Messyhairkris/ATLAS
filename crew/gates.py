"""Deterministic, zero-token gates for crew output.

Each gate returns a step {"rung", "file", "ok", "detail"}, the same shape the
experiment runners use, so experiments/attempts.py can grade submissions.

Evidence-bound gates (citation, grounding) check the output against what the
member actually observed this job (tools.Evidence), so a confident summary of
a note it never opened fails even if the note exists.
"""

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

WIKILINK = re.compile(r"\[\[(?!\s*src:)([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
# [src: x] is the citation form; [[src: x]] (a small-model mix of both forms,
# seen 2026-09-19) is accepted as the same thing rather than failed.
SRC_CITE = re.compile(r"\[\[?src:\s*([^\]]+?)\s*\]\]?")
OPEN_SECTION = re.compile(r"^#+\s*(open questions?|unknowns?|not (yet )?(known|found))",
                          re.IGNORECASE)  # NOT "gaps": absence claims live there
# The source list itself: its lines ARE citations, in whatever form.
SOURCES_SECTION = re.compile(r"^#+\s*(sources?|references?|bibliography)\b", re.IGNORECASE)
# A bullet that only labels the nested bullets under it ("- **Options:**").
LABEL_ITEM = re.compile(r"^([-*+]|\d+[.)])\s+[*_`]*[^.!?]{1,60}?[*_`]*\s*[:–—-]\s*[*_]*\s*$")
CLAIM_NUMBER = re.compile(r"\$?\d[\d.,]*(?:/\d+)?(?:%|k|K|x|×)?")
VERDICT_WORDS = ("PASS", "FAIL", "MET", "CONFIRMED", "PARTIAL", "DONE",
                 "BLOCKED", "REJECTED")


ABSENCE = re.compile(
    r"\b(no|not|never|none|nothing|nowhere|without)\b[^.;]{0,40}\b"
    r"(test|tests|tested|covered|coverage|check|checked|verif\w+|assert\w*|"
    r"handle[sd]?|implement\w*|report\w*|log\w*|exist\w*|present|defined|"
    r"mention\w*|document\w*)\b"
    r"|\b(missing|absent|lacks?|lacking|untested|uncovered|unhandled|"
    r"undocumented|unimplemented|no such)\b", re.IGNORECASE)
INFERRED = re.compile(r"\((inferred|inference|assumed|not verified|unverified)\)",
                      re.IGNORECASE)



def step(rung: str, ok: bool, detail: str = "ok", file: str = "") -> dict:
    return {"rung": rung, "file": file, "ok": bool(ok),
            "detail": detail if not ok else "ok"}


def _body_lines(text: str) -> Iterable[str]:
    """Lines outside YAML frontmatter and fenced code."""
    in_front = text.startswith("---")
    fence = False
    for i, line in enumerate(text.splitlines()):
        if in_front:
            if i > 0 and line.strip() == "---":
                in_front = False
            continue
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if not fence:
            yield line


def claims(line: str) -> List[str]:
    bare = SRC_CITE.sub(" ", WIKILINK.sub(" ", line))
    nums = [n.rstrip(".,") for n in CLAIM_NUMBER.findall(bare)]
    words = [w for w in VERDICT_WORDS if re.search(rf"\b{w}\b", bare)]
    return [n for n in nums if len(n) >= 2] + words


def _strip_locator(cite: str) -> str:
    """'ACCESSIBILITY.md#71-86' / 'engine.py:120' / 'x.py L40-60' -> the file.
    Members add line locators to citations; the file is what gets checked.
    URL fragments are kept (http...#x is a different page state)."""
    c = cite.strip()
    if c.startswith(("http://", "https://")):
        return c.split("#", 1)[0]
    c = c.split("#", 1)[0]
    c = re.sub(r"(:\d+(-\d+)?|\s+L?\d+(-\d+)?)$", "", c)
    return c.strip()


def citations(line: str) -> List[str]:
    return ([l.strip() for l in WIKILINK.findall(line)]
            + [_strip_locator(s) for s in SRC_CITE.findall(line)])


# -- structural gates -------------------------------------------------------------

def output_paths(files: Dict[str, str], allowed: List[str], out_root: Path,
                 writable) -> dict:
    bad = []
    for rel in files:
        if allowed and rel not in allowed:
            bad.append(f"{rel} (not a declared output; allowed: {', '.join(allowed)})")
            continue
        dest = (out_root / rel).resolve()
        if ".." in Path(rel).parts or not writable(dest):
            bad.append(f"{rel} (outside write roots)")
    if not files:
        return step("output", False, "no output files in the submission")
    return step("output", not bad, "bad output paths: " + "; ".join(bad))


def wikilinks_resolve(text: str, link_root: Path, vault_root: Optional[Path],
                      file: str = "") -> dict:
    dangling = []
    names = None
    for target in WIKILINK.findall(text):
        t = target.strip().removesuffix(".md")
        if (link_root / (t + ".md")).exists() or (link_root / t).exists():
            continue
        if vault_root:
            if names is None:
                names = {p.stem.lower() for p in vault_root.rglob("*.md")}
            if Path(t).name.lower() in names:
                continue
        dangling.append(t)
    return step("links", not dangling,
                "wikilinks that resolve to no note: " + ", ".join(sorted(set(dangling))),
                file)


def coverage(text: str, required: Iterable[str], file: str = "") -> dict:
    linked = {l.strip().removesuffix(".md") for l in WIKILINK.findall(text)}
    missing = sorted(r for r in required if r not in linked)
    return step("coverage", not missing, "not linked: " + ", ".join(missing), file)


def must_mention(text: str, terms: Iterable[str], file: str = "") -> dict:
    low = text.lower()
    missing = [t for t in terms if t.lower() not in low]
    return step("must-mention", not missing, "missing: " + ", ".join(missing), file)


def frontmatter(text: str, fields: Iterable[str], file: str = "") -> dict:
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    if not m:
        return step("frontmatter", False, "no YAML frontmatter (--- ... ---) at top", file)
    keys = {ln.split(":", 1)[0].strip() for ln in m.group(1).splitlines()
            if ":" in ln and not ln.startswith((" ", "-"))}
    missing = [f for f in fields if f not in keys]
    return step("frontmatter", not missing,
                "frontmatter missing: " + ", ".join(missing), file)


# -- evidence-bound gates ---------------------------------------------------------

def cited_lines(text: str, toolbox, file: str = "", require: bool = True) -> dict:
    """Every content line (bullet, numbered item, table row) carries a
    citation, and every citation names something observed this job."""
    uncited, unseen = [], set()
    lines = list(_body_lines(text))
    in_open = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#"):
            # questions have no source; the source list is the sources
            in_open = bool(OPEN_SECTION.match(s) or SOURCES_SECTION.match(s))
            continue
        # A list marker needs a following space: "*Note:*" is emphasis, not a bullet.
        is_item = bool(re.match(r"^([-*+]|\d+[.)])\s+\S", s) or s.startswith("|")) \
            and not re.match(r"^\|?\s*:?-{3,}", s)
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        is_table_header = s.startswith("|") and bool(re.match(r"^\|?\s*:?-{3,}", nxt))
        if not is_item or is_table_header or in_open or LABEL_ITEM.match(s):
            continue
        cites = citations(s)
        if not cites:
            if require and not INFERRED.search(s):
                uncited.append(s[:70])
            continue
        for c in cites:
            if toolbox.evidence_key(c) is None:
                unseen.add(c)
    problems = []
    if uncited:
        problems.append(f"{len(uncited)} item line(s) without a citation, e.g. "
                        + " | ".join(uncited[:3]))
    if unseen:
        problems.append("cited but never opened this job: "
                        + ", ".join(sorted(unseen)[:8]))
    return step("citations", not problems, "; ".join(problems), file)


def grounded(text: str, toolbox, file: str = "") -> dict:
    """Numbers/ratios/$/verdict words must appear in the observed text of the
    line's cited sources (or of anything observed, for an uncited line)."""
    everything = "\n".join(toolbox.evidence.seen.values())
    bad = []
    for line in _body_lines(text):
        cl = claims(line)
        if not cl:
            continue
        keys = [k for k in (toolbox.evidence_key(c) for c in citations(line)) if k]
        corpus = "\n".join(toolbox.evidence.text_for(k) for k in keys) \
            if keys else everything
        for c in cl:
            if c not in corpus:
                bad.append(f"'{c}' in: {line.strip()[:60]}")
    return step("grounding", not bad,
                "claims not found in what you read: " + "; ".join(bad[:6]), file)


def must_read(toolbox, paths: Iterable[str], file: str = "") -> dict:
    """Reviewer-required reading: each path must be in this job's evidence
    (opened with a tool or preloaded in full). Turns "read X first" from an
    instruction a small model may skip into a check it cannot."""
    missing = [p for p in paths
               if toolbox.evidence_key(p, opened_only=True) is None]
    return step("must-read", not missing,
                "you were required to read (read_file) but did not: "
                + ", ".join(missing), file)


def ascii_only(text: str, file: str = "") -> dict:
    bad = sorted({c for c in text if ord(c) > 127})
    return step("ascii", not bad,
                "non-ASCII characters (use plain - and quotes): "
                + " ".join(f"U+{ord(c):04X}" for c in bad[:8]), file)


def acceptance(text: str, spec: dict, toolbox, file: str = "") -> List[dict]:
    """Optional gates a submitter or reviewer attached to this task."""
    acc = spec.get("acceptance") or {}
    steps = []
    if acc.get("must_mention"):
        steps.append(must_mention(text, acc["must_mention"], file))
    if acc.get("must_read"):
        steps.append(must_read(toolbox, acc["must_read"], file))
    if acc.get("ascii_only"):
        steps.append(ascii_only(text, file))
    return steps


# -- absence claims ------------------------------------------------------------------
#
# "Nothing tests X", "X never reports Y", "the log is missing Z" are the most
# useful findings a reviewer gets and the easiest to fabricate: absence cannot
# be evidenced by a log that simply does not mention the thing. So each such
# line must either cite a source the member OPENED itself (it looked and did
# not find it) or be marked "(inferred)" so a reader can weigh it.
# CrossTalk wants exactly this distinction: what is missing, what failed to
# report, and what should have reported but did not.

def absence_claims(text: str, toolbox, file: str = "") -> dict:
    """Every claim that something is missing must rest on a source the member
    opened, or be labeled (inferred)."""
    unbacked = []
    in_open = False
    for line in _body_lines(text):
        s = line.strip()
        if s.startswith("#"):
            in_open = bool(OPEN_SECTION.match(s) or SOURCES_SECTION.match(s))
            continue
        if in_open or not s or not ABSENCE.search(s):
            continue
        if INFERRED.search(s):
            continue
        opened = [c for c in citations(s)
                  if toolbox.evidence_key(c, opened_only=True)]
        if not opened:
            unbacked.append(s[:80])
    return step("absence-claims", not unbacked,
                "claims that something is missing must cite a file you opened "
                "yourself, or say (inferred): " + " | ".join(unbacked[:4]), file)


# -- test triage ---------------------------------------------------------------------

TEST_ID = re.compile(r"[\w./\\-]+\.py::[\w:\[\]. -]+|\btest_[A-Za-z0-9_]+")


def named_things_exist(text: str, run_log: str, kind: str = "test",
                       file: str = "") -> dict:
    """Every quoted NAME must appear in the captured run output. Invented names
    are the failure mode a plausible report hides.

    Deliberately narrow, because a report also quotes things that are not
    names: the run's own summary line, JSON fragments from the log, numbers.
    Those are skipped, and comparison ignores whitespace differences ("97.73 s"
    vs "97.73s" is not an invention)."""
    squash = lambda s: re.sub(r"\s+", "", s)           # noqa: E731
    log_squashed = squash(run_log)
    quoted = (set(re.findall(r'"([^"\n]{2,60})"', text))
              | set(re.findall(r"`([^`\n]{2,60})`", text))
              | set(re.findall(r"\*\*([^*\n]{2,60})\*\*", text)))
    skip = re.compile(r"^\d+\s+(failed|passed|error)|^\w+:\s|\bfalse\b|\btrue\b"
                      r"|^\d[\d.,\s]*\w?$|^(src|http)", re.IGNORECASE)
    invented = sorted({q.strip() for q in quoted
                       if q.strip() and not skip.search(q.strip())
                       and squash(q) not in log_squashed})
    return step(f"no-invented-{kind}s", not invented,
                "named in the report but absent from the run output: "
                + ", ".join(invented[:8]), file)


def reported_failures_exist(text: str, run_log: str, file: str = "") -> dict:
    """Every test the report names must appear in the captured run output.
    The log is the only admissible evidence for what failed, so a plausible
    invented test name fails here."""
    invented = sorted({t.strip() for t in TEST_ID.findall(text)
                       if t.strip() and t.strip() not in run_log})
    return step("no-invented-tests", not invented,
                "named in the report but absent from the run output: "
                + ", ".join(invented[:8]), file)


def reports_interference(text: str, run_log: str, file: str = "") -> dict:
    """When the run log says a human (or another program) acted during the
    test, the report must name it and mark the affected results unreliable."""
    if "human_interference" not in run_log:
        return step("interference", True, "no interference in the run", file)
    low = text.lower()
    said = any(w in low for w in ("interfer", "unreliable", "human input",
                                 "hands off", "keyboard or mouse"))
    return step("interference", said,
                "the run log records human interference during the test; the "
                "report must say which presses are unreliable and why", file)


# Run-log events that a sweep report must not silently drop, and the words
# that count as reporting them. Kris watched a sweep move past "open the logs"
# while nothing opened, and the report called the run clean.
STALL_EVENTS = {
    "nothing_opened": ("never opened", "nothing opened", "did not open",
                       "didn't open", "no window", "nothing happened"),
    "stalled": ("stall", "still busy", "still working", "unfinished",
                "did not finish", "not finished"),
    "menu_did_not_open": ("did not open", "didn't open", "never opened",
                          "stayed closed"),
    "dialog_would_not_close": ("would not close", "wouldn't close",
                               "stayed open", "did not close"),
}


def reports_stalls(text: str, run_log: str, file: str = "") -> dict:
    """The sweep now waits for the app to be ready and records what never
    happened. Those records are the point of the run, so the report must carry
    them: a control whose window never appeared, an app still busy when the
    ceiling ran out, a menu that stayed shut, a dialog that would not close."""
    low = text.lower()
    missing = [event for event, words in STALL_EVENTS.items()
               if event in run_log and not any(w in low for w in words)]
    if not missing:
        return step("stalls", True, "no stalled or unopened controls in the run",
                    file)
    return step("stalls", False,
                "the run log records " + ", ".join(sorted(missing)) + "; the "
                "report must name the control and say plainly that it never "
                "opened or never finished", file)


def quotes_the_totals(text: str, run_log: str, file: str = "") -> dict:
    """The pytest summary line (e.g. '3 failed, 29 passed in 1.2s') must be
    reproduced verbatim, so the report cannot soften the result."""
    m = re.findall(r"^=*\s*\d+ (?:failed|passed|error)[^\n]*$", run_log, re.MULTILINE)
    if not m:
        return step("totals", True, "no summary line in the run output", file)
    tail = m[-1].strip().strip("= ")
    core = re.sub(r"\s+in\s+[\d.]+s.*$", "", tail).strip()
    return step("totals", core and core in text,
                f"the run's summary line must appear verbatim: {core!r}", file)


# -- organize plan -------------------------------------------------------------------

def organize_plan(text: str, root: Path, readable, file: str = "") -> dict:
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as e:
        return step("plan-schema", False, f"plan.json is not valid JSON: {e}", file)
    if not isinstance(plan, dict) or not isinstance(plan.get("moves", []), list):
        return step("plan-schema", False,
                    'plan must be {"moves": [{"from","to","why"}], '
                    '"tags": [...], "notes": "..."}', file)
    problems, targets = [], set()
    for i, mv in enumerate(plan.get("moves", [])):
        if not isinstance(mv, dict) or not {"from", "to", "why"} <= set(mv):
            problems.append(f"move {i}: needs from/to/why")
            continue
        src, dst = (root / mv["from"]).resolve(), (root / mv["to"]).resolve()
        if not src.exists():
            problems.append(f"move {i}: source {mv['from']} does not exist")
        if not readable(dst) or not (dst == root or root in dst.parents):
            problems.append(f"move {i}: target {mv['to']} leaves {root.name}")
        if dst.exists():
            problems.append(f"move {i}: target {mv['to']} already exists")
        if dst in targets:
            problems.append(f"move {i}: two moves target {mv['to']}")
        targets.add(dst)
    for i, tg in enumerate(plan.get("tags", []) or []):
        if not isinstance(tg, dict) or not (root / str(tg.get("path", ""))).exists():
            problems.append(f"tag {i}: path missing or does not exist")
    return step("plan-schema", not problems, "; ".join(problems[:8]), file)
