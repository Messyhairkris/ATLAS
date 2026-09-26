# Contract: st_schema.py - check a model's native tool calls before anything runs

One self-contained Python module, `st_schema.py`, for the special-teams harness
(Kimi driving real tools through native tool calling). A model's tool call is
text the model wrote; before the harness executes it, this module turns it into
a clean `(name, args)` pair or a precise error the model can fix.

Why it matters: a published agent study (Continual Harness, 2026) watched a model
repeat one malformed tool call 1,003 times because nothing told it what was wrong.
Every error string here must say exactly what to change.

## Public API (all of these names must exist)

```python
def parse_tool_calls(message: dict) -> list: ...
def validate_args(schema: dict, args: dict) -> list: ...
def check_call(tools: list, name: str, args: dict) -> list: ...
```

Allowed imports: `json`. Nothing else.

## parse_tool_calls(message)

`message` is one assistant message in OpenAI chat format. Its `tool_calls` key
(missing or `None` means no calls) holds a list of calls shaped like:

```python
{"id": "call_1", "type": "function",
 "function": {"name": "browser_click", "arguments": "{\"ref\": \"e12\"}"}}
```

Return a list with one dict per call, in the same order:

```python
{"id": "call_1", "name": "browser_click", "args": {"ref": "e12"}, "error": None}
```

Rules:

1. `arguments` may be a JSON **string** (usual) or already a **dict**. A dict is used as is.
2. An empty string, `None` or a missing `arguments` means `{}` (no error).
3. A string that is not valid JSON gives `args: {}` and
   `error: "arguments are not valid JSON: <the json error message>"`.
4. Valid JSON that is not an object (e.g. a list or a number) gives `args: {}` and
   `error: "arguments must be a JSON object"`.
5. A missing `id` becomes `""`; a missing function name becomes `""` with
   `error: "tool call has no function name"` (if rule 3 or 4 already set an error,
   keep that first error).
6. No `tool_calls` -> `[]`.

## validate_args(schema, args)

`schema` is a JSON-Schema **subset**: `{"type": "object", "properties": {...},
"required": [...], "additionalProperties": false}`. Each property is
`{"type": T}` with optional `"enum": [...]`, where T is one of `"string"`,
`"integer"`, `"number"`, `"boolean"`, `"array"`, `"object"`.

Return a list of error strings; `[]` means valid. Check in this order and report
every problem found (not just the first):

1. every name in `required` that is missing from `args`:
   `"missing required argument '<name>'"`
2. for each key in `args` (in the order of `args`):
   - not in `properties` and `additionalProperties` is `False`:
     `"unknown argument '<name>'"` (when `additionalProperties` is absent or
     `True`, unknown keys are allowed and not type-checked)
   - wrong type: `"argument '<name>' must be <T>, got <python type name>"`
     where the python type name is `type(value).__name__`
   - has `enum` and the value is not in it:
     `"argument '<name>' must be one of <enum as a Python list repr>"`
     (only checked when the type is right)

Type rules: `"integer"` accepts `int` but **not** `bool`; `"number"` accepts `int`
and `float` but not `bool`; `"boolean"` only `bool`; `"string"` only `str`;
`"array"` only `list`; `"object"` only `dict`. A property with no `type` accepts anything.

## check_call(tools, name, args)

`tools` is the list sent to the model, each item
`{"type": "function", "function": {"name": ..., "description": ..., "parameters": schema}}`.

- If no tool has that name: return
  `["unknown tool '<name>'; available: <names sorted and joined with ', '>"]`.
- Else return `validate_args(<that tool's parameters>, args)`; a tool with no
  `parameters` accepts only `{}` (any key is `"unknown argument '<k>'"`).

## Examples

```python
validate_args({"type": "object", "properties": {"n": {"type": "integer"}},
               "required": ["n"], "additionalProperties": False}, {"n": True, "x": 1})
# -> ["argument 'n' must be integer, got bool", "unknown argument 'x'"]

validate_args({"type": "object", "properties": {"mode": {"type": "string", "enum": ["a", "b"]}},
               "required": ["mode", "ref"]}, {"mode": "c"})
# -> ["missing required argument 'ref'", "argument 'mode' must be one of ['a', 'b']"]

parse_tool_calls({"tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": "{bad"}}]})
# -> [{"id": "c1", "name": "t", "args": {}, "error": "arguments are not valid JSON: ..."}]
```

The error text after `valid JSON: ` is `str()` of the `json.JSONDecodeError`.
