# Contract: attention_lib.py - which conversations need you

One self-contained Python module, `attention_lib.py`. It answers the Project folders requirement
(Kris, 2026-10-30): "should show an indicator when a conversation needs attention or activity has
finished." One conversation gets one state; a folder gets one state from its conversations.

It is the pure half. A runner reads the engine database and the job store and passes the four facts
in; this module never touches a file, a clock or a process.

**Allowed imports: `typing`, `__future__`.** Nothing else - no `open()` (the crew's airlock bans it).

## Public API

```python
STATES = ("needs_attention", "finished", "working", "idle")
DEFAULT_QUIET_S = 120

def state_for(now, last_activity=None, last_read=None, running=False, alive=None,
              finished_at=None, quiet_s=DEFAULT_QUIET_S) -> str
def label(state) -> str
def folder_state(states) -> str
```

All times are **seconds** (int or float). Every argument but `now` may be missing. `alive` is
`True`, `False`, or `None` when nobody checked. `running` says a turn or a job is in flight.
`last_read` is when Kris last looked at the conversation; `None` means never.

## state_for - the rules, first match wins

1. `running is True` and `alive is False` -> `"needs_attention"`. It is running, but its process is
   gone, so it will never finish - the one case that always needs a person.
2. `running is True` and `last_activity is None` -> `"working"`. Just started; nothing to read yet.
3. `running is True` and `now - last_activity < quiet_s` -> `"working"`. Strictly less: an activity
   exactly `quiet_s` old is already quiet.
4. `running is True` -> `"needs_attention"`. Silent while running - a hang, or a slow model.
5. `finished_at is not None` and (`last_read is None` or `finished_at > last_read`) ->
   `"finished"`. A run ended since Kris last looked.
6. `last_activity is not None` and (`last_read is None` or `last_activity > last_read`) ->
   `"needs_attention"`. Something happened since Kris last looked.
7. anything else -> `"idle"`.

A `quiet_s` of `0` or less makes rule 3 never true, so a running conversation always falls through
to rule 4 - that is how a caller asks to be told about any pause.

| now | last_activity | last_read | running | alive | finished_at | quiet_s | state_for |
|---|---|---|---|---|---|---|---|
| 1000 | 988 | 900 | True | True | - | 120 | `working` |
| 1000 | 880 | 900 | True | True | - | 120 | `needs_attention` (quiet while running) |
| 1000 | 900 | 900 | True | True | - | 120 | `working` (age 100 is under 120) |
| 1000 | - | - | True | True | - | 120 | `working` (just started) |
| 1000 | 988 | - | True | False | - | 120 | `needs_attention` (running, process gone) |
| 1000 | 980 | 900 | False | - | 990 | 120 | `finished` |
| 1000 | 998 | 995 | False | - | 990 | 120 | `needs_attention` (activity after the read) |
| 1000 | 980 | None | False | - | - | 120 | `needs_attention` (never read) |
| 1000 | 1000 | 999 | False | - | - | 120 | `needs_attention` (activity after the read) |
| 1000 | 980 | 980 | False | - | - | 120 | `idle` (read exactly at the activity) |
| 1000 | None | None | False | - | - | 120 | `idle` (nothing ever happened) |
| 1000 | 880 | 900 | True | True | - | 0 | `needs_attention` (quiet_s 0 turns rule 3 off) |

## label

A short human phrase for the indicator, no glyphs:

| state | label |
|---|---|
| `"needs_attention"` | `"needs attention"` |
| `"finished"` | `"finished"` |
| `"working"` | `"working"` |
| `"idle"` | `"idle"` |
| anything else (`None`, `""`, `"nonsense"`) | `"idle"` |

## folder_state

The folder's own indicator, from its conversations' states. The first of
`("needs_attention", "finished", "working", "idle")` that appears in `states` wins, so one
conversation needing attention marks the folder. An empty list, `None`, or a list of unknown values
gives `"idle"`.

```
folder_state(["idle", "finished", "working"])   # "finished"
folder_state(["idle", "working"])               # "working"
folder_state([])                                # "idle"
folder_state(None)                              # "idle"
folder_state(["nonsense"])                      # "idle"
```

## Style

Type hints. A one-line docstring per public function naming the rule it implements. No `print()`, no
module-level code beyond the constants. Follow HOUSE_STYLE.md, pasted below this contract when the
task is submitted.
