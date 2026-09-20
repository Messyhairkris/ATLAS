# Contract: chattiness.py — deciding what the voice mentions

One self-contained Python module, `chattiness.py`. Pure decision logic: given an
event that happened inside VtoT and the user's chattiness level, say whether the
voice mentions it, and what it would say.

From TTS_SPEC_DRAFT.md section 3: one setting, five levels, and **each level
includes everything the quieter levels say**. A user dictating with their eyes
off the screen turns this up; a user who can see it turns it down.

## Public API

```python
LEVELS = ("off", "brief", "normal", "full", "verbatim")
EVENTS = (...)                 # tuple of the event names below
SPEAKS_FROM = {...}            # event name -> the quietest level that says it

def level_index(level: str) -> int: ...
def should_speak(event: str, level: str) -> bool: ...
def describe(event: str, payload: dict) -> str: ...
```

Allowed imports: `typing`. Nothing else.

## The events, and the quietest level that mentions each

| event | speaks from | why |
|---|---|---|
| `"error"` | `brief` | something went wrong; silence would hide it |
| `"mode_change"` | `brief` | the user must know which mode is listening |
| `"read_back"` | `brief` | the user explicitly asked to hear text |
| `"command_applied"` | `normal` | confirmation a command landed |
| `"block_created"` | `normal` | structure changed |
| `"dictation_word"` | `full` | echoing each word as it is typed |
| `"edit_applied"` | `full` | Kris's "speaks all of the edits" |
| `"punctuation"` | `verbatim` | naming the marks |
| `"whitespace"` | `verbatim` | naming line breaks and tabs |

`EVENTS` must contain exactly these nine names. `SPEAKS_FROM` must map every one
of them to one of `"brief"`, `"normal"`, `"full"`, `"verbatim"` exactly as the
table says.

## level_index(level)

The position of `level` in `LEVELS` (`"off"` is 0, `"verbatim"` is 4). An unknown
level raises `ValueError`.

## should_speak(event, level)

- an event not in `EVENTS` raises `ValueError`
- a level not in `LEVELS` raises `ValueError`
- `level == "off"` is always `False`, for every event, including `"error"`
- otherwise `True` when `level_index(level) >= level_index(SPEAKS_FROM[event])`

So at `"normal"`: `error` and `command_applied` speak, `dictation_word` and
`punctuation` do not. At `"verbatim"` everything speaks.

## describe(event, payload)

Returns the sentence the voice would say. `payload` is a dict. An unknown event
raises `ValueError`; a payload missing the key an event needs raises `KeyError`
(just reading the key is enough — do not invent a default).

| event | needs | returns |
|---|---|---|
| `"error"` | `message` | `"error: " + message` |
| `"mode_change"` | `mode` | `mode + " mode"` |
| `"read_back"` | `text` | `text` unchanged |
| `"command_applied"` | `command` | `command + " applied"` |
| `"block_created"` | `block` | `"new " + block` |
| `"dictation_word"` | `word` | `word` unchanged |
| `"edit_applied"` | `what`, `to` | `what + " changed to " + to` |
| `"punctuation"` | `name` | `name` unchanged |
| `"whitespace"` | `name` | `name` unchanged |

Examples the tests use:

```python
describe("error", {"message": "microphone lost"})        == "error: microphone lost"
describe("mode_change", {"mode": "command"})             == "command mode"
describe("command_applied", {"command": "heading two"})  == "heading two applied"
describe("block_created", {"block": "bullet list"})      == "new bullet list"
describe("edit_applied", {"what": "colour", "to": "color"}) == "colour changed to color"
```

## Style

Type hints, a one-line docstring per function naming the rule it implements, no
`print()`. Write the complete file.
