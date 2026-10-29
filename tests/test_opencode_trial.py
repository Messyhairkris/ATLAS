"""crew/runners/opencode_trial.py: the crew's OpenCode jobs.

Kris's ruling, 2026-10-29: where a member would reach for the shell, the brief says to use the
built-in tools. It is not a permission change - it is the rule the 104 refusals of `ls -la` and
`python <file>` in these jobs asked for (found by crew/runners/mine_failures.py on its first run).

The prompts are `str.format` templates, so a stray brace in the rule would break every job that
uses them - that is tested too.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "crew" / "runners" / "opencode_trial.py"


def _module():
    """The module, or None when this machine cannot resolve an opencode.exe (it raises)."""
    try:
        spec = importlib.util.spec_from_file_location("opencode_trial", TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except SystemExit:
        return None


mod = _module()
PROMPTS_TEXT = TOOL.read_text(encoding="utf-8")


def test_every_prompt_says_to_use_the_built_in_tools():
    assert PROMPTS_TEXT.count("USE THE BUILT-IN TOOLS") == 2, "both prompts, module and rescue"


def test_the_prompts_name_the_shell_as_powershell():
    # measured from the engine binary: `powershell -NoProfile -ExecutionPolicy Bypass -Command`,
    # so cmd.exe and Unix syntax can never work in it
    assert PROMPTS_TEXT.count("Windows PowerShell") == 2


def test_the_prompts_forbid_pipes_ampersand_and_redirection():
    assert "no `&`, no redirection" in PROMPTS_TEXT


def test_the_prompts_say_not_to_retry_a_refused_command():
    assert "do not try another form of it" in PROMPTS_TEXT.lower() or \
        "do not try another form of it" in PROMPTS_TEXT
    assert PROMPTS_TEXT.count("try another form of it") == 2


def test_the_prompts_still_format():
    # a rule with a brace in it would raise here, and every job using these prompts with it
    if mod is None:
        return
    assert "{module}" in mod.PROMPT and "{module}" in mod.RESCUE_PROMPT
    mod.PROMPT.format(module="m.py")
    mod.RESCUE_PROMPT.format(module="m.py", failures="grader output")


def test_the_formatter_stays_off():
    # the formatter week's lesson: a formatter rewriting files between a read and an edit is what
    # caused the stale_edit failures in the catalogue
    if mod is None:
        return
    assert mod.opencode_config("m", 1000, 1000)["formatter"] is False
