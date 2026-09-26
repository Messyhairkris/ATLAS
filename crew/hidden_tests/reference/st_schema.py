"""PA reference implementation of contracts/st_schema.md (never shown to the crew)."""

import json

_TYPES = {"string": (str,), "integer": (int,), "number": (int, float),
          "boolean": (bool,), "array": (list,), "object": (dict,)}


def parse_tool_calls(message):
    out = []
    for call in (message or {}).get("tool_calls") or []:
        fn = call.get("function") or {}
        raw = fn.get("arguments")
        args, error = {}, None
        if isinstance(raw, dict):
            args = raw
        elif raw in (None, ""):
            args = {}
        else:
            try:
                val = json.loads(raw)
            except json.JSONDecodeError as e:
                error = f"arguments are not valid JSON: {e}"
            else:
                if isinstance(val, dict):
                    args = val
                else:
                    error = "arguments must be a JSON object"
        name = fn.get("name") or ""
        if not name and error is None:
            error = "tool call has no function name"
        out.append({"id": call.get("id") or "", "name": name, "args": args, "error": error})
    return out


def _type_ok(t, v):
    if t is None:
        return True
    if t in ("integer", "number") and isinstance(v, bool):
        return False
    return isinstance(v, _TYPES[t])


def validate_args(schema, args):
    errors = []
    props = schema.get("properties") or {}
    for r in schema.get("required") or []:
        if r not in args:
            errors.append(f"missing required argument '{r}'")
    extra_ok = schema.get("additionalProperties", True) is not False
    for k, v in args.items():
        if k not in props:
            if not extra_ok:
                errors.append(f"unknown argument '{k}'")
            continue
        t = props[k].get("type")
        if not _type_ok(t, v):
            errors.append(f"argument '{k}' must be {t}, got {type(v).__name__}")
            continue
        if "enum" in props[k] and v not in props[k]["enum"]:
            errors.append(f"argument '{k}' must be one of {props[k]['enum']!r}")
    return errors


def check_call(tools, name, args):
    for t in tools:
        fn = t.get("function") or {}
        if fn.get("name") == name:
            params = fn.get("parameters")
            if params is None:
                return [f"unknown argument '{k}'" for k in args]
            return validate_args(params, args)
    names = sorted((t.get("function") or {}).get("name", "") for t in tools)
    return [f"unknown tool '{name}'; available: {', '.join(names)}"]
