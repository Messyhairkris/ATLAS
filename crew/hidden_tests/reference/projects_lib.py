"""Reference implementation for the projects_lib.py contract (Project folders' pure model)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

UNSORTED = "Unsorted"


def make(name: str, description: str = "", tags: Optional[List[str]] = None,
         links: Optional[List[str]] = None) -> Dict[str, Any]:
    """A new project; an empty name raises, tags and links are cleaned."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a project needs a name")
    return {
        "name": name.strip(),
        "description": (description or "").strip() if isinstance(description, str) or description is None else str(description).strip(),
        "tags": _clean(tags),
        "links": _clean(links),
        "chats": [],
    }


def place(project: Dict[str, Any], chat: str) -> Dict[str, Any]:
    """A new project with `chat` appended when it is not already there (idempotent)."""
    if not isinstance(chat, str) or not chat:
        raise ValueError("a chat needs an id")
    out = _copy(project)
    if chat not in out["chats"]:
        out["chats"] = out["chats"] + [chat]
    return out


def remove(project: Dict[str, Any], chat: str) -> Dict[str, Any]:
    """A new project without `chat`; removing one that is not there changes nothing."""
    out = _copy(project)
    out["chats"] = [c for c in out["chats"] if c != chat]
    return out


def locate(projects: List[Dict[str, Any]], chat: str) -> str:
    """The name of the project holding `chat`, else UNSORTED; two projects raises."""
    holders = [p["name"] for p in projects if chat in (p.get("chats") or [])]
    if len(holders) > 1:
        raise ValueError("a chat is in exactly one place")
    return holders[0] if holders else UNSORTED


def duplicates(projects: List[Dict[str, Any]]) -> List[str]:
    """The chat ids held by more than one project, each once, in first-seen order."""
    seen: List[str] = []
    twice: List[str] = []
    for project in projects:
        for chat in (project.get("chats") or []):
            if chat in seen:
                if chat not in twice:
                    twice.append(chat)
            else:
                seen.append(chat)
    return twice


def groups(projects: List[Dict[str, Any]], chats: List[str]) -> List[Dict[str, Any]]:
    """The Chats list: one entry per project in order, then UNSORTED with the unclaimed chats."""
    project_names = [p["name"] for p in projects]
    taken: List[str] = []
    out: List[Dict[str, Any]] = []
    for project in projects:
        mine = [c for c in chats if c in (project.get("chats") or []) and c not in taken]
        taken.extend(mine)
        out.append({"name": project["name"], "description": project.get("description") or "",
                    "tags": list(project.get("tags") or []), "links": list(project.get("links") or []),
                    "chats": mine})
    leftovers = [c for c in chats if c not in taken]
    out.append({"name": UNSORTED, "description": "Not in a project", "tags": [], "links": [],
                "chats": leftovers})
    return out


def _clean(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for value in (values or []):
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def _copy(project: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": project.get("name"), "description": project.get("description") or "",
            "tags": list(project.get("tags") or []), "links": list(project.get("links") or []),
            "chats": list(project.get("chats") or [])}
