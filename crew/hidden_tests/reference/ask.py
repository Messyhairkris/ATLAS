"""Reference for ask.py: a stuck crew member asks one question (PA-written)."""

import re

QUESTION_MAX_CHARS = 400
OPTION_MAX_CHARS = 80
USAGE = ('ask needs {"question": "...", "options": ["...", "..."]} - options are optional: '
         'none, or 2 to 4')
HINT = ('STUCK? If you cannot tell how to get past this, ask ONE question instead of repeating '
        'yourself: {"tool": "ask", "args": {"question": "...", "options": ["...", "..."]}}. '
        'The job pauses until it is answered.')

_NUMBER = re.compile(r"^([0-9]+)\.?$")


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_question(args: object) -> tuple[dict | None, str]:
    """The member's question, cleaned, or None and what was wrong with it."""
    if not isinstance(args, dict) or not isinstance(args.get("question"), str):
        return None, USAGE
    question = _clean(args["question"])
    if not question:
        return None, "ask: the question is empty"
    if len(question) > QUESTION_MAX_CHARS:
        return None, f"ask: keep the question to at most {QUESTION_MAX_CHARS} characters"
    raw = args.get("options")
    raw = [] if raw is None else raw
    if not isinstance(raw, list):
        return None, USAGE
    options = []
    for item in raw:
        if not isinstance(item, str):
            return None, USAGE
        option = _clean(item)
        if not option:
            return None, "ask: an option is empty"
        if len(option) > OPTION_MAX_CHARS:
            return None, f"ask: keep each option to at most {OPTION_MAX_CHARS} characters"
        options.append(option)
    if len(options) == 1 or len(options) > 4:
        return None, "ask: give 2 to 4 options, or none"
    if len({o.lower() for o in options}) < len(options):
        return None, "ask: two options are the same"
    return {"question": question, "options": options}, ""


def pick_answer(question: dict, reply: str) -> str:
    """The option a numbered reply names, or the reply itself."""
    answer = reply.strip()
    match = _NUMBER.match(answer)
    if match and 1 <= int(match.group(1)) <= len(question["options"]):
        return question["options"][int(match.group(1)) - 1]
    return answer


def answer_constraint(question: dict, answer: str) -> str:
    """The text a re-run job is given with the answer to its question."""
    lines = ["ANSWER TO YOUR QUESTION", f"You asked: {question['question']}"]
    if question["options"]:
        lines.append("Options were: " + " | ".join(question["options"]))
    lines.append(f"Answer: {pick_answer(question, answer)}")
    lines.append("Carry on with this answer. Do not ask the same question again.")
    return "\n".join(lines)


def stuck_hint(asked: bool) -> str:
    """The hint offered to a member that is repeating itself, once per job."""
    return "" if asked else HINT
