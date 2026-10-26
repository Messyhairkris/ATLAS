# Contract: compact.py - a long job keeps what it found

Part of the crew harness itself. A crew member works through a job in replies; every reply
re-sends the whole conversation, so old tool results are trimmed to keep the prompt small, and a
job ends when its token budget is spent. Two things went wrong (2026-10-26 record: 33 runs ended
on the token budget, many with nothing submitted):

- a trimmed result took what the member had learned from it with it;
- nothing warned the member before the budget ran out, so it never got a last chance to SUBMIT.

This module is the pure logic for both: the member's NOTES (short findings it adds to its own tool
calls as it goes; they stay in its own replies, which are never trimmed, and are shown ONCE as a
block when a job is re-run), the stub left where a result was trimmed, and the budget line.
Nothing here is sent on every reply: Kris's rule is that per-call additions bloat every request,
so each piece of text below appears only when it carries something new.
Pure text in, text out. No I/O, no clock, no globals that change.

## Public API

```python
NOTE_MAX_CHARS = 300
NOTES_MAX_CHARS = 3000
WARN_AT = 0.75
NOTES_HEADER = "YOUR NOTES FROM THE EARLIER RUN (you wrote these; do not redo that work):"

def clean_note(text: object) -> str | None: ...
def add_note(notes: list[str], text: object) -> bool: ...
def render_notes(notes: list[str], max_chars: int = NOTES_MAX_CHARS) -> str: ...
def stub(tool: str, args: dict, content: str, keep_chars: int = 400) -> str: ...
def budget_line(tokens_used: int, max_tokens: int, last_request_tokens: int,
                requests_left: int) -> tuple[str, bool]: ...
def lead_with(line: str, content: str) -> str: ...
```

Allowed imports: `json`. Nothing else. Spell every name exactly as above.

## clean_note(text)

Rules, in order; the first that applies decides:

1. `text` is not a `str` -> `None`.
2. Replace every run of whitespace (spaces, tabs, newlines; regex `\s+`) with ONE space, then
   strip both ends. (Without `re`: `" ".join(text.split())` does exactly this.)
3. The result is empty -> `None`.
4. Longer than `NOTE_MAX_CHARS` characters -> its first `NOTE_MAX_CHARS - 3` characters,
   right-stripped, followed by `"..."`.
5. Otherwise the cleaned text.

## add_note(notes, text)

1. `n = clean_note(text)`; if `n` is `None` -> return `False`, `notes` unchanged.
2. `n` is already in `notes` (exact match) -> return `False`, `notes` unchanged.
3. Append `n` to `notes` (mutate the list given) and return `True`.

## render_notes(notes, max_chars=NOTES_MAX_CHARS)

The block a re-run job is given ONCE, in its task text.

1. Empty `notes` -> `""`.
2. Each note becomes the line `"- " + note`.
3. Keep the NEWEST lines that fit: start from the last line and walk backwards, keeping a line
   while the kept lines joined with `"\n"` stay at most `max_chars` long. The newest line is
   always kept, even when it alone is longer. Stop at the first line that does not fit (the kept
   lines are always a run of the newest ones, in their original order).
4. `dropped` = number of lines not kept.
5. Result: `NOTES_HEADER`, then - only when `dropped > 0` - a newline and
   `"(1 older note folded away)"` or `"(N older notes folded away)"`, then a newline and the
   kept lines joined with `"\n"`.

## stub(tool, args, content, keep_chars=400)

What an old tool result becomes when it is trimmed.

1. `len(content) <= keep_chars` -> `content` unchanged.
2. `call` = `tool + "(" + json.dumps(args, sort_keys=True) + ")"`.
3. Result: the first `keep_chars` characters of `content`, then
   `"\n...[trimmed: " + call + " gave " + str(len(content)) + " chars; call it again to re-read a part]"`

## budget_line(tokens_used, max_tokens, last_request_tokens, requests_left)

The line the harness puts at the TOP of the next message to the member (a warning at the end of a
long tool result is ignored - Kris saw exactly that with his own compaction hook). Returns
`(line, last)`; `last` is `True` when this must be the member's final reply.

`pct` = `0` when `max_tokens <= 0`, otherwise `min(100, (100 * tokens_used) // max_tokens)`
(integer floor division).

Rules, in order; the first that applies decides:

1. `requests_left <= 1` ->
   `("LAST REPLY: this is your last reply. SUBMIT your best complete file(s) now; a tool call here is wasted.", True)`
2. `max_tokens > 0` and `tokens_used + last_request_tokens >= max_tokens` ->
   `(f"LAST REPLY: {pct}% of this job's token budget is spent and one more reply this size would use the rest. SUBMIT your best complete file(s) now; a tool call here is wasted.", True)`
3. `max_tokens > 0` and `tokens_used >= WARN_AT * max_tokens` ->
   `(f"TOKENS: {pct}% of this job's token budget is spent. Note what you still need and SUBMIT soon.", False)`
4. Otherwise `("", False)`.

## lead_with(line, content)

1. `line` is `""` -> `content` unchanged.
2. Otherwise `line + "\n\n" + content`.

## Worked examples (the hidden tests walk every row)

| call | result |
|---|---|
| `clean_note(42)` | `None` |
| `clean_note("  a\n\tb   c ")` | `"a b c"` |
| `clean_note(" \n ")` | `None` |
| `clean_note("x" * 301)` | `"x" * 297 + "..."` |
| `clean_note("x" * 300)` | `"x" * 300` |
| `clean_note("abc " * 100)` | cleaned is `"abc abc ... abc"` (399 chars); first 297 chars end in `"abc a"`, so `("abc " * 74) + "a..."` |
| `add_note(["a"], "a")` | `False`, list stays `["a"]` |
| `add_note(["a"], " b ")` | `True`, list becomes `["a", "b"]` |
| `add_note([], None)` | `False` |
| `render_notes([])` | `""` |
| `render_notes(["a", "b"])` | `NOTES_HEADER + "\n- a\n- b"` |
| `render_notes(["aaaa", "bbbb", "cccc"], 13)` | `NOTES_HEADER + "\n(1 older note folded away)\n- bbbb\n- cccc"` |
| `render_notes(["aaaa", "bbbb", "cccc"], 6)` | `NOTES_HEADER + "\n(2 older notes folded away)\n- cccc"` |
| `render_notes(["a" * 50], 10)` | `NOTES_HEADER + "\n- " + "a" * 50` |
| `stub("read_file", {"path": "x.md"}, "short", 400)` | `"short"` |
| `stub("read_file", {"start": 5, "path": "x.md"}, "abcdefghij", 4)` | `"abcd\n...[trimmed: read_file({\"path\": \"x.md\", \"start\": 5}) gave 10 chars; call it again to re-read a part]"` |
| `budget_line(1000, 10000, 500, 5)` | `("", False)` |
| `budget_line(7400, 10000, 500, 5)` | `("", False)` |
| `budget_line(7500, 10000, 500, 5)` | `("TOKENS: 75% of this job's token budget is spent. Note what you still need and SUBMIT soon.", False)` |
| `budget_line(8999, 10000, 1000, 5)` | `("TOKENS: 89% ...", False)` |
| `budget_line(9000, 10000, 1000, 5)` | `("LAST REPLY: 90% of this job's token budget is spent and one more reply ...", True)` |
| `budget_line(12000, 10000, 10, 3)` | `("LAST REPLY: 100% ...", True)` |
| `budget_line(100, 10000, 50, 1)` | `("LAST REPLY: this is your last reply. ...", True)` |
| `budget_line(5000, 0, 9999, 5)` | `("", False)` |
| `lead_with("", "body")` | `"body"` |
| `lead_with("TOKENS: 80%", "body")` | `"TOKENS: 80%\n\nbody"` |
