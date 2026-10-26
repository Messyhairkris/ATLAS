"""Reference for history_docs.py: search records and safe FTS5 queries (PA-written)."""

import re

MAX_BODY_CHARS = 20000

_TERM = re.compile(r'"([^"]*)"|(\w+)(\*?)')


def _slashes(path: str) -> str:
    return path.replace("\\", "/")


def job_record(job: dict, outputs: dict[str, str], path: str) -> dict:
    """A crew job as one search record."""
    result = job.get("result") or {}
    title = job.get("title")
    when = next((job.get(k) for k in ("finished_at", "updated_at", "created_at")
                 if job.get(k)), "")
    tags = []
    for value in (job.get("task_type"), job.get("status"), result.get("stop_reason"),
                  "question" if job.get("question") else None):
        if isinstance(value, str) and value and value not in tags:
            tags.append(value)
    parts = [job.get("description") or ""]
    parts += [f"## {name}\n{outputs[name]}" for name in sorted(outputs)]
    findings = result.get("findings")
    if isinstance(findings, list) and findings:
        parts.append("## notes\n" + "\n".join(f"- {f}" for f in findings))
    return {"key": f"job:{job['task_id']}", "kind": "job",
            "title": title if isinstance(title, str) and title else job["task_id"],
            "body": "\n\n".join(p for p in parts if p)[:MAX_BODY_CHARS],
            "path": _slashes(path), "when": when, "who": job.get("assigned_to") or "",
            "tags": " ".join(tags)}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def doc_record(path: str, text: str, kind: str = "doc", when: str = "") -> dict:
    """A markdown document as one search record."""
    p = _slashes(path)
    lines = text.split("\n")
    front, body = {}, text
    if lines and lines[0].rstrip("\r") == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r") == "---"), None)
        if end is not None:
            for line in lines[1:end]:
                key, sep, value = line.partition(":")
                if sep:
                    front.setdefault(key.strip(), value.rstrip("\r"))
            body = "\n".join(lines[end + 1:])
    title = _unquote(front.get("title", ""))
    if not title:
        heading = next((ln for ln in body.split("\n") if ln.startswith("# ")), None)
        title = heading[2:].strip() if heading is not None else p.rsplit("/", 1)[-1]
    tags = ""
    if "tags" in front:
        raw = front["tags"].strip().strip("[]")
        tags = " ".join(t for t in (x.strip().strip("\"' ") for x in raw.split(",")) if t)
    return {"key": f"{kind}:{p}", "kind": kind, "title": title,
            "body": body.strip()[:MAX_BODY_CHARS], "path": p, "when": when, "who": "",
            "tags": tags}


def fts_query(text: str, max_terms: int = 12) -> str:
    """What a person typed, as an FTS5 query nothing in it can break."""
    terms = []
    for match in _TERM.finditer(text):
        phrase, word, star = match.groups()
        if phrase is not None:
            words = re.findall(r"\w+", phrase.lower())
            if not words:
                continue
            term = '"' + " ".join(words) + '"'
        else:
            term = f'"{word.lower()}"' + ("*" if star else "")
        if term not in terms:
            terms.append(term)
    return " ".join(terms[:max_terms])
