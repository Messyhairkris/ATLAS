"""The crew member's read-only work loop.

Protocol (plain text, so it works with any chat model — no provider
tool-calling support needed): each reply is EITHER one JSON tool call OR a
submission ("SUBMIT" + fenced file blocks + optional ```notes block).

Leash, by construction rather than by prompt:
- hard request budget per job (Synthetic subscriptions meter requests);
- repeated identical tool calls are not re-executed, and three repeats end
  the job (loop); two invalid replies in a row end it (contract abandoned);
- every submission is gated; the BEST submission is kept (attempts.py), and
  a regressing or identical resubmission ends the loop;
- older tool results are trimmed so a small model's prompt stays small.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from attempts import AttemptTracker  # noqa: E402

from .tools import ToolError  # noqa: E402

FENCE = re.compile(r"^```([^\s`]*)[^\n]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
LANG_TAGS = {"", "md", "markdown", "json", "text", "txt"}
KEEP_FULL_RESULTS = 3
TRIMMED_CHARS = 400
MAX_REPEATS = 3
MAX_INVALID_IN_A_ROW = 2
MAX_EMPTY = 3
MAX_TRUNCATIONS = 3

SYSTEM_TEMPLATE = """You are {persona}, a crew member on a human+AI team. You work ONE task using READ-ONLY tools. You cannot write, run, move, or delete anything; automatic checks grade your submission, then a reviewer decides.

EVERY REPLY IS EXACTLY ONE OF:
1. A tool call, as a single JSON object and nothing else, e.g.
   {{"tool": "search", "args": {{"pattern": "orbit", "path": "."}}}}
2. Your submission: the word SUBMIT on its own line, then one fenced block per output file whose info string is the file name, e.g.
   SUBMIT
   ```{example_file}
   ...file content...
   ```
   optionally followed by a ```notes block with 0-3 one-line lessons that would help the next person doing this kind of task.

TOOLS
- list_dir(path=".")
- read_file(path, start=1, lines=200)
- search(pattern, path=".", max_hits=30)  (regex, case-insensitive, searches file contents)
- fetch_url(url){fetch_note}
Relative paths resolve against the first read root.

BUDGET: {max_requests} replies in total for this task, tool calls and submissions included. Submit before you run out.

PLAYBOOK for {task_type} (rules learned from earlier runs; follow every one):
{playbook}
"""


def parse_reply(text: str, expected_files: List[str]) -> Tuple[str, object, object]:
    """-> ("submit", files, notes) | ("tool", name, args) | ("invalid", reason, None)"""
    text = (text or "").strip()
    blocks = FENCE.findall(text)
    file_blocks = [(i, c) for i, c in blocks if i.lower() != "notes"]
    looks_like_submit = re.search(r"^\s*SUBMIT\b", text, re.MULTILINE) or any(
        "." in i and i.lower() not in LANG_TAGS for i, _ in file_blocks)
    if looks_like_submit and file_blocks:
        files: Dict[str, str] = {}
        for info, content in file_blocks:
            name = info.strip()
            if name.lower() in LANG_TAGS:
                if len(expected_files) == 1 and expected_files[0] not in files:
                    name = expected_files[0]
                else:
                    continue
            files[name] = content.rstrip() + "\n"
        notes = []
        for info, content in blocks:
            if info.lower() == "notes":
                notes += [l.strip().lstrip("-* ").strip()
                          for l in content.splitlines() if l.strip()]
        if files:
            return "submit", files, notes[:3]
    call = _find_tool_json(text)
    if call:
        return "tool", call[0], call[1]
    return "invalid", ("reply was neither one JSON tool call nor SUBMIT with "
                       "fenced file blocks"), None


def _find_tool_json(text: str) -> Optional[Tuple[str, dict]]:
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("tool") or obj.get("name")
        args = obj.get("args", obj.get("arguments", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if isinstance(name, str) and isinstance(args, dict):
            return name, args
    return None


# gpt-oss was trained with a built-in "repo_browser" tool namespace. Even when
# no tools are declared, it sometimes emits a NATIVE tool call (harmony
# channel) that the provider returns as message.tool_calls with content null
# (Synthetic, 2026-09-19: "repo_browser.read_file"). Those are real work, not
# empty replies: accept them and map its trained names onto ours.
NATIVE_TOOL_NAMES = {"read_file": "read_file", "open_file": "read_file",
                     "open": "read_file", "cat": "read_file",
                     "list_dir": "list_dir", "list_directory": "list_dir",
                     "print_tree": "list_dir", "ls": "list_dir",
                     "search": "search", "grep": "search", "find": "search",
                     "fetch_url": "fetch_url", "fetch": "fetch_url"}
NATIVE_ARG_NAMES = {"line_start": "start", "start_line": "start",
                    "query": "pattern", "regex": "pattern", "file": "path",
                    "filepath": "path", "dir": "path", "directory": "path"}


def native_tool_call(res: dict) -> Optional[Tuple[str, dict]]:
    try:
        calls = res["raw"]["choices"][0]["message"].get("tool_calls") or []
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    for call in calls:
        fn = (call or {}).get("function") or {}
        raw_name = str(fn.get("name") or "")
        name = NATIVE_TOOL_NAMES.get(raw_name.rsplit(".", 1)[-1].lower())
        if not name:
            continue
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        mapped = {NATIVE_ARG_NAMES.get(k, k): v for k, v in args.items()}
        if "line_end" in mapped:
            end = mapped.pop("line_end")
            try:
                mapped["lines"] = max(1, int(end) - int(mapped.get("start", 1)) + 1)
            except (TypeError, ValueError):
                pass
        allowed = {"read_file": {"path", "start", "lines"},
                   "list_dir": {"path"},
                   "search": {"pattern", "path", "max_hits"},
                   "fetch_url": {"url"}}[name]
        return name, {k: v for k, v in mapped.items() if k in allowed}
    return None


def _trim_old_results(messages: List[dict]) -> None:
    results = [m for m in messages if m.get("_result")]
    for m in results[:-KEEP_FULL_RESULTS]:
        if not m.get("_trimmed") and len(m["content"]) > TRIMMED_CHARS:
            m["content"] = (m["content"][:TRIMMED_CHARS]
                            + "\n...[older result trimmed; call the tool again "
                              "if you need it]")
            m["_trimmed"] = True


def run_member(*, persona: str, task_type: str, playbook: str, task_text: str,
               expected_files: List[str], toolbox, grade: Callable[[Dict[str, str]], List[dict]],
               chat: Callable[[List[dict], int], dict], max_requests: int,
               max_tokens: int, fetch_enabled: bool,
               log: Callable[[dict], None] = lambda e: None) -> dict:
    system = SYSTEM_TEMPLATE.format(
        persona=persona, task_type=task_type, playbook=playbook.strip(),
        max_requests=max_requests, example_file=expected_files[0],
        fetch_note="" if fetch_enabled else "  (disabled for this task)")
    messages: List[dict] = [{"role": "system", "content": system},
                            {"role": "user", "content": task_text}]
    tracker = AttemptTracker()
    calls: Counter = Counter()
    repeats = invalid_run = requests = tokens = empties = natives = 0
    truncations = 0
    stop_reason = None
    submissions = 0

    while True:
        if requests >= max_requests:
            stop_reason = stop_reason or "budget_requests"
            break
        if tokens >= max_tokens:
            stop_reason = "budget_tokens"
            break
        _trim_old_results(messages)
        wire = [{"role": m["role"], "content": m["content"]} for m in messages]
        res = chat(wire, requests)
        requests += 1
        usage = (res.get("raw") or {}).get("usage") or {}
        tokens += usage.get("total_tokens", 0) or 0
        reply = res.get("content") or ""
        left = max_requests - requests
        native = native_tool_call(res) if not reply.strip() else None
        if native:
            # Re-express it in our text protocol so the transcript the member
            # sees next turn is consistent with what we asked for.
            reply = json.dumps({"tool": native[0], "args": native[1]})
            natives += 1
        if not reply.strip():
            # Observed with gpt-oss (2026-09-19): ~15% of calls spend 100-150
            # completion tokens on reasoning and put nothing in the answer.
            # A nudge, not a contract violation; but still a spent request.
            empties += 1
            log({"event": "reply", "n": requests, "kind": "empty",
                 "tokens": usage.get("total_tokens", 0),
                 "reasoning_chars": len(res.get("reasoning") or "")})
            if empties >= MAX_EMPTY:
                stop_reason = "empty_replies"
                break
            messages.append({"role": "assistant", "content": "(empty reply)"})
            messages.append({"role": "user", "content":
                             "EMPTY REPLY: your answer channel was empty. You "
                             "spent the whole output budget thinking and never "
                             "wrote an answer. Think briefly, then put the JSON "
                             "tool call or the SUBMIT block in the answer "
                             "itself - a plan in your reasoning reaches nobody. "
                             "If the file is long, write it directly without "
                             "drafting it first. "
                             f"({left} replies left)"})
            continue
        messages.append({"role": "assistant", "content": reply})
        kind, a, b = parse_reply(reply, expected_files)
        log({"event": "reply", "n": requests, "kind": kind,
             "tokens": usage.get("total_tokens", 0), "reply": reply[:4000]})

        if kind == "invalid" and re.search(r"^\s*SUBMIT\b", reply, re.MULTILINE) \
                and reply.count("```") % 2 == 1:
            # A submission cut off by the reply-length limit: the closing
            # fence never arrived. Say so; "invalid reply" would mislead.
            truncations += 1
            if truncations >= MAX_TRUNCATIONS:
                stop_reason = "output_truncated"
                break
            messages.append({"role": "user", "content":
                             "SUBMISSION CUT OFF: your reply hit the length limit "
                             "before the closing ``` fence. SUBMIT again, shorter: "
                             "fewer words per row, no repeated explanations. "
                             f"({left} replies left)"})
            continue

        if kind == "invalid":
            invalid_run += 1
            if invalid_run >= MAX_INVALID_IN_A_ROW:
                stop_reason = "contract_abandoned"
                break
            messages.append({"role": "user", "content":
                             f"INVALID REPLY: {a}. Reply with ONE JSON tool call "
                             f"or SUBMIT + fenced file blocks. ({left} replies left)"})
            continue
        invalid_run = 0

        if kind == "tool":
            key = json.dumps([a, b], sort_keys=True)
            calls[key] += 1
            if calls[key] > 1:
                repeats += 1
                log({"event": "repeat", "call": key})
                if repeats >= MAX_REPEATS:
                    stop_reason = "loop_repeat"
                    break
                messages.append({"role": "user", "content":
                                 f"REPEATED CALL {a}: you already have that result "
                                 f"above. Take a different step or SUBMIT. "
                                 f"({left} replies left)"})
                continue
            try:
                out = toolbox.call(a, b)
                content = f"RESULT {a}({json.dumps(b)}) [{left} replies left]:\n{out}"
            except ToolError as e:
                content = f"TOOL ERROR {a}: {e} [{left} replies left]"
            except OSError as e:
                content = f"TOOL ERROR {a}: {type(e).__name__}: {e} [{left} replies left]"
            if left == 1:
                content += "\nLAST REPLY: you must SUBMIT now."
            log({"event": "tool", "tool": a, "args": b, "result_chars": len(content)})
            messages.append({"role": "user", "content": content, "_result": True})
            continue

        # submission
        submissions += 1
        files, notes = a, b
        steps = grade(files)
        passed = bool(steps) and all(s["ok"] for s in steps)
        log({"event": "submission", "n": submissions, "passed": passed,
             "files": sorted(files), "steps": steps})
        go_on = tracker.add(submissions, files, steps, passed, notes=notes)
        if not go_on:
            stop_reason = tracker.stop_reason
            break
        failed = "\n".join(f"- [{s['rung']}] {s.get('file', '')}: {s['detail']}"
                           for s in steps if not s["ok"])
        messages.append({"role": "user", "content":
                         f"SUBMISSION FAILED THESE CHECKS:\n{failed}\n"
                         f"Fix only these. You may use tools, then SUBMIT the "
                         f"complete file(s) again. ({left} replies left)"})

    best = tracker.best
    return {"stop_reason": stop_reason, "requests": requests, "tokens": tokens,
            "submissions": submissions, "repeats": repeats, "empty_replies": empties,
            "native_tool_calls": natives,
            "passed": bool(best and best["passed"]),
            "files": best["files"] if best else {},
            "steps": best["steps"] if best else [],
            "notes": (best or {}).get("notes", []) if best else [],
            "evidence": toolbox.evidence.keys(),
            **({"tracker": tracker.summary()} if best else {})}
