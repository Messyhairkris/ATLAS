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
OPEN_SECTION = re.compile(r"^#+\s*(open questions?|unknowns?|not (yet )?(known|found)|"
                          r"excluded)",
                          re.IGNORECASE)  # NOT "gaps": absence claims live there
# "excluded" (2026-09-25): a scout's list of what it looked at and left out has a
# reason per line, not a source - Gordon's correct scout lost two lines to it.
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
# "(not stated in source)" is the playbook's own wording (rd-009) for a source that
# is silent - and a silence has nothing to cite. Until 2026-09-21 the gate refused
# the very lines the playbook asked for; Gordon lost a digest to it.
INFERRED = re.compile(r"\((inferred|inference|assumed|not verified|unverified|"
                      r"not stated in (the )?sources?)\)", re.IGNORECASE)



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


# "lines 219-315", "L40-60", "line 12": where something is, not a claim about it.
# Both read tools number their lines, so members cite ranges; the citation gate
# already checks the file was opened. (Barry lost a digest to this, 2026-09-21.)
LINE_LOCATOR = re.compile(r"\b(?:lines?|L)\s*\d+(?:\s*[-–]\s*\d+)?(?:\s*(?:,|and)\s*\d+"
                          r"(?:\s*[-–]\s*\d+)?)*", re.IGNORECASE)


def claims(line: str) -> List[str]:
    bare = LINE_LOCATOR.sub(" ", SRC_CITE.sub(" ", WIKILINK.sub(" ", line)))
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
    # Strip EVERY trailing locator: 'Catalog.md L22 L31' names two ranges of one
    # file (ahk-use research, 2026-09-21: Barry lost a digest to the second one).
    c = re.sub(r"(?:(?::\d+(?:-\d+)?)|(?:[\s,;]+L?\d+(?:-\d+)?))+$", "", c)
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


def reported_failures_exist(text: str, run_log: str, file: str = "",
                            toolbox=None) -> dict:
    """No invented test names.

    Under ## Failures (and ## Groups) a name must be in the captured run output:
    the log is the only admissible evidence for what FAILED. Elsewhere - the
    coverage section names tests that exist - a name may also come from a file
    the member read or searched this job. Until 2026-09-25 every name had to be
    in the log, and a quiet `pytest -q` prints only failures, so Qwen's correct
    triage failed for naming five real tests it had read in tests/test_crew.py.
    """
    seen = "\n".join(toolbox.evidence.seen.values()) if toolbox else ""
    invented, section = set(), ""
    for line in text.splitlines():
        if line.startswith("#"):
            section = line.lstrip("#").strip().lower()
            continue
        failure_section = section.startswith(("failures", "groups"))
        for t in TEST_ID.findall(line):
            t = t.strip()
            if not t or t in run_log:
                continue
            if not failure_section and t in seen:
                continue
            invented.add(t)
    return step("no-invented-tests", not invented,
                "named in the report but absent from the run output"
                + ("" if not toolbox else " (and, outside ## Failures, from every file you read)")
                + ": " + ", ".join(sorted(invented)[:8]), file)


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


# -- code tasks ----------------------------------------------------------------------
#
# These are the only gates whose subject is EXECUTED. The order matters and the
# task type enforces it: scan first, run second. A gate that runs member code
# before the scan has passed would defeat the airlock.

# -- clerk gates (scout, log_clerk, completion_audit) ----------------------------
#
# Ported from Crush-lite's worker contracts (.crush/lite/workers). Lite asked
# for verbatim quotes and exact paths in the prompt; these make them checks.

# Pair the backticks first and filter by length after: a length inside the
# pattern lets `make all` (short) be skipped and "` ended with `" - the text
# BETWEEN two spans - be read as a quote.
QUOTE_SPAN = re.compile(r"`([^`\n]+)`")


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _quotes(text: str, inline: bool = True) -> List[tuple]:
    """(quote, line) for every blockquote line, and with inline=True every
    inline code span of 12+ characters with a space in it.

    Inline spans count only where the playbook makes backticks THE quote form
    (log_clerk). A scout quotes in blockquotes and uses backticks for labels:
    `_reply_tokens(cfg, persona)` in a heading named a function Gordon had
    quoted correctly below it, and failed him (2026-09-25)."""
    out = []
    for line in _body_lines(text):
        s = line.strip()
        if s.startswith(">"):
            q = SRC_CITE.sub("", s.lstrip("> ")).strip()
            if len(q) >= 8 and not q.startswith("```"):   # a fence, not text
                out.append((q, s))
            continue
        if not inline:
            continue
        for q in QUOTE_SPAN.findall(s):
            # short spans and `EVIDENCE_COMPLETE`, `a/b.py` are names, not quotes
            if len(q.strip()) >= 12 and " " in q.strip():
                out.append((q, s))
    return out


def required_sections(text: str, names: Iterable[str], file: str = "") -> dict:
    heads = {_squash(l.lstrip("#")).lower() for l in text.splitlines()
             if l.startswith("#")}
    missing = [n for n in names
               if not any(h.startswith(n.lower()) for h in heads)]
    return step("sections", not missing,
                "missing section headings: " + ", ".join(f"## {n}" for n in missing), file)


def quotes_verbatim(text: str, toolbox, file: str = "", inline: bool = True) -> dict:
    """Every quote appears, whitespace aside, in what the member observed:
    in the text of the line's cited sources, or anywhere observed if the
    line cites nothing. A paraphrase in quote marks is the failure mode."""
    everything = _squash("\n".join(toolbox.evidence.seen.values()))
    bad = []
    for q, line in _quotes(text, inline):
        keys = [k for k in (toolbox.evidence_key(c) for c in citations(line)) if k]
        corpus = _squash("\n".join(toolbox.evidence.text_for(k) for k in keys)) \
            if keys else everything
        if _squash(q) not in corpus and _squash(q) not in everything:
            bad.append(q[:60])
    return step("verbatim", not bad,
                "quoted text not found word for word in what you read: "
                + " | ".join(bad[:4]), file)


def findings_quoted(text: str, section: str = "findings", file: str = "") -> dict:
    """Every top-level finding under the section is followed by a > quote
    before the next finding. Without it, quotes_verbatim has nothing to check
    and a scout's report is a list of claims (Gordon, LSP-off run, 2026-09-25:
    right answer, zero quotes)."""
    unquoted, inside, current, quoted = [], False, None, False
    for line in list(_body_lines(text)) + ["# end"]:
        s = line.strip()
        is_top = bool(re.match(r"^([-*+]|\d+[.)])\s+\S", line))
        if s.startswith("#") or is_top:
            if current and not quoted:
                unquoted.append(current[:60])
            current, quoted = (s if inside and is_top else None), False
            if s.startswith("#"):
                inside = _squash(s.lstrip("#")).lower().startswith(section)
            continue
        if s.startswith(">"):
            quoted = True
    return step("quoted", not unquoted, "findings without a > verbatim quote under "
                "them: " + " | ".join(unquoted[:3]), file)


LOCATOR = re.compile(r"\bL(\d+)(?:\s*[-–]\s*L?(\d+))?\b")


def locators_in_range(text: str, toolbox, file: str = "") -> dict:
    """A line number a scout gives must exist in the file it cites."""
    bad = []
    for line in _body_lines(text):
        locs = LOCATOR.findall(line)
        if not locs:
            continue
        for c in citations(line):
            key = toolbox.evidence_key(c)
            if not key or not Path(key).is_file():
                continue
            try:
                n = len(Path(key).read_text(encoding="utf-8", errors="replace")
                        .splitlines())
            except OSError:
                continue
            for a, b in locs:
                if int(b or a) > n or int(a) < 1:
                    bad.append(f"L{a}{'-' + b if b else ''} in {c} ({n} lines)")
    return step("locations", not bad, "line numbers past the end of the file: "
                + "; ".join(bad[:4]), file)


def failures_in_order(text: str, log: str, section: str = "failures",
                      file: str = "") -> dict:
    """The log clerk's failures are listed earliest first: each quote's first
    position in the log must not come before the previous one's."""
    body, inside = [], False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = _squash(line.lstrip("#")).lower().startswith(section)
            continue
        if inside:
            body.append(line)
    flat, last, bad = _squash(log), -1, []
    for q, _ in _quotes("\n".join(body)):
        pos = flat.find(_squash(q))
        if pos < 0:
            continue            # quotes_verbatim reports it
        if pos < last:
            bad.append(q[:50])
        last = max(last, pos)
    return step("order", not bad, "failures not in log order (earliest first): "
                + " | ".join(bad[:3]), file)


STATES = ("YES", "NO", "PARTIAL", "UNKNOWN")
CONCLUSIONS = ("EVIDENCE_COMPLETE", "EVIDENCE_INCOMPLETE", "CANNOT_DETERMINE")


def completion_inventory(text: str, expected: List[dict], toolbox,
                         file: str = "") -> dict:
    """Each expected artifact has one table row with a state; the harness
    knows whether each given path exists, so NO/YES cannot be made up: a path
    that does not exist is NO, one that exists is YES or PARTIAL and must have
    been opened by the member. The conclusion follows from the states."""
    rows = [[c.strip() for c in l.strip().strip("|").split("|")]
            for l in _body_lines(text)
            if l.strip().startswith("|") and not re.match(r"^\|?\s*:?-{3,}", l.strip())]
    problems, states = [], []
    for item in expected:
        label = item["artifact"]
        row = next((r for r in rows if r and _squash(r[0]).lower()
                    == _squash(label).lower()), None)
        if row is None:
            problems.append(f"no row whose first cell is '{label}'")
            continue
        joined = " | ".join(row)
        state = next((s for s in STATES if re.search(rf"\b{s}\b", " | ".join(row[1:2]))), None)
        if state is None:
            problems.append(f"'{label}': second cell must be one of {'/'.join(STATES)}")
            continue
        states.append(state)
        if item.get("exists") is False and state != "NO":
            problems.append(f"'{label}': {item['path']} does not exist, so the state is NO")
        if item.get("exists") is True:
            if state == "NO":
                problems.append(f"'{label}': {item['path']} exists; YES or PARTIAL")
            elif toolbox.evidence_key(item["path"], opened_only=True) is None:
                problems.append(f"'{label}': open {item['path']} before judging it {state}")
        if item.get("path") is None and state in ("YES", "PARTIAL") \
                and not any(toolbox.evidence_key(c, opened_only=True)
                            for c in citations(joined)):
            problems.append(f"'{label}': a {state} needs a citation of a file you opened")
    m = re.search(r"conclusion\W+(\w+)", text, re.IGNORECASE)
    concl = m.group(1).upper() if m else None
    if concl not in CONCLUSIONS:
        problems.append(f"a 'Conclusion: {'|'.join(CONCLUSIONS)}' line is required")
    elif states and len(states) == len(expected):
        if concl == "EVIDENCE_COMPLETE" and any(s != "YES" for s in states):
            problems.append("EVIDENCE_COMPLETE needs every state YES")
        if concl == "EVIDENCE_INCOMPLETE" and all(s == "YES" for s in states):
            problems.append("every state is YES, so the conclusion is EVIDENCE_COMPLETE")
    return step("inventory", not problems, "; ".join(problems[:5]), file)


def lsp_clean(lsp_cfg: dict, lang: str, modules: Dict[str, str], target: str,
              file: str = "") -> dict:
    """No ERROR-severity diagnostics (undefined names, syntax errors) from the
    language's diagnostics server. Warnings never fail: an unused import is
    style, and style is autofix's and the reviewer's business, not a retry's.

    Runs before the hidden tests so a member learns "undefined name on L8"
    instead of reading it out of a test traceback. The server not starting is
    reported as passing with a note - a missing linter must not fail a module.
    """
    import tempfile
    from .lsp import ERROR, LspError, check_source, format_diagnostics
    try:
        with tempfile.TemporaryDirectory(prefix="crew-lsp-") as tmp:
            diags = check_source(lsp_cfg, lang, modules, target, Path(tmp))
    except (LspError, OSError) as e:
        return {**step("lsp", True, file=file), "note": f"lsp skipped: {e}"}
    errors = format_diagnostics(diags, min_severity=ERROR)
    return step("lsp", not errors,
                "language-server errors: " + " | ".join(errors[:6]), file)


def module_is_safe(source: str, file: str = "", allowed_modules=()) -> dict:
    """crew/codetask.py reads the source as an AST and refuses anything that
    reaches outside a pure function. Contracts pass devices, audio and files in
    as callables precisely so this is satisfiable. `allowed_modules` are the
    crew's own accepted modules this task may build on."""
    from . import codetask
    problems = codetask.scan(source, file or "module", extra_imports=allowed_modules)
    return step("safety", not problems,
                "the module may not be executed: " + "; ".join(problems[:6])
                if problems else "the module only uses allowed imports and calls",
                file)


def defines_api(source: str, required, file: str = "") -> dict:
    """The contract names the public API. A module that renames half of it is
    not an implementation of that contract, however good the code is."""
    from . import codetask
    have = set(codetask.public_names(source))
    missing = [name for name in required if name not in have]
    return step("api", not missing,
                f"the contract requires these public names, which are missing: "
                f"{', '.join(missing)}" if missing
                else f"all {len(required)} contract names are defined", file)


def not_stubbed(source: str, required, file: str = "") -> dict:
    """`pass`, `...` and `raise NotImplementedError` import cleanly and help
    nobody."""
    from . import codetask
    empty = codetask.stubbed(source, list(required))
    return step("no stubs", not empty,
                f"these are stubs, not implementations: {', '.join(empty)}"
                if empty else "no stubbed functions", file)


def hidden_tests_pass(modules: dict, tests: dict, timeout_s: int,
                      file: str = "", allowed_modules=()) -> dict:
    """The tests that decide the outcome, which the member never sees. Their
    output is fed back as the reason to try again, so the loop is driven by
    evidence rather than by opinion."""
    from . import codetask
    ok, out, detail = codetask.run_tests(modules, tests, timeout_s,
                                         extra_imports=allowed_modules)
    tail = codetask.summarize(out)
    extra = detail.get("unexpected_files") or []
    if ok and extra:
        return step("hidden tests", False,
                    f"the tests passed but the run left files behind, so the "
                    f"module is writing to disk: {', '.join(extra)}", file)
    return step("hidden tests", ok,
                ("the hidden tests pass" if ok else
                 "the hidden tests fail. This is the evidence; fix the module, "
                 "do not argue with it:\n" + tail), file)


def test_file_is_safe(source: str, file: str = "", allowed_modules=()) -> dict:
    """A test file is executed too. pytest and the module under test are
    allowed; nothing else new is."""
    from . import codetask
    extra = {"pytest", "unittest"} | {str(m) for m in allowed_modules}
    problems = codetask.scan(source, file or "tests", extra_imports=extra)
    return step("safety", not problems,
                "the test file may not be executed: " + "; ".join(problems[:6])
                if problems else "the test file is safe to run", file)


def enough_tests(source: str, minimum: int, file: str = "") -> dict:
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return step("test count", False, f"the test file does not parse: {e.msg}", file)
    n = sum(1 for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_"))
    return step("test count", n >= minimum,
                f"{n} test functions; the task asks for at least {minimum}", file)


def tests_run_green(modules: dict, tests: dict, timeout_s: int,
                    file: str = "", allowed_modules=()) -> dict:
    """The tester's tests must pass against the module that was already
    accepted. A failure here is a real disagreement between two members: either
    the module has a bug the hidden tests missed, or the test misreads the
    contract. Both go to a senior, neither is guessed at."""
    from . import codetask
    ok, out, _ = codetask.run_tests(modules, tests, timeout_s,
                                    extra_imports=allowed_modules)
    return step("tests green", ok,
                ("the tests pass against the accepted module" if ok else
                 "these tests fail against the accepted module. Either your test "
                 "misreads the contract or the module has a bug the hidden tests "
                 "missed. Quote the contract line you are testing:\n"
                 + codetask.summarize(out)), file)


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
