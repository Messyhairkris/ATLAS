# Contract: alive_lib.py - tell alive from dead

One self-contained Python module, `alive_lib.py`. It decides, from four plain facts, whether a
running turn or build is **WORKING**, **QUIET** or **DEAD** - the question Kris asked after the
crash: "there is no way for me to tell if it's still processing or just appears to be."

It is the pure half. The runner `crew/runners/alive.py` reads the facts (the engine database, the
engine process, a build's `status.json`) and passes them in; this module never touches a file, a
clock or a process.

Allowed imports: `json`, `typing`, `__future__`. Nothing else.

## Public API

```python
STATES = ("WORKING", "QUIET", "DEAD")
DEFAULT_QUIET_S = 120

def state_of(now, started=None, activity=None, engine_start=None, alive=None, quiet_s=DEFAULT_QUIET_S) -> str: ...
def age_of(now, activity) -> object: ...
def doing_of(part) -> str: ...
def line(now, started=None, activity=None, engine_start=None, alive=None, quiet_s=DEFAULT_QUIET_S, doing="") -> str: ...
```

All times are **seconds** (a float or int). `alive` is `True`, `False`, or `None` when nobody
checked. Every argument except `now` may be missing.

## state_of - the rules, first match wins

The one that the crash taught us is rule 1: a turn that started before the engine that is running
now **can never finish**, whatever the process table says. That turn was real - my compact dry run
started 15:00:32 and the engine restarted at 15:41.

1. `alive is False` -> `"DEAD"`. The process is gone.
2. `started` and `engine_start` are both given, and `started < engine_start` -> `"DEAD"`.
   It began **before** the current engine; it cannot complete. Starting at the same moment the
   engine did (`started == engine_start`) is not "before it" and does not fire this rule.
3. `activity is None` -> `"QUIET"`. Nothing to read yet (a turn may just have started).
4. `now - activity < quiet_s` -> `"WORKING"` (strictly less: an activity exactly `quiet_s` old is
   already `QUIET`).
5. Otherwise -> `"QUIET"`. Silence, but the process is alive - a slow model, or a long cargo build.

A `quiet_s` of `0` or less makes rule 4 never true, so an activity the runner did see still reads
`"QUIET"`; that is how a caller asks to be told about any pause.

| now | started | activity | engine_start | alive | quiet_s | state_of |
|---|---|---|---|---|---|---|
| 1000 | - | 988 | - | True | 120 | `WORKING` |
| 1000 | - | 881 | - | True | 120 | `WORKING` (119 s ago) |
| 1000 | - | 880 | - | True | 120 | `QUIET` (age 120 is at the line, not under it) |
| 1000 | - | 60 | - | True | 120 | `QUIET` |
| 1000 | - | - | - | True | 120 | `QUIET` |
| 1000 | - | 900 | - | False | 120 | `DEAD` |
| 1000 | 100 | 900 | 500 | True | 120 | `DEAD` (started before the engine) |
| 1000 | 500 | 900 | 500 | True | 120 | `WORKING` (started with the engine, not before) |
| 1000 | 100 | 900 | - | True | 120 | `WORKING` (no engine start given, so rule 2 cannot fire) |
| 1000 | - | 999 | - | None | 120 | `WORKING` (alive unknown is not dead) |

## age_of

`int(now - activity)` when both are numbers; `None` otherwise. Never negative? It may be
**negative** when the activity is in the future, and that is reported as it is rather than
invented away - the caller can see a clock problem for what it is.

| now | activity | age_of |
|---|---|---|
| 1000 | 988 | `12` |
| 1000.9 | 988.0 | `12` (floored) |
| 1000 | None | `None` |
| None | 988 | `None` |
| 1000 | 1010 | `-10` |

## doing_of

What the turn is doing, from the newest part's own JSON. A part's JSON carries `type`, and a tool
part also carries `tool`:

| part | doing_of |
|---|---|
| `{"type": "tool", "tool": "read"}` | `"tool read"` |
| `{"type": "tool", "tool": ""}` | `"tool"` |
| `{"type": "text", "text": "hi"}` | `"text"` |
| `{"type": "step-start"}` | `"step-start"` |
| `{}` | `""` |
| `None` | `""` |

A tool whose `tool` is missing or not a non-empty string gives just `"tool"`.

## line - exactly what the header shows

Two spaces after the state word, so the three line up in a fixed-width font.

1. WORKING, with `doing`: `WORKING  last activity 12s ago (tool read)`
2. WORKING, no `doing`: `WORKING  last activity 12s ago`
3. QUIET with an age: `QUIET    no activity for 940s, but the process is alive`
4. QUIET with no age: `QUIET    no activity yet, but the process is alive`
5. DEAD because the process is gone:
   `DEAD     its process is gone; it will never finish - resend`
6. DEAD because it started before the engine:
   `DEAD     started before this engine; it will never finish - resend`

There is no WORKING-with-no-age case: `state_of` returns WORKING only when it has an age, so the
four WORKING/QUIET lines above are exhaustive.

`line` calls `state_of` and then formats; it does not re-decide.

```python
line(1000, activity=988, alive=True) == "WORKING  last activity 12s ago"
line(1000, activity=988, alive=True, doing="tool read") == "WORKING  last activity 12s ago (tool read)"
line(1000, activity=60, alive=True) == "QUIET    no activity for 940s, but the process is alive"
line(1000, alive=True) == "QUIET    no activity yet, but the process is alive"
line(1000, activity=900, alive=False) == "DEAD     its process is gone; it will never finish - resend"
line(1000, started=100, engine_start=500, alive=True) == "DEAD     started before this engine; it will never finish - resend"
```

When both DEAD reasons apply (no process AND started before the engine), rule 1 of `state_of`
fires first, so the line is the "process is gone" one.

## Style

Type hints, a one-line docstring per public function naming the rule it implements, no `print()`.
Follow HOUSE_STYLE.md, pasted below this contract when the task is submitted.
