# Playbook: organize_plan

Propose (never perform) a reorganization of one folder: moves, renames, and
tag additions, as a JSON plan a reviewer approves. Entries are rules learned
from real runs; follow every one.

## Entries
- [op-001] (seed) Output exactly one file, plan.json: {"moves": [{"from": "rel/path", "to": "rel/path", "why": "..."}], "tags": [{"path": "rel/path", "add": ["tag"]}], "notes": "..."}; paths are relative to the folder being organized.
- [op-002] (seed) Every "from" must be a file you saw in list_dir; every "to" must stay inside the folder and must not already exist; never send two moves to the same target.
- [op-003] (seed) Prefer few, high-value moves; an empty moves list with good notes is a valid answer when the folder is already sensible.
- [op-004] (seed) Moving a note breaks wikilinks that use its path; mention in notes which notes link to anything you move (use search for the note name).
