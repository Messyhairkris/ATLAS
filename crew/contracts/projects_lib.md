# Contract: projects_lib.py - the Project folders' pure model

One self-contained Python module, `projects_lib.py`. It holds the **shape** of Project folders
(Kris, 2026-10-30): a project has a name, a description for mouse-over, tags, key links, and the
chats that belong to it. A chat is in **exactly one place** - a project, or **Unsorted**.

It is the pure half. A runner reads and writes the settings file; this module never touches a file,
a clock or the screen.

**Allowed imports: `typing`, `__future__`.** Nothing else - no `json`, no `re`, and **no `open()`**
(the crew's airlock bans it, crew/codetask.py; a module that reads the disk is not a pure module).

## Public API

```python
UNSORTED = "Unsorted"

def make(name, description="", tags=None, links=None) -> dict
def place(project, chat) -> dict
def remove(project, chat) -> dict
def locate(projects, chat) -> str
def duplicates(projects) -> list
def groups(projects, chats) -> list
```

## The project shape

```python
{"name": "The Crew", "description": "the control room and its harness",
 "tags": ["ui", "harness"], "links": ["https://github.com/Messyhairkris/TheCrew"],
 "chats": ["ses_a", "ses_b"]}
```

`name` and `description` are `str`; `tags`, `links` and `chats` are lists of `str`.

## The rules

**`make(name, description="", tags=None, links=None)`** - a new project with `chats` empty.
`name` is stripped; an empty name, or one that is not a `str`, raises
`ValueError("a project needs a name")`. `description` is stripped (`""` when missing). `tags` and
`links`: `None` becomes `[]`; each entry is stripped; entries that are empty after stripping are
dropped; duplicates are dropped keeping the **first**; the given order is kept.

**`place(project, chat)`** - returns a **new** project dict; the one passed in is never mutated.
`chat` is appended to `chats` when it is not already there, so `place` is idempotent. An empty
`chat`, or one that is not a `str`, raises `ValueError("a chat needs an id")`.

**`remove(project, chat)`** - a new project dict without `chat`. Removing a chat that is not there
is **not** an error: it changes nothing and still returns a new dict.

**`locate(projects, chat)`** - the `name` of the project whose `chats` hold `chat`; `UNSORTED` when
no project does. A chat in **more than one** project raises
`ValueError("a chat is in exactly one place")`.

**`duplicates(projects)`** - the chat ids held by more than one project, each once, in the order
they are first seen.

**`groups(projects, chats)`** - the Chats list the window shows. One entry per project, **in the
order given**, each `{"name", "description", "tags", "links", "chats"}`; but a project's `chats`
list here holds the chats **in the order they appear in the caller's `chats` list**, not the order
they were placed - the window's list decides what the user sees first. Then a final entry:
`{"name": UNSORTED, "description": "Not in a project", "tags": [], "links": [],
"chats": [<the ids in chats that are in no project, in the caller's order>]}`.

A chat claimed by two projects appears **once**, in the first project that claims it (it is invalid
input; `duplicates` is how a caller finds out). A chat id in `chats` that no project claims is in
`UNSORTED`, whatever it looks like.

## Worked examples

```python
P = make("  The Crew  ", "the control room", ["ui", "ui", " harness ", ""], None)
# {"name": "The Crew", "description": "the control room",
#  "tags": ["ui", "harness"], "links": [], "chats": []}

make("")                                  # ValueError
make("x")["chats"]                        # []

place(P, "ses_a")                         # P is unchanged; the result has chats ["ses_a"]
place(place(P, "ses_a"), "ses_a")         # still ["ses_a"] - idempotent
place(P, "")                              # ValueError

remove(place(P, "ses_a"), "ses_b")        # chats unchanged: ["ses_a"]
remove(P, "ses_a")                        # chats [] and no error

locate([place(P, "ses_a")], "ses_a")      # "The Crew"
locate([], "ses_a")                       # "Unsorted"
locate([place(P, "ses_a"), place(make("B"), "ses_a")], "ses_a")   # ValueError

duplicates([place(P, "ses_a"), place(make("B"), "ses_a")])        # ["ses_a"]

projects = [place(make("The Crew"), "ses_b"), place(make("Other"), "ses_c")]
chats = ["ses_a", "ses_c", "ses_b"]
groups(projects, chats)
# [ {"name": "The Crew", "chats": ["ses_b"], ...},
#   {"name": "Other",    "chats": ["ses_c"], ...},
#   {"name": "Unsorted", "description": "Not in a project", "tags": [], "links": [],
#    "chats": ["ses_a"]} ]
```

## Style

Type hints. A one-line docstring per public function naming the rule it implements. No `print()`, no
module-level code beyond the constants. Follow HOUSE_STYLE.md, pasted below this contract when the
task is submitted.
