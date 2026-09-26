# Contract: st_mission.py - the guard around a special-teams mission

One self-contained Python module, `st_mission.py`. A special-teams member (Kimi)
drives real tools - a browser, for example - through native tool calls. Kimi is
capable but known for "excessive proactiveness": doing things nobody asked for.
Before the harness runs any call, it asks this module whether the call is part of
the mission; after the call it records what happened; between calls it asks
whether the mission must stop.

## Public API (all of these names must exist)

```python
def url_allowed(url, prefixes: list) -> bool: ...

class Mission:
    def __init__(self, allowed_tools: list, acting_tools: list, url_prefixes: list,
                 max_steps: int, max_actions: int,
                 max_errors_in_a_row: int = 3, max_repeats: int = 2): ...
    def check(self, name: str, args: dict): ...        # None, or a refusal string
    def record(self, name: str, args: dict, ok: bool) -> None: ...
    def stop_reason(self): ...                          # None, or a reason string
    def summary(self) -> dict: ...
```

Allowed imports: `json`, `urllib.parse`. Nothing else.

## url_allowed(url, prefixes)

True only when ALL hold:

1. `url` is a non-empty `str`.
2. Its scheme (lowercased) is `http`, `https` or `file`.
3. After `urllib.parse.unquote` of the path, no path segment (split on `/`) is `..`.
4. Some prefix matches: same scheme (lowercased), same netloc (lowercased), and the
   url's unquoted path starts with the prefix's unquoted path. For `file` URLs the
   path comparison is case-insensitive (Windows paths); for `http`/`https` it is
   case-sensitive. Query strings and fragments of the url are ignored.

Anything else is False (never an exception). A prefix meant as a folder ends in
`/`, so `file:///C:/work/` does not match `file:///C:/workshop/x`.

## Mission

Attributes readable at any time: `steps`, `actions`, `errors_in_a_row`, `refused`.
All start at 0.

### check(name, args) -> None or str

Return the FIRST applicable refusal, else `None`. Each refusal adds 1 to
`refused` and to an internal refused-in-a-row counter; a `None` answer does not
change any counter.

1. `steps >= max_steps` -> `"step budget spent (<max_steps> steps)"`
2. `name` not in `allowed_tools` -> `"tool '<name>' is not part of this mission"`
3. `name` in `acting_tools` and `actions >= max_actions` ->
   `"action budget spent (<max_actions> actions)"`
4. `args` has a key `"url"` and `url_allowed(args["url"], url_prefixes)` is False ->
   `"url '<url>' is outside this mission's allowlist"`
5. The same call - same `name` and args equal after
   `json.dumps(args, sort_keys=True)` - has already been RECORDED `max_repeats`
   times -> `"repeated call: '<name>' with the same arguments <n> times already"`
   where `<n>` is that count.

### record(name, args, ok)

Called after a call ran (only allowed calls are recorded):

- `steps += 1`; resets the refused-in-a-row counter to 0
- if `name` in `acting_tools`: `actions += 1`
- `ok` False -> `errors_in_a_row += 1`; `ok` True -> `errors_in_a_row = 0`
- counts the call for rule 5 and for `summary()["by_tool"]`

### stop_reason() -> None or str

First that applies:

1. `steps >= max_steps` -> `"max_steps"`
2. `errors_in_a_row >= max_errors_in_a_row` -> `"errors_in_a_row"`
3. refused-in-a-row `>= 3` -> `"refused_in_a_row"`
4. otherwise `None`

### summary() -> dict

```python
{"steps": int, "actions": int, "refused": int, "errors_in_a_row": int,
 "by_tool": {name: times recorded}, "stop_reason": stop_reason()}
```

## Example

```python
m = Mission(["browser_navigate", "browser_click"], ["browser_click"],
            ["file:///C:/work/"], max_steps=10, max_actions=1)
m.check("browser_navigate", {"url": "file:///C:/work/a.html"})   # None
m.record("browser_navigate", {"url": "file:///C:/work/a.html"}, True)
m.check("browser_type", {})        # "tool 'browser_type' is not part of this mission"
m.check("browser_click", {"ref": "e1"})   # None
m.record("browser_click", {"ref": "e1"}, True)
m.check("browser_click", {"ref": "e2"})   # "action budget spent (1 actions)"
m.summary()["by_tool"]             # {"browser_navigate": 1, "browser_click": 1}
```
