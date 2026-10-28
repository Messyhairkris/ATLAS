"""pa_build's preflight: a run with no session is a FAILURE, and the reason carries the engine's
own words.

The engine (opencode) prints its reason on stderr - "service=server error= failed", then
"Error: Session not found", with ANSI colour. A run that never happened must never be reported as
a pass: without this, run_checks graded an UNTOUCHED worktree and "passed" (measured 2026-10-28).
"""
import sys
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
