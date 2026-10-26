"""A stuck crew member asks ONE question; the pure logic (contract: crew/contracts/ask.md).

Written by Nemotron in campaign atlas-compact-ask (2026-10-26); pick_answer fixed in
review to read ASCII digits only.
"""

QUESTION_MAX_CHARS = 400
OPTION_MAX_CHARS = 80
USAGE = 'ask needs {"question": "...", "options": ["...", "..."]} - options are optional: none, or 2 to 4'
HINT = ('STUCK? If you cannot tell how to get past this, ask ONE question instead of repeating '
        'yourself: {"tool": "ask", "args": {"question": "...", "options": ["...", "..."]}}. '
        'The job pauses until it is answered.')


def _clean(s: str) -> str:
    return " ".join(s.split())


def parse_question(args: object) -> tuple[dict | None, str]:
    if not isinstance(args, dict):
        return None, USAGE
    question = args.get("question")
    if not isinstance(question, str):
        return None, USAGE
    cleaned_question = _clean(question)
    if not cleaned_question:
        return None, "ask: the question is empty"
    if len(cleaned_question) > QUESTION_MAX_CHARS:
        return None, "ask: keep the question to at most 400 characters"
    options = args.get("options")
    if options is None:
        options = []
    if not isinstance(options, list):
        return None, USAGE
    cleaned_options = []
    for opt in options:
        if not isinstance(opt, str):
            return None, USAGE
        cleaned_opt = _clean(opt)
        if not cleaned_opt:
            return None, "ask: an option is empty"
        if len(cleaned_opt) > OPTION_MAX_CHARS:
            return None, "ask: keep each option to at most 80 characters"
        cleaned_options.append(cleaned_opt)
    if len(cleaned_options) == 1 or len(cleaned_options) > 4:
        return None, "ask: give 2 to 4 options, or none"
    lower_opts = [opt.lower() for opt in cleaned_options]
    if len(lower_opts) != len(set(lower_opts)):
        return None, "ask: two options are the same"
    return {"question": cleaned_question, "options": cleaned_options}, ""


def pick_answer(question: dict, reply: str) -> str:
    r = reply.strip()
    num_str = r[:-1] if r.endswith(".") else r
    # ASCII digits only: str.isdigit() is True for a superscript two, which int() refuses
    if num_str.isascii() and num_str.isdigit():
        n = int(num_str)
        if 1 <= n <= len(question["options"]):
            return question["options"][n - 1]
    return r


def answer_constraint(question: dict, answer: str) -> str:
    lines = [
        "ANSWER TO YOUR QUESTION",
        f"You asked: {question['question']}",
    ]
    if question["options"]:
        lines.append(f"Options were: {' | '.join(question['options'])}")
    lines.append(f"Answer: {pick_answer(question, answer)}")
    lines.append("Carry on with this answer. Do not ask the same question again.")
    return "\n".join(lines)


def stuck_hint(asked: bool) -> str:
    if asked:
        return ""
    return HINT
