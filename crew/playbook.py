"""Task-type playbooks: the crew's retained knowledge.

One markdown file per task type under crew/playbooks/. Entries are itemized
and id-stamped ("- [vi-003] (source) text") and only ever ADDED or edited
one at a time: never regenerated wholesale, because iterative rewriting
erodes detail (ACE's "context collapse", arXiv 2510.04618). Near-duplicates
are refused so the playbook grows in information, not length.

Sources of entries: seeds (hand-written), reviewer directives
(crew_review playbook_add), and member proposals accepted by a reviewer —
the probation -> live path of CrossTalk's Registry/Crystallization Engine.
"""

import difflib
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .config import CREW_DIR, CrewError

PLAYBOOK_DIR = CREW_DIR / "playbooks"
ENTRY = re.compile(r"^- \[(?P<id>[a-z]{2}-\d{3})\] \((?P<src>[^)]*)\) (?P<text>.+)$")
PREFIX = {"vault_index": "vi", "research_digest": "rd", "organize_plan": "op",
          "test_triage": "tt", "ui_sweep": "us"}
NEAR_DUP = 0.88


def _path(task_type: str) -> Path:
    if task_type not in PREFIX:
        raise CrewError(f"no playbook for task type {task_type!r}")
    return PLAYBOOK_DIR / f"{task_type}.md"


def load(task_type: str) -> str:
    return _path(task_type).read_text(encoding="utf-8")


def entries(task_type: str) -> List[Tuple[str, str, str]]:
    out = []
    for line in load(task_type).splitlines():
        m = ENTRY.match(line.strip())
        if m:
            out.append((m.group("id"), m.group("src"), m.group("text")))
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def add(task_type: str, text: str, source: str) -> Optional[str]:
    """Append an entry; returns its id, or None if a near-duplicate exists."""
    text = " ".join(text.split())
    if not text:
        return None
    existing = entries(task_type)
    for _, _, t in existing:
        if difflib.SequenceMatcher(None, _norm(t), _norm(text)).ratio() >= NEAR_DUP:
            return None
    n = max([int(i.split("-")[1]) for i, _, _ in existing] or [0]) + 1
    new_id = f"{PREFIX[task_type]}-{n:03d}"
    source = re.sub(r"[()\n]", "", source)[:60]
    path = _path(task_type)
    body = path.read_text(encoding="utf-8").rstrip() + \
        f"\n- [{new_id}] ({source}) {text}\n"
    path.write_text(body, encoding="utf-8")
    return new_id
