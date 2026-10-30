"""projects_lib.py - the pure shape of Project folders and the chats they hold."""

from __future__ import annotations

UNSORTED = "Unsorted"

_NO_NAME = "a project needs a name"
_NO_CHAT = "a chat needs an id"
_TWO_PLACES = "a chat is in exactly one place"


def _clean(items: list[str] | None) -> list[str]:
    """Strip each entry, drop empties and later duplicates, keep the first order."""
    if items is None:
        return []
    kept: list[str] = []
    for item in items:
        text = item.strip()
        if text and text not in kept:
            kept.append(text)
    return kept


def _entry(
    name: str,
    description: str,
    tags: list[str],
    links: list[str],
    chats: list[str],
) -> dict[str, object]:
    """Build the five-key project shape shared by make() and groups()."""
    return {
        "name": name,
        "description": description,
        "tags": list(tags),
        "links": list(links),
        "chats": list(chats),
    }


def _copy(project: dict[str, object]) -> dict[str, object]:
    """Copy a project, lists included, so the caller's dict is never mutated."""
    return _entry(
        project.get("name", ""),
        project.get("description", ""),
        project.get("tags") or [],
        project.get("links") or [],
        project.get("chats") or [],
    )


def make(
    name: str,
    description: str = "",
    tags: list[str] | None = None,
    links: list[str] | None = None,
) -> dict[str, object]:
    """A new project with no chats; the name is required and stripped."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError(_NO_NAME)
    text = description if isinstance(description, str) else ""
    return _entry(name.strip(), text.strip(), _clean(tags), _clean(links), [])


def place(project: dict[str, object], chat: str) -> dict[str, object]:
    """A new project holding chat once - place() is idempotent."""
    if not isinstance(chat, str) or not chat.strip():
        raise ValueError(_NO_CHAT)
    result = _copy(project)
    chats = result["chats"]
    if chat not in chats:
        chats.append(chat)
    return result


def remove(project: dict[str, object], chat: str) -> dict[str, object]:
    """A new project without chat; removing an absent chat is not an error."""
    result = _copy(project)
    result["chats"] = [held for held in result["chats"] if held != chat]
    return result


def locate(projects: list[dict[str, object]], chat: str) -> str:
    """The name of the one project holding chat, else UNSORTED."""
    holders = [
        project.get("name", "")
        for project in projects
        if chat in (project.get("chats") or [])
    ]
    if len(holders) > 1:
        raise ValueError(_TWO_PLACES)
    return holders[0] if holders else UNSORTED


def duplicates(projects: list[dict[str, object]]) -> list[str]:
    """Chat ids held by more than one project, each once, first-seen order."""
    order: list[str] = []
    counts: dict[str, int] = {}
    for project in projects:
        for chat in project.get("chats") or []:
            if chat not in counts:
                counts[chat] = 0
                order.append(chat)
            counts[chat] += 1
    return [chat for chat in order if counts[chat] > 1]


def groups(
    projects: list[dict[str, object]],
    chats: list[str],
) -> list[dict[str, object]]:
    """The window's Chats list: projects in order, then the UNSORTED entry."""
    claimed: set[str] = set()
    result: list[dict[str, object]] = []
    for project in projects:
        held = project.get("chats") or []
        mine = [chat for chat in chats if chat in held and chat not in claimed]
        claimed.update(mine)
        result.append(
            _entry(
                project.get("name", ""),
                project.get("description", ""),
                project.get("tags") or [],
                project.get("links") or [],
                mine,
            )
        )
    loose = [chat for chat in chats if chat not in claimed]
    result.append(_entry(UNSORTED, "Not in a project", [], [], loose))
    return result
