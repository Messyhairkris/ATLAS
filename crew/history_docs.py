"""history_docs.py - utilities for indexing crew history documents.

Provides functions to turn job dictionaries and generic documents into
records suitable for an SQLite FTS5 index, and to safely build an FTS5 query
from free-form user input.

Only the standard library ``re`` module is used, as required by the contract.
Written by Hoss in campaign round3-history-map-inbox (2026-10-26); the frontmatter
check fixed in review to accept only a first-line fence.
"""

import re

MAX_BODY_CHARS = 20000


def _first_non_empty(*values: str | None) -> str:
    """Return the first value that is a non-empty string, else ``""``."""
    for v in values:
        if isinstance(v, str) and v:
            return v
    return ""


def _unique_join(items: list[str]) -> str:
    """Join items with a single space, preserving order and dropping duplicates."""
    seen: set[str] = set()
    uniq: list[str] = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            uniq.append(i)
    return " ".join(uniq)


def job_record(job: dict, outputs: dict[str, str], path: str) -> dict:
    """Create an index record for a crew job.

    The returned dict contains exactly the keys required by the contract,
    all values being strings.
    """
    # key
    key = f"job:{job['task_id']}"
    # kind
    kind = "job"
    # title
    title = job.get("title") or job["task_id"]
    if not isinstance(title, str) or not title:
        title = job["task_id"]
    # who
    who = job.get("assigned_to") or ""
    # when
    when = _first_non_empty(
        job.get("finished_at"),
        job.get("updated_at"),
        job.get("created_at"),
    )
    # tags
    tags_parts: list[str] = []
    if job.get("task_type"):
        tags_parts.append(job["task_type"])
    if job.get("status"):
        tags_parts.append(job["status"])
    result = job.get("result")
    if isinstance(result, dict):
        stop = result.get("stop_reason")
        if stop:
            tags_parts.append(stop)
    if job.get("question"):
        tags_parts.append("question")
    tags = _unique_join(tags_parts)

    # body construction
    body_parts: list[str] = []
    description = job.get("description")
    if isinstance(description, str) and description:
        body_parts.append(description)

    for name in sorted(outputs):
        body_parts.append(f"## {name}\n{outputs[name]}")

    findings = []
    if isinstance(result, dict):
        findings = result.get("findings") or []
    if isinstance(findings, list) and findings:
        notes = "\n".join(f"- {f}" for f in findings)
        body_parts.append(f"## notes\n{notes}")

    body = "\n\n".join(body_parts)
    body = body[:MAX_BODY_CHARS]

    # path normalisation
    norm_path = path.replace("\\", "/")

    return {
        "key": key,
        "kind": kind,
        "title": title,
        "body": body,
        "path": norm_path,
        "when": when,
        "who": who,
        "tags": tags,
    }


def doc_record(path: str, text: str, kind: str = "doc", when: str = "") -> dict:
    """Create an index record for a generic document.

    Handles optional front-matter for title and tags.
    """
    p = path.replace("\\", "/")
    key = f"{kind}:{p}"
    # front-matter detection
    lines = text.splitlines()
    fm_start = fm_end = None
    for i, line in enumerate(lines):
        if line.rstrip("\r") == "---":
            if fm_start is None:
                fm_start = i
            else:
                fm_end = i
                break
    frontmatter: list[str] = []
    body_start = 0
    # only a FIRST line --- opens frontmatter; later ones are markdown rules (review fix)
    if fm_start == 0 and fm_end is not None:
        frontmatter = lines[fm_start + 1 : fm_end]
        body_start = fm_end + 1

    # title extraction
    title = ""
    # 1. front-matter title
    for fm_line in frontmatter:
        if fm_line.lstrip().startswith("title:"):
            _, val = fm_line.split(":", 1)
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            if val:
                title = val
                break
    # 2. first body heading
    if not title:
        for line in lines[body_start:]:
            if line.startswith("# "):
                title = line[2:].strip()
                break
    # 3. fallback to filename segment
    if not title:
        title = p.rsplit("/", 1)[-1]

    # tags extraction
    tags = ""
    for fm_line in frontmatter:
        if fm_line.lstrip().startswith("tags:"):
            _, val = fm_line.split(":", 1)
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                val = val[1:-1]
            raw_tags = [t.strip() for t in val.split(",")]
            cleaned = []
            for t in raw_tags:
                if not t:
                    continue
                if (t.startswith('"') and t.endswith('"')) or (
                    t.startswith("'") and t.endswith("'")
                ):
                    t = t[1:-1]
                cleaned.append(t)
            tags = " ".join(cleaned)
            break

    # body
    body = "\n".join(lines[body_start:]).strip()
    body = body[:MAX_BODY_CHARS]

    return {
        "key": key,
        "kind": kind,
        "title": title,
        "body": body,
        "path": p,
        "when": when,
        "who": "",
        "tags": tags,
    }


def fts_query(text: str, max_terms: int = 12) -> str:
    """Convert free-form user input into a safe FTS5 query.

    The algorithm follows the contract's exact steps.
    """
    pattern = re.compile(r'"([^"]*)"|(\w+)(\*?)')
    terms: list[str] = []
    seen: set[str] = set()

    for match in pattern.finditer(text):
        phrase, word, star = match.groups()
        term = None
        if phrase is not None:
            # extract words from the phrase
            words = re.findall(r"\w+", phrase, flags=re.UNICODE)
            if words:
                term = f'"{" ".join(w.lower() for w in words)}"'
        elif word is not None:
            base = word.lower()
            term = f'"{base}"'
            if star:
                term = f'{term}*'

        if term and term not in seen:
            seen.add(term)
            terms.append(term)
            if len(terms) >= max_terms:
                break

    return " ".join(terms)
