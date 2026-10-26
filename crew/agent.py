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

from . import ask as asking  # noqa: E402
from . import compact  # noqa: E402
from .tools import ToolError  # noqa: E402

FENCE = re.compile(r"^```([^\s`]*)[^\n]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
# Fence info strings that name a LANGUAGE rather than a file. A member that
# writes ```python instead of ```review_rules.py has submitted a perfectly good
# file with a label our parser misread - and that failed a task on 2026-09-20.
# When exactly one output file is expected, the language tag is harmless.
LANG_TAGS = {"", "md", "markdown", "json", "text", "txt", "python", "py",
             "python3", "pycon", "console", "shell", "bash", "sh", "zsh",
             "powershell", "ps1", "cmd", "bat", "ini", "cfg", "conf", "toml",
             "yaml", "yml", "xml", "html", "css", "js", "javascript", "ts",
             "typescript", "diff", "patch", "sql", "csv", "tsv", "gdscript",
             "c", "cpp", "rust", "go", "java", "kotlin", "swift", "rb", "php"}
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
   It may also carry "note": one short finding from what you read last. Old results get trimmed; your notes stay.
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
- fetch_url(url, start=1, lines=120, pattern="")  (a web page as numbered lines; page with start, or give a regex pattern to list only matching lines){fetch_note}{lsp_tools}{ask_tool}
Relative paths resolve against the first read root.

BUDGET: {max_requests} replies in total for this task, tool calls and submissions included. Submit before you run out.

PLAYBOOK for {task_type} (rules learned from earlier runs; follow every one):
{playbook}
"""


_CODE_START = ("export ", "import ", "const ", "let ", "function ", "async function ",
               "//", "/*", '"""', "from ", "def ", "class ", "#", '"use strict"',
               "'use strict'")


def _single_file_body(text: str, file_blocks: list, expected: List[str]):
    """The file, when a one-file task's answer is plainly that file but misses SUBMIT.

    splat-single-file 2026-09-21: Nemotron answered three attempts with the file
    name on a line and then a ```javascript block, or with bare code, and all three
    were thrown away as "invalid" without being judged. Being lenient here is safe:
    whatever is taken still has to pass every gate, the hidden tests included.
    """
    if len(expected) != 1:
        return None
    if len(file_blocks) == 1:
        return file_blocks[0][1].rstrip() + "\n"
    if file_blocks:
        return None
    lines = text.splitlines()
    if lines and lines[0].strip().strip("`*: ") == expected[0]:
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return body + "\n" if body.startswith(_CODE_START) else None


def blind_call(text: str) -> Optional[Tuple[str, dict]]:
    """The tool call, when a reply makes one and THEN writes its files anyway.

    atlas study 2026-10-26: Gordon twice wrote a fetch_url call, an imagined
    "Tool result" for it and a whole digest in one reply. The files came first in
    our parser, so a page nobody fetched was graded (the citation gate caught it).
    Files written after a call cannot have seen its result: run the call instead.
    """
    text = (text or "").strip()
    call = _find_tool_json_at(text)
    if call is None:
        return None
    at = call[0]
    obj, _ = json.JSONDecoder().raw_decode(text[at:])
    if "tool" not in obj and not ({"args", "arguments"} & obj.keys()):
        return None          # {"name": ...} alone is prose, not a call
    starts = [m.start() for m in re.finditer(r"^\s*SUBMIT\b", text, re.MULTILINE)]
    starts += [m.start() for m in FENCE.finditer(text) if not m.start(2) <= at < m.end(2)]
    if not starts or at > min(starts):
        return None
    return call[1], call[2]


def parse_reply(text: str, expected_files: List[str]) -> Tuple[str, object, object]:
    """-> ("submit", files, notes) | ("tool", name, args) | ("invalid", reason, None)"""
    text = (text or "").strip()
    blind = blind_call(text)
    if blind:
        return "tool", blind[0], blind[1]
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
    only = _single_file_body(text, file_blocks, expected_files)
    if only is not None:
        return "submit", {expected_files[0]: only}, []
    return "invalid", ("reply was neither one JSON tool call nor SUBMIT with "
                       "fenced file blocks"), None


def _find_tool_json(text: str) -> Optional[Tuple[str, dict]]:
    call = _find_tool_json_at(text)
    return (call[1], call[2]) if call else None


def _find_tool_json_at(text: str) -> Optional[Tuple[int, str, dict]]:
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
            return m.start(), name, {k: v for k, v in args.items() if k != "note"}
    return None


def call_note(text: str) -> Optional[str]:
    """The finding a member put on its tool call ("note" beside or inside "args")."""
    call = _find_tool_json_at(text or "")
    if call is None:
        return None
    obj, _ = json.JSONDecoder().raw_decode(text[call[0]:])
    args = obj.get("args", obj.get("arguments"))
    note = obj.get("note", args.get("note") if isinstance(args, dict) else None)
    return compact.clean_note(note)


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


def _thinking_cut_off(res: dict) -> bool:
    """True when the provider stopped at the length limit before any answer.

    The client falls back to the reasoning text when content is empty, so the
    reply looks non-empty; only the raw message shows nothing was answered.
    """
    try:
        choice = res["raw"]["choices"][0]
    except (KeyError, IndexError, TypeError):
        return False
    message = choice.get("message") or {}
    return (choice.get("finish_reason") == "length"
            and not str(message.get("content") or "").strip())


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
                   "fetch_url": {"url", "start", "lines", "pattern"}}[name]
        return name, {k: v for k, v in mapped.items() if k in allowed}
    return None


CHARS_PER_TOKEN = 3.5


def _trim_old_results(messages: List[dict], context_tokens: Optional[int] = None) -> None:
    """Shorten old tool results so the prompt stays small.

    Without a context budget: keep the newest KEEP_FULL_RESULTS in full (the
    rule until 2026-09-25). With one (personnel.json context_ceiling of the
    member's window): keep as many of the newest results in full as fit under
    it, oldest trimmed first, never fewer than KEEP_FULL_RESULTS. A 1M-window
    member re-reading a file it was shown three turns ago was our trimming,
    not its memory."""
    results = [m for m in messages if m.get("_result")]
    total = sum(len(m["content"]) for m in messages)
    limit = int(context_tokens * CHARS_PER_TOKEN) if context_tokens else 0
    for m in results[:-KEEP_FULL_RESULTS]:
        if context_tokens and total <= limit:
            break
        if not m.get("_trimmed") and len(m["content"]) > TRIMMED_CHARS:
            before = len(m["content"])
            m["content"] = _trimmed(m)
            m["_trimmed"] = True
            total -= before - len(m["content"])


def _trimmed(m: dict) -> str:
    """The stub an old result leaves; it names the call so the member can re-read a part.
    The budget line that led the message is dropped with the rest (it is out of date)."""
    if m.get("_call"):
        return compact.stub(m["_call"][0], m["_call"][1], m.get("_body", m["content"]),
                            TRIMMED_CHARS)
    return (m["content"][:TRIMMED_CHARS]
            + "\n...[older result trimmed; call the tool again if you need it]")


ASK_TOOL = """
- ask(question, options=[])  (ONE question per job, only when you cannot see how to go on; 0 or 2-4 short options; the job pauses until it is answered)"""

LSP_TOOLS = """
- symbols(path)  (a language server's outline of a code file: classes, functions, methods with line numbers)
- definition(path, name)  (where the symbol `name`, as used in that file, is defined)
- references(path, name)  (every use of the symbol `name` found in that file)
- diagnostics(path)  (a linter's errors and warnings for a code file)"""


def run_member(*, persona: str, task_type: str, playbook: str, task_text: str,
               expected_files: List[str], toolbox, grade: Callable[[Dict[str, str]], List[dict]],
               chat: Callable[[List[dict], int], dict], max_requests: int,
               max_tokens: int, fetch_enabled: bool,
               log: Callable[[dict], None] = lambda e: None,
               context_tokens: Optional[int] = None, addenda: str = "",
               leash: Optional[dict] = None, can_ask: bool = False) -> dict:
    leash = leash or {}
    max_repeats = int(leash.get("max_repeats", MAX_REPEATS))
    max_invalid = int(leash.get("max_invalid_in_a_row", MAX_INVALID_IN_A_ROW))
    max_empty = int(leash.get("max_empty", MAX_EMPTY))
    system = SYSTEM_TEMPLATE.format(
        persona=persona, task_type=task_type, playbook=playbook.strip(),
        max_requests=max_requests, example_file=expected_files[0],
        fetch_note="" if fetch_enabled else "  (disabled for this task)",
        lsp_tools=LSP_TOOLS if getattr(toolbox, "lsp", None) else "",
        ask_tool=ASK_TOOL if can_ask else "") + addenda
    messages: List[dict] = [{"role": "system", "content": system},
                            {"role": "user", "content": task_text}]
    tracker = AttemptTracker()
    calls: Counter = Counter()
    repeats = invalid_run = requests = tokens = empties = natives = 0
    truncations = 0
    stop_reason = None
    submissions = 0
    last_tokens = 0
    findings: List[str] = []     # the member's notes, kept for a re-run (compact.py)
    question: Optional[dict] = None
    hinted = not can_ask         # the ask hint is offered once, and only where ask exists

    while True:
        # The budget line leads the message it belongs to; empty until it matters.
        newest = messages[-1]
        if requests and newest["role"] == "user" and not newest.get("_led"):
            line, _last = compact.budget_line(tokens, max_tokens, last_tokens,
                                              max_requests - requests)
            newest["_body"] = newest["content"]
            newest["content"] = compact.lead_with(line, newest["content"])
            newest["_led"] = True
        if requests >= max_requests:
            stop_reason = stop_reason or "budget_requests"
            break
        if tokens >= max_tokens:
            stop_reason = "budget_tokens"
            break
        _trim_old_results(messages, context_tokens)
        wire = [{"role": m["role"], "content": m["content"]} for m in messages]
        res = chat(wire, requests)
        requests += 1
        usage = (res.get("raw") or {}).get("usage") or {}
        last_tokens = usage.get("total_tokens", 0) or 0
        tokens += last_tokens
        reply = res.get("content") or ""
        left = max_requests - requests
        if _thinking_cut_off(res):
            # The provider stopped the member mid-thought: no answer arrived, and
            # the client's fallback put the reasoning where the answer goes.
            # Judging that as a file would blame the member for our ceiling.
            truncations += 1
            log({"event": "reply", "n": requests, "kind": "thinking_cut_off",
                 "tokens": usage.get("total_tokens", 0),
                 "reasoning_chars": len(res.get("reasoning") or "")})
            if truncations >= MAX_TRUNCATIONS:
                stop_reason = "output_truncated"
                break
            # A placeholder keeps the turns alternating without replaying the
            # half-finished reasoning back to the member.
            messages.append({"role": "assistant",
                             "content": "(cut off while thinking - no answer)"})
            messages.append({"role": "user", "content":
                             "YOU RAN OUT OF ROOM WHILE THINKING: the reply limit "
                             "was reached before any answer. Think less; decide, "
                             "then SUBMIT the file straight away. "
                             f"({left} replies left)"})
            continue
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
            if empties >= max_empty:
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
            if invalid_run >= max_invalid:
                stop_reason = "contract_abandoned"
                break
            messages.append({"role": "user", "content":
                             f"INVALID REPLY: {a}. Reply with ONE JSON tool call "
                             f"or SUBMIT + fenced file blocks. ({left} replies left)"})
            continue
        invalid_run = 0

        if kind == "tool":
            if compact.add_note(findings, call_note(reply)):
                log({"event": "note", "note": findings[-1]})
            if a == "ask" and can_ask:
                question, err = asking.parse_question(b)
                if question:
                    log({"event": "question", **question})
                    stop_reason = "question"
                    break
                messages.append({"role": "user", "content":
                                 f"TOOL ERROR {err} ({left} replies left)"})
                continue
            key = json.dumps([a, b], sort_keys=True)
            calls[key] += 1
            if calls[key] > 1:
                repeats += 1
                log({"event": "repeat", "call": key})
                if repeats >= max_repeats:
                    stop_reason = "loop_repeat"
                    break
                hint = "" if hinted else "\n" + asking.stuck_hint(False)
                hinted = True
                messages.append({"role": "user", "content":
                                 f"REPEATED CALL {a}: you already have that result "
                                 f"above. Take a different step or SUBMIT. "
                                 f"({left} replies left){hint}"})
                continue
            try:
                out = toolbox.call(a, b)
                content = f"RESULT {a}({json.dumps(b)}) [{left} replies left]:\n{out}"
            except ToolError as e:
                content = f"TOOL ERROR {a}: {e} [{left} replies left]"
            except OSError as e:
                content = f"TOOL ERROR {a}: {type(e).__name__}: {e} [{left} replies left]"
            if blind_call(reply):
                content += ("\nNOTE: your reply went on past the tool call (a result you "
                            "imagined, files). That part was discarded: files written "
                            "before a result arrives cannot use it. One tool call per "
                            "reply; SUBMIT once you have read the real result above.")
                log({"event": "blind_files_discarded", "tool": a})
            log({"event": "tool", "tool": a, "args": b, "result_chars": len(content)})
            messages.append({"role": "user", "content": content, "_result": True,
                             "_call": (a, b)})
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
        hint = ""
        if submissions >= 2 and not hinted:      # failing again: offer the way out, once
            hint, hinted = "\n" + asking.stuck_hint(False), True
        messages.append({"role": "user", "content":
                         f"SUBMISSION FAILED THESE CHECKS:\n{failed}\n"
                         f"Fix only these. You may use tools, then SUBMIT the "
                         f"complete file(s) again. ({left} replies left){hint}"})

    best = tracker.best
    return {"stop_reason": stop_reason, "requests": requests, "tokens": tokens,
            "question": question, "findings": findings,
            "submissions": submissions, "repeats": repeats, "empty_replies": empties,
            "native_tool_calls": natives,
            "passed": bool(best and best["passed"]),
            "files": best["files"] if best else {},
            "steps": best["steps"] if best else [],
            "notes": (best or {}).get("notes", []) if best else [],
            "evidence": toolbox.evidence.keys(),
            **({"tracker": tracker.summary()} if best else {})}
