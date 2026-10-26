"""crew/rules.py: rules with triggers (Kris 2026-10-24) - one folder of rules for
every PA runtime, each rule with a trigger that says when it applies. Rendered ONCE -
into a PA's brief at session start and into a crew job's system prompt at job start -
never added to every reply."""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import pa_brief, rules  # noqa: E402


@pytest.fixture
def tmp_path():
    """pytest's built-in tmp_path needs the shared pytest-of-* base temp dir, which is
    unreadable on this box (WinError 5, 2026-10-26); mkdtemp makes a fresh dir instead
    (the way tests/test_pa_handoff.py does it)."""
    path = Path(tempfile.mkdtemp(prefix="rules-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def write_rule(folder: Path, name: str, text: str) -> Path:
    path = folder / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def make(name, trigger, description="", globs=None, body="B"):
    return {
        "name": name,
        "trigger": trigger,
        "description": description,
        "globs": globs or [],
        "body": body,
    }


# --- parse_rule ---


def test_parse_rule_reads_every_key(tmp_path):
    text = (
        "---\n"
        "name: powershell-not-bash\n"
        "trigger: always_on\n"
        "description: Windows 10 - PowerShell is the shell; Unix habits break commands\n"
        'globs: "*.ps1, crew/**/*.py"\n'
        "---\n"
        "\n"
        "Body text, markdown.\n"
        "Second line.\n"
        "\n"
    )
    rule = rules.parse_rule(text, "whatever-stem")
    assert rule == {
        "name": "powershell-not-bash",
        "trigger": "always_on",
        "description": "Windows 10 - PowerShell is the shell; Unix habits break commands",
        "globs": ["*.ps1", "crew/**/*.py"],
        "body": "Body text, markdown.\nSecond line.",
    }


def test_parse_rule_name_defaults_to_the_file_stem(tmp_path):
    text = "---\ntrigger: always_on\ndescription: d\n---\nbody\n"
    assert rules.parse_rule(text, "the-stem")["name"] == "the-stem"


def test_parse_rule_quoted_globs_string(tmp_path):
    text = '---\nname: a\ntrigger: glob\ndescription: d\nglobs: "*.ps1, crew/**/*.py"\n---\nbody\n'
    assert rules.parse_rule(text, "a")["globs"] == ["*.ps1", "crew/**/*.py"]


def test_parse_rule_plain_globs_string(tmp_path):
    text = "---\nname: a\ntrigger: glob\ndescription: d\nglobs: *.ahk, **/*.ahk\n---\nbody\n"
    assert rules.parse_rule(text, "a")["globs"] == ["*.ahk", "**/*.ahk"]


def test_parse_rule_yaml_list_globs(tmp_path):
    text = "---\nname: a\ntrigger: glob\ndescription: d\nglobs: [a.py, b/?.py]\n---\nbody\n"
    assert rules.parse_rule(text, "a")["globs"] == ["a.py", "b/?.py"]


def test_parse_rule_none_without_frontmatter(tmp_path):
    assert rules.parse_rule("Body only, no frontmatter.\n", "x") is None
    assert rules.parse_rule("", "x") is None


def test_parse_rule_none_when_the_frontmatter_never_closes(tmp_path):
    assert (
        rules.parse_rule("---\nname: x\ntrigger: always_on\nbody never closed", "x")
        is None
    )


def test_parse_rule_none_for_an_unknown_or_missing_trigger(tmp_path):
    assert (
        rules.parse_rule(
            "---\nname: x\ntrigger: sometimes\ndescription: d\n---\nbody\n", "x"
        )
        is None
    )
    assert rules.parse_rule("---\nname: x\ndescription: d\n---\nbody\n", "x") is None


def test_parse_rule_none_for_model_decision_without_description(tmp_path):
    assert (
        rules.parse_rule("---\nname: x\ntrigger: model_decision\n---\nbody\n", "x")
        is None
    )


def test_parse_rule_none_for_glob_without_globs(tmp_path):
    assert (
        rules.parse_rule(
            "---\nname: x\ntrigger: glob\ndescription: d\n---\nbody\n", "x"
        )
        is None
    )
    assert (
        rules.parse_rule(
            '---\nname: x\ntrigger: glob\ndescription: d\nglobs: ""\n---\nbody\n', "x"
        )
        is None
    )


# --- load_rules ---


def test_load_rules_reads_every_md_sorted_and_skips_unparseable(tmp_path):
    write_rule(
        tmp_path,
        "b-second",
        "---\nname: b\ntrigger: always_on\ndescription: d\n---\nB body\n",
    )
    write_rule(
        tmp_path,
        "a-first",
        "---\nname: a\ntrigger: always_on\ndescription: d\n---\nA body\n",
    )
    write_rule(tmp_path, "broken", "no frontmatter here\n")
    (tmp_path / "notes.txt").write_text(
        "---\nnot a markdown rule\n---\n", encoding="utf-8"
    )
    loaded = rules.load_rules(tmp_path)
    assert [r["name"] for r in loaded] == ["a", "b"]
    assert loaded[1]["body"] == "B body"


def test_load_rules_missing_folder_is_empty(tmp_path):
    assert rules.load_rules(tmp_path / "nope") == []


# --- glob_match ---


def test_glob_star_matches_any_run_except_slash():
    assert rules.glob_match("*.py", "run.py")
    assert rules.glob_match("a/*.py", "a/run.py")
    assert not rules.glob_match("a/*.py", "a/b/run.py")


def test_glob_question_is_exactly_one_character_except_slash():
    assert rules.glob_match("a?c", "abc")
    assert not rules.glob_match("a?c", "ac")
    assert not rules.glob_match("a?c", "abbc")
    assert rules.glob_match("a?/x", "ab/x")
    assert not rules.glob_match("a?/x", "a/x")


def test_glob_starstar_slash_matches_zero_or_more_whole_folders():
    assert rules.glob_match("**/x.py", "x.py")
    assert rules.glob_match("**/x.py", "a/b/x.py")
    assert not rules.glob_match("**/x.py", "ax.py")
    assert rules.glob_match("crew/**/*.py", "crew/x.py")
    assert rules.glob_match("crew/**/*.py", "crew/a/b/x.py")


def test_glob_trailing_starstar_matches_anything():
    assert rules.glob_match("crew/**", "crew/x.py")
    assert rules.glob_match("crew/**", "crew/a/b/x.py")
    assert not rules.glob_match("crew/**", "crew")
    assert not rules.glob_match("crew/**", "crewx")


def test_glob_pattern_without_slash_matches_the_last_segment_only():
    assert rules.glob_match("*.ps1", "a/b/run.ps1")
    assert not rules.glob_match("*.ps1", "a/b/run.txt")


def test_glob_is_case_insensitive():
    assert rules.glob_match("CREW/**/*.py", "crew/x.py")
    assert rules.glob_match("*.PS1", "a/b/run.ps1")
    assert rules.glob_match("a*/b", "A/b")


def test_glob_backslashes_count_as_slashes():
    assert rules.glob_match("crew\\**\\*.py", "crew\\a\\x.py")
    assert rules.glob_match("*.PS1", "a\\b\\run.ps1")
    assert not rules.glob_match("crew\\**\\*.py", "tests\\crew\\x.py")


def test_glob_whole_path_must_match_when_the_pattern_has_a_slash():
    assert not rules.glob_match("crew/**/*.py", "tests/crew/x.py")


# --- select ---


def test_select_picks_every_trigger_and_orders_by_trigger_then_name():
    rs = [
        make("z-aa", "always_on"),
        make("g1", "glob", globs=["*.py"]),
        make("m1", "manual"),
        make("md1", "model_decision", description="when it applies"),
        make("a-ab", "always_on"),
        make("m2", "manual"),
        make("g2", "glob", globs=["*.zzz"]),
    ]
    full, listed = rules.select(rs, files=("x/y.py",), manual=("m1",))
    assert [r["name"] for r in full] == ["a-ab", "z-aa", "g1", "m1"]
    assert [r["name"] for r in listed] == ["md1"]


def test_select_without_files_or_manual_drops_the_unmatched_glob_and_manual_rules():
    rs = [
        make("a", "always_on"),
        make("g", "glob", globs=["*.py"]),
        make("m", "manual"),
        make("d", "model_decision", description="d"),
    ]
    full, listed = rules.select(rs)
    assert [r["name"] for r in full] == ["a"]
    assert [r["name"] for r in listed] == ["d"]


# --- render ---


def test_render_empty_is_the_empty_string():
    assert rules.render([], []) == ""


def test_render_full_rules_only():
    assert (
        rules.render([make("a", "always_on", body="A body")], [])
        == "## Rules\n### a\nA body"
    )


def test_render_listed_lines():
    out = rules.render(
        [], [make("md", "model_decision", description="when it applies")]
    )
    assert out == (
        "## Rules\n"
        "Read one of these when it applies (crew/rules/<name>.md):\n"
        "- md: when it applies"
    )


def test_render_budget_overflow_moves_a_rule_to_the_listed_part():
    big = make("big", "always_on", description="a big rule", body="x" * 100)
    small = make("small", "always_on", body="s" * 10)
    out = rules.render([big, small], [], budget_chars=60)
    assert "### big" not in out
    assert "### small" in out
    assert "- big: a big rule" in out
    assert out.index("### small") < out.index("- big: a big rule")


def test_render_overflow_rule_without_description_gets_the_budget_note():
    big = make("big", "always_on", description="", body="x" * 100)
    out = rules.render([big], [], budget_chars=60)
    assert "- big: (over the rules budget)" in out


# --- for_brief / for_job ---


def seed_folder(folder: Path) -> None:
    write_rule(
        folder,
        "always-one",
        "---\nname: always-one\ntrigger: always_on\ndescription: always\n---\nAlways body.\n",
    )
    write_rule(
        folder,
        "ahk-sandbox-only",
        "---\nname: ahk-sandbox-only\ntrigger: glob\ndescription: sandbox only\n"
        'globs: "*.ahk, **/*.ahk"\n---\nSandbox body.\n',
    )
    write_rule(
        folder,
        "no-per-call-injection",
        "---\nname: no-per-call-injection\ntrigger: model_decision\n"
        "description: when designing a hook, a prompt or anything that adds text to calls\n"
        "---\nOnce body.\n",
    )


def test_for_brief_inlines_always_on_and_lists_model_decision(tmp_path):
    seed_folder(tmp_path)
    out = rules.for_brief(tmp_path)
    assert "### always-one" in out
    assert "### ahk-sandbox-only" not in out  # a brief knows no files yet
    assert (
        "- no-per-call-injection: when designing a hook, a prompt or anything "
        "that adds text to calls" in out
    )


def test_for_job_with_an_ahk_module_gets_the_glob_rule(tmp_path):
    seed_folder(tmp_path)
    out = rules.for_job(
        {"output": {"files": ["out.py"]}, "module": "bridge.ahk"}, tmp_path
    )
    assert "### ahk-sandbox-only" in out
    assert "### always-one" in out


def test_for_job_without_ahk_files_does_not_get_the_glob_rule(tmp_path):
    seed_folder(tmp_path)
    out = rules.for_job({"output": {"files": ["out.py"]}, "module": "m.py"}, tmp_path)
    assert "### ahk-sandbox-only" not in out


def test_for_job_reads_context_files_and_survives_missing_keys(tmp_path):
    seed_folder(tmp_path)
    out = rules.for_job({"context_files": ["deep/bridge.ahk"]}, tmp_path)
    assert "### ahk-sandbox-only" in out
    out = rules.for_job({}, tmp_path)
    assert "### ahk-sandbox-only" not in out
    assert "### always-one" in out


# --- the seed folder (crew/rules) and the PA brief ---


def test_the_seed_folder_has_the_three_seed_rules():
    loaded = rules.load_rules()
    assert [r["name"] for r in loaded] == [
        "ahk-sandbox-only",
        "no-per-call-injection",
        "powershell-not-bash",
    ]
    assert {r["name"]: r["trigger"] for r in loaded} == {
        "ahk-sandbox-only": "glob",
        "no-per-call-injection": "model_decision",
        "powershell-not-bash": "always_on",
    }
    ahk = next(r for r in loaded if r["name"] == "ahk-sandbox-only")
    assert ahk["globs"] == ["*.ahk", "**/*.ahk"]


def test_the_seed_brief_gets_the_always_on_rule_and_the_listed_one():
    out = rules.for_brief()
    assert "### powershell-not-bash" in out
    assert "### ahk-sandbox-only" not in out
    assert (
        "- no-per-call-injection: when designing a hook, a prompt or anything "
        "that adds text to calls" in out
    )


def test_the_pa_brief_contains_the_rules_section_when_the_seed_folder_has_always_on():
    brief = pa_brief.render("Claude")
    assert "## Rules" in brief
    assert "### powershell-not-bash" in brief


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
