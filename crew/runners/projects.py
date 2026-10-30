"""Project folders: the store, and the Chats list the window draws.

    python crew/runners/projects.py groups                 the Chats list as JSON
    python crew/runners/projects.py groups --chats a,b,c   ...in the caller's chat order
    python crew/runners/projects.py create "The Crew" --description "the control room" --tags ui,tools
    python crew/runners/projects.py move ses_abc "The Crew"
    python crew/runners/projects.py move ses_abc Unsorted

The rules live in crew/projects_lib.py, which is pure and has no `open()` (the crew's airlock keeps
it that way). This file is the impure half: it reads and writes crew/projects.json, and prints one
JSON object. Writes are atomic - a temp file beside the target, then a replace - so a crash cannot
leave a half-written list of projects.

Read-only unless `create` or `move` is asked for.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # the harness root
if str(REPO / "crew") not in sys.path:
    sys.path.insert(0, str(REPO / "crew"))

import projects_lib as pl                       # noqa: E402

STORE = REPO / "crew" / "projects.json"

ABOUT = ("Project folders (Kris, 2026-10-30). One entry per project: name, description shown on "
         "mouse-over, tags, key links, and the chats in it. A chat is in exactly one project - or "
         "in Unsorted, which is not listed here because it is everything else. Kris edits this; "
         "crew/runners/projects.py reads it and writes it, and crew/projects_lib.py holds the rules.")


def load(path: Path = STORE) -> dict:
    """The store; a missing or broken file reads as no projects rather than failing."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"projects": []}
    if not isinstance(data, dict):
        return {"projects": []}
    projects = data.get("projects")
    return {"projects": projects if isinstance(projects, list) else []}


def save(store: dict, path: Path = STORE) -> None:
    """Write the store atomically: a temp file in the same folder, then a replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        about = json.loads(path.read_text(encoding="utf-8")).get("_about") or ABOUT
    except (OSError, ValueError):
        about = ABOUT
    payload = {"_about": about, "projects": store.get("projects", [])}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def find(store: dict, name: str):
    """The project dict with that name, or None. Case-insensitive, trimmed."""
    wanted = (name or "").strip().lower()
    for project in store.get("projects", []):
        if str(project.get("name", "")).strip().lower() == wanted:
            return project
    return None


def create(store: dict, name: str, description: str = "", tags=None, links=None) -> dict:
    """A new project; an existing name is refused."""
    if find(store, name):
        raise ValueError("a project named %r is already there" % name)
    project = pl.make(name, description, tags, links)
    store["projects"] = list(store.get("projects", [])) + [project]
    return store


def move(store: dict, chat: str, project_name: str) -> dict:
    """Put a chat in a project, or in Unsorted when the name is Unsorted."""
    projects = list(store.get("projects", []))
    stripped = [pl.remove(p, chat) for p in projects]          # out of wherever it was
    if (project_name or "").strip().lower() == pl.UNSORTED.lower():
        store["projects"] = stripped
        return store
    target = find({"projects": stripped}, project_name)
    if target is None:
        raise ValueError("no project named %r" % project_name)
    store["projects"] = [pl.place(p, chat) if p is target or p["name"] == target["name"] else p
                         for p in stripped]
    return store


def chats_for(store: dict, chats=None) -> list:
    """The caller's chat order, or the projects' own chats when the caller gave none."""
    if chats:
        return list(chats)
    seen = []
    for project in store.get("projects", []):
        for chat in project.get("chats", []):
            if chat not in seen:
                seen.append(chat)
    return seen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["groups", "create", "move"])
    ap.add_argument("name", nargs="?", default="", help="create: the project name; move: the chat")
    ap.add_argument("to", nargs="?", default="", help="move: the project, or Unsorted")
    ap.add_argument("--to", dest="to_opt", default="", help="move: the project, or Unsorted")
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--links", default="")
    ap.add_argument("--chats", default="", help="a comma-separated chat list, the caller's order")
    ap.add_argument("--store", default=str(STORE))
    a = ap.parse_args(argv)
    path = Path(a.store)

    def items(text):
        return [t.strip() for t in text.split(",") if t.strip()]

    if a.action == "groups":
        store = load(path)
        chats = items(a.chats) if a.chats else None
        print(json.dumps({"groups": pl.groups(store.get("projects", []), chats_for(store, chats))}))
        return 0

    store = load(path)
    if a.action == "create":
        store = create(store, a.name, a.description, items(a.tags), items(a.links))
    else:
        store = move(store, a.name, a.to_opt or a.to)
    save(store, path)
    print(json.dumps({"projects": [p["name"] for p in store.get("projects", [])]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
