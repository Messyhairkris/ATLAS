# Contract: compactlib.py - the pure logic of the chat compact

One self-contained Python module, `compactlib.py`. It is the part of The Crew's chat compact
(Kris, 2026-10-27: "I requested a compact and Gordon did it, but it did not seem like a ready
built system") that needs no files and no network, so it can be tested on its own. The runner
`crew/runners/chat_compact.py` does the reading, backing up and HTTP; it passes the engine's
message JSON in and gets numbers and text back.

Allowed imports: `json`, `typing`, `__future__`. Nothing else - no files, no time, no printing.

## Public API

```python
STAGE_ORDER = ("none", "light", "medium", "heavy", "critical")
DEFAULT_STAGES = {"light": 0.60, "medium": 0.75, "heavy": 0.85, "critical": 0.95}
REASONING_KEEP = 500
TOOL_RESULT_KEEP = 2000
MESSAGE_KEEP = 10000

def stages_from(config: object) -> dict: ...
def stage_of(fraction: float, stages: dict) -> str: ...
def context_used(message: object) -> int: ...
def newest_fill(messages: object) -> int: ...
def truncate(text: object, keep: int) -> str: ...
def summary_input(messages: object, template: object) -> str: ...
```

## stages_from(config)

`config` is the parsed `crew/context.json`. The four thresholds live in its `stages` object;
Kris edits them. Returns a dict with exactly the four keys `light`, `medium`, `heavy`,
`critical`.

1. Start from `DEFAULT_STAGES`.
2. When `config` is a dict and `config["stages"]` is a dict, take each of the four names from it
   **when the value is a real number** (`int` or `float`, but not a `bool`).
3. Any name absent, or present with a non-number, keeps its default.
4. Unknown extra names in `config["stages"]` are ignored - the result has exactly four keys.
5. `config` being None, a string, a list, or a dict without `stages` -> the defaults, unchanged.

| config | result |
|---|---|
| `None` | `{"light": 0.60, "medium": 0.75, "heavy": 0.85, "critical": 0.95}` |
| `{"stages": {"medium": 0.8}}` | `{"light": 0.60, "medium": 0.8, "heavy": 0.85, "critical": 0.95}` |
| `{"stages": {"heavy": "big"}}` | heavy keeps `0.85` |
| `{"stages": {"light": True}}` | light keeps `0.60` (a bool is not a number here) |
| `{"stages": {"extra": 0.1}}` | the defaults; `extra` is ignored |

## stage_of(fraction, stages)

The **highest** stage in `STAGE_ORDER` whose threshold `fraction` has reached. Reaching the
threshold exactly counts (`>=`). Named in order, so the answer does not depend on the numbers
being in order - `light` is one step, `critical` is four.

A stage whose threshold is missing or not a number in `stages` is skipped.

| fraction | with `DEFAULT_STAGES` | returns |
|---|---|---|
| `0.0` | | `"none"` |
| `0.59` | | `"none"` |
| `0.60` | | `"light"` |
| `0.74` | | `"light"` |
| `0.75` | | `"medium"` |
| `0.849` | | `"medium"` |
| `0.85` | | `"heavy"` |
| `0.949` | | `"heavy"` |
| `0.95` | | `"critical"` |
| `1.2` | | `"critical"` |

`stage_of(0.8, {})` is `"none"` (nothing to compare against).

## context_used(message)

One message's JSON from the engine (the shape `opencode` stores in its `message` table). The
window's context meter reads `tokens.input + tokens.cache.read`; `tokens.input` alone
undercounts by nearly all of it, because the prompt is served mostly from the cache.

1. Not a dict, or no `tokens` dict -> `0`.
2. Otherwise `tokens["input"] + tokens["cache"]["read"]`.
3. `tokens["cache"]` missing or not a dict -> its read counts as `0`.
4. A value that is not a number counts as `0`; a `float` is floored to an `int`; a `bool` counts
   as `0`.

```python
context_used({"tokens": {"input": 702, "cache": {"read": 115200}}})  # 115902
context_used({"tokens": {"input": 287}})                            # 287
context_used({"role": "user"})                                      # 0
```

## newest_fill(messages)

`messages` is a list of message JSONs in the order they were said (oldest first). Returns
`context_used` of the **newest assistant message that finished and reported usage**; `0` when
there is none. This is the number the meter shows and the before/after line quotes.

1. Walk from the end.
2. A message counts only when it is a dict, `message["role"] == "assistant"`, and it
   **finished**: `message["time"]` is a dict with a `"completed"` key in it.
3. Of those, the newest whose `context_used` is greater than `0` is the answer.
4. Nothing matches -> `0`.

An assistant message that is still streaming (no `time.completed`) carries all-zero tokens and
would read as `0`; it is skipped, exactly as the window's meter does (measured 2026-10-27).

```python
messages = [
    {"role": "user", "time": {"created": 1}},
    {"role": "assistant", "time": {"created": 2, "completed": 3},
     "tokens": {"input": 100, "output": 5, "cache": {"read": 900}}},
    {"role": "assistant", "time": {"created": 4},
     "tokens": {"input": 0, "output": 0, "cache": {"read": 0}}},
]
newest_fill(messages)   # 1000 - the streaming last message is skipped
newest_fill([])         # 0
```

## truncate(text, keep)

The one cutting helper; the keeps above are its callers' arguments.

1. `text` not a `str` -> `""`.
2. `len(text) <= keep` -> `text` unchanged.
3. Otherwise `text[:keep]` followed by exactly this marker, on a new line:

```
\n...[trimmed: {len(text)} chars, kept {keep}]
```

```python
truncate("abc", 500)              # "abc"
truncate("x" * 600, 500)[:500]    # "x" * 500
truncate("x" * 600, 500).endswith("...[trimmed: 600 chars, kept 500]")  # True
```

## summary_input(messages, template)

The text kept beside the backup: what the conversation was, with the verbose parts cut, so a
person or a model can re-summarise if the engine's own summary ever needs replacing. Rules are
from the yeti-compact study (`runs/crew/outbox/atlas-research/a16-local-crush.md`).

Each item of `messages` is a small dict the runner builds, with any of these keys:

- `role`: `"user"` or `"assistant"` (default `"assistant"`).
- `text`: the prompt or the conclusion, cut with `truncate` at `MESSAGE_KEEP`.
- `reasoning`: the model's thinking, cut with `truncate` at `REASONING_KEEP`; kept only when
  non-empty.
- `tools`: a list of `{"name": ..., "input": ...}` - the tool **name and its input** are kept.
- `results`: a list of `{"name": ..., "output": ...}` - an output is cut with `truncate` at
  `TOOL_RESULT_KEEP`.

**The template and the messages are independent.** A non-empty `template` is the heading; the
messages are the body. Either may be absent: no messages gives the heading alone, an empty or
non-string template gives the body alone, and both empty gives `""`. Never return an empty string
merely because the template is empty.

The output is: the stripped `template` (when it is a non-empty string), then a blank line, then
one block per message, in order. Each block is:

```
## <role>
<text, cut with truncate at MESSAGE_KEEP>
reasoning: <reasoning, cut with truncate at REASONING_KEEP>   # only when reasoning is non-empty
tool <name>(<input>)                                          # one line per tool
result <name>: <output, cut with truncate at TOOL_RESULT_KEEP># one line per result
```

Empty lines inside a block are dropped, so a message with none of `text`, `reasoning`, `tools`,
`results` contributes only its `## <role>` heading. `inputs` inside a tool are rendered as JSON
(`json.dumps(input, sort_keys=True)`), so the text is stable.

```python
summary_input([{"role": "user", "text": "Compact this chat."}], "# Summary input")
# "# Summary input\n\n## user\nCompact this chat."
summary_input([{"role": "user", "text": "Compact this chat."}], "")
# "## user\nCompact this chat."          <- an empty template still keeps the messages
summary_input([{"role": "assistant"}], "")   # "## assistant"
summary_input([], "# Only a template")       # "# Only a template"
summary_input([], "")                        # ""
summary_input([], None)                      # ""
```

## Style

Type hints, a one-line docstring per public function naming the rule it implements, no
`print()`. Follow HOUSE_STYLE.md, pasted below this contract when the task is submitted.
