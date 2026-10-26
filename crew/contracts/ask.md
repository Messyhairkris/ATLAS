# Contract: ask.py - a stuck crew member asks one question

Part of the crew harness itself. A crew member that cannot see how to get past a check tends to
repeat itself until the job stops (2026-10-26 record: 66 runs ended stuck - an unchanged
resubmission, no progress across submissions, or the same tool call again). From now on it may
ask ONE question instead. The harness pauses the job; the PA or Kris answers; the job runs again
with the answer. This module is the pure logic: checking the question the member wrote, turning
an answer into the text the re-run is given, and the one-line hint offered when a member is
repeating itself. Pure text in, text out. No I/O.

## Public API

```python
QUESTION_MAX_CHARS = 400
OPTION_MAX_CHARS = 80
USAGE = 'ask needs {"question": "...", "options": ["...", "..."]} - options are optional: none, or 2 to 4'
HINT = ('STUCK? If you cannot tell how to get past this, ask ONE question instead of repeating '
        'yourself: {"tool": "ask", "args": {"question": "...", "options": ["...", "..."]}}. '
        'The job pauses until it is answered.')

def parse_question(args: object) -> tuple[dict | None, str]: ...
def pick_answer(question: dict, reply: str) -> str: ...
def answer_constraint(question: dict, answer: str) -> str: ...
def stuck_hint(asked: bool) -> str: ...
```

Allowed imports: none needed (`re` is allowed if you want it). Spell every name exactly as above;
copy USAGE and HINT character for character.

"Clean" below means: replace every run of whitespace with one space and strip both ends
(`" ".join(s.split())`).

## parse_question(args)

Returns `(question, "")` when the question is good, or `(None, message)` when it is not.
Rules, in order; the first that fails decides the message:

1. `args` is not a `dict` -> `(None, USAGE)`.
2. `args.get("question")` is not a `str` -> `(None, USAGE)`.
3. The cleaned question is empty -> `(None, "ask: the question is empty")`.
4. The cleaned question is longer than `QUESTION_MAX_CHARS` ->
   `(None, "ask: keep the question to at most 400 characters")`.
5. `options = args.get("options")`; `None` (or the key missing) means `[]`. Not a `list` ->
   `(None, USAGE)`.
6. Walk the options in order. One that is not a `str` -> `(None, USAGE)`. One that is empty once
   cleaned -> `(None, "ask: an option is empty")`. One longer than `OPTION_MAX_CHARS` once cleaned
   -> `(None, "ask: keep each option to at most 80 characters")`.
7. Exactly 1 option, or more than 4 -> `(None, "ask: give 2 to 4 options, or none")`.
8. Two options equal when compared lower-cased -> `(None, "ask: two options are the same")`.
9. Otherwise `({"question": <cleaned question>, "options": [<cleaned options, in order>]}, "")`.
   Extra keys in `args` are ignored.

## pick_answer(question, reply)

The answer may be the option's number. `r = reply.strip()`.

1. `r` is one or more ASCII digits `0-9` (not `"²"` or other Unicode digits), optionally
   followed by one `.` (for example `"2"` or `"2."`), and
   that number `n` satisfies `1 <= n <= len(question["options"])` -> `question["options"][n - 1]`.
2. Otherwise `r`.

## answer_constraint(question, answer)

The text the re-run is given. Lines joined with `"\n"`:

1. `"ANSWER TO YOUR QUESTION"`
2. `"You asked: " + question["question"]`
3. only when there are options: `"Options were: " + " | ".join(question["options"])`
4. `"Answer: " + pick_answer(question, answer)`
5. `"Carry on with this answer. Do not ask the same question again."`

## stuck_hint(asked)

1. `asked` is truthy -> `""` (one question per job; do not offer another).
2. Otherwise `HINT`.

## Worked examples (the hidden tests walk every row)

| call | result |
|---|---|
| `parse_question("why?")` | `(None, USAGE)` |
| `parse_question({"question": 3})` | `(None, USAGE)` |
| `parse_question({"question": "  \n "})` | `(None, "ask: the question is empty")` |
| `parse_question({"question": "q" * 401})` | `(None, "ask: keep the question to at most 400 characters")` |
| `parse_question({"question": "Which file?", "options": "a.md"})` | `(None, USAGE)` |
| `parse_question({"question": "Which?", "options": ["a", 2]})` | `(None, USAGE)` |
| `parse_question({"question": "Which?", "options": ["a", " "]})` | `(None, "ask: an option is empty")` |
| `parse_question({"question": "Which?", "options": ["a", "b" * 81]})` | `(None, "ask: keep each option to at most 80 characters")` |
| `parse_question({"question": "Which?", "options": ["only"]})` | `(None, "ask: give 2 to 4 options, or none")` |
| `parse_question({"question": "Which?", "options": ["a", "b", "c", "d", "e"]})` | `(None, "ask: give 2 to 4 options, or none")` |
| `parse_question({"question": "Which?", "options": ["Yes", "yes "]})` | `(None, "ask: two options are the same")` |
| `parse_question({"question": " Which\n file? ", "options": [" a.md ", "b.md"]})` | `({"question": "Which file?", "options": ["a.md", "b.md"]}, "")` |
| `parse_question({"question": "Why?"})` | `({"question": "Why?", "options": []}, "")` |
| `parse_question({"question": "Why?", "options": None, "x": 1})` | `({"question": "Why?", "options": []}, "")` |
| `pick_answer({"question": "Q", "options": ["a.md", "b.md"]}, " 2 ")` | `"b.md"` |
| `pick_answer({"question": "Q", "options": ["a.md", "b.md"]}, "1.")` | `"a.md"` |
| `pick_answer({"question": "Q", "options": ["a.md", "b.md"]}, "3")` | `"3"` |
| `pick_answer({"question": "Q", "options": []}, " use the README ")` | `"use the README"` |
| `answer_constraint({"question": "Which file?", "options": ["a.md", "b.md"]}, "2")` | `"ANSWER TO YOUR QUESTION\nYou asked: Which file?\nOptions were: a.md \| b.md\nAnswer: b.md\nCarry on with this answer. Do not ask the same question again."` |
| `answer_constraint({"question": "Why?", "options": []}, "because")` | `"ANSWER TO YOUR QUESTION\nYou asked: Why?\nAnswer: because\nCarry on with this answer. Do not ask the same question again."` |
| `stuck_hint(False)` | `HINT` |
| `stuck_hint(True)` | `""` |

(In the table, `\|` is a literal `|` escaped for the table.)
