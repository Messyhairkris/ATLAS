"""pa_build's preflight: a run with no session is a FAILURE, and the reason carries the engine's
own words.

The engine (opencode) prints its reason on stderr - "service=server error= failed", then
"Error: Session not found", with ANSI colour. A run that never happened must never be reported as
a pass: without this, run_checks graded an UNTOUCHED worktree and "passed" (measured 2026-10-28).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew.runners import pa_build

NL = chr(10)
ESC = chr(27)


def test_a_no_session_reason_carries_the_engines_own_error():
    stderr = ("Performing one time database migration, may take a few minutes..." + NL
              + "sqlite-migration:done" + NL
              + ESC + "[91m" + ESC + "[1mError: " + ESC + "[0mSession not found" + NL)
    why = pa_build.no_session_reason(stderr)
    assert "did not start" in why, why
    assert "Session not found" in why, why
    assert ESC not in why, "the ANSI colour must be stripped"


def test_a_no_session_reason_prefers_an_error_line_over_the_last_line():
    why = pa_build.no_session_reason("INFO starting" + NL + "ERROR service=server error= failed" + NL + "done" + NL)
    assert "service=server error= failed" in why, why


def test_a_no_session_reason_with_no_stderr_is_still_clear():
    why = pa_build.no_session_reason("")
    assert why.startswith("no session"), why
    assert "engine said" not in why, why


# ---- saved_by: which fixers actually changed something ---------------------------------------

def test_saved_by_names_each_fixer_once_in_order():
    sentences = ["cargo_fix: cargo fix applied the compiler's suggestions (--allow-dirty)",
                 "normalise_newlines: rewrote CRLF/BOM in 1 file(s): a.py",
                 "cargo_fix: a second sentence from the same fixer"]
    assert pa_build.saved_by(sentences) == ["cargo_fix", "normalise_newlines"]


def test_saved_by_of_nothing_is_empty():
    assert pa_build.saved_by([]) == []


# ---- fixer_message: the check output is quoted, never paraphrased ----------------------------

def test_fixer_message_carries_the_check_output_verbatim():
    checks = "$ python -m pytest -q" + NL + "-> FAILED" + NL + "E   SyntaxError: boom"
    msg = pa_build.fixer_message(checks, ["cargo_fix: applied the compiler's suggestions"])
    assert "E   SyntaxError: boom" in msg, msg            # the compiler's own line, unchanged
    assert checks in msg, msg
    assert "cargo_fix: applied the compiler's suggestions" in msg, msg


def test_fixer_message_says_so_when_no_fixer_acted():
    msg = pa_build.fixer_message("$ pytest" + NL + "-> FAILED" + NL + "boom", [])
    assert "no fixer acted" in msg, msg
    assert "boom" in msg, msg                             # the output is still quoted in full


# ---- record_fixers: the evidence file, and never a raise --------------------------------------

def test_record_fixers_writes_one_line_per_sentence():
    with tempfile.TemporaryDirectory(prefix="pa-build-") as home:
        root = Path(home)
        pa_build.record_fixers(root, ["cargo_fix: applied", "ruff_fix: fixed 1 file(s): a.py"])
        text = (root / "fixers.txt").read_text(encoding="utf-8")
        assert text.splitlines() == ["cargo_fix: applied", "ruff_fix: fixed 1 file(s): a.py"]


def test_record_fixers_writes_no_fixer_acted_for_an_empty_list():
    with tempfile.TemporaryDirectory(prefix="pa-build-") as home:
        root = Path(home)
        pa_build.record_fixers(root, [])
        assert (root / "fixers.txt").read_text(encoding="utf-8").strip() == "no fixer acted"


# ---- fix_plugin_env: the refused-command plugin is on every build, and it exists

REPO = Path(__file__).resolve().parents[1]


def test_the_refused_command_plugin_is_put_on_the_builds_env():
    env = pa_build.fix_plugin_env(REPO, Path("C:/tmp/build-home"))
    config_dir = Path(env["OPENCODE_CONFIG_DIR"])
    assert config_dir.name == "opencode_config" and config_dir.parent.name == "crew", config_dir
    log = Path(env["CREW_FIX_LOG"])
    assert log.name == "fixes.jsonl" and log.parent.name == "build-home", log


def test_the_plugin_the_env_points_at_really_exists():
    # Fails if the plugin is moved or renamed out from under the wiring - the env would then
    # point at nothing and a build would silently lose its rewrites.
    plugin = REPO / "crew" / "opencode_config" / "plugins" / "fix_commands.js"
    assert plugin.is_file(), plugin
    src = plugin.read_text(encoding="utf-8")
    assert "export const STRATEGY" in src, "the gate reads STRATEGY from the plugin"
    assert "tool.execute.before" in src, "the hook that rewrites the call before it runs"


