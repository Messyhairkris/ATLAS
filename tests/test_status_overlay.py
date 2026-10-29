"""crew/runners/status_overlay.py - the always-on-top crew status window.

Only the two things added on 2026-10-29 are tested here, and both are pure on purpose: which
window counts as TheCrew's own (so the overlay can hide when it is in front) and how a build's
silence reads. The window itself is never opened.
"""

import importlib.util
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "crew" / "runners" / "status_overlay.py"


def _load():
    spec = importlib.util.spec_from_file_location("status_overlay", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


overlay = _load()


# ---- which window is TheCrew's own -------------------------------------------------------

def test_the_crew_process_name_is_recognised():
    assert overlay.is_crew_window("the-crew.exe", "")
    assert overlay.is_crew_window("the_crew.exe", "anything")
    assert overlay.is_crew_window("THE-CREW.EXE", "")


def test_the_title_is_the_fallback_when_the_name_is_unknown():
    assert overlay.is_crew_window("", "The Crew")
    assert overlay.is_crew_window("", "The Crew - control room")
    assert not overlay.is_crew_window("", "Visual Studio Code")


def test_a_known_other_process_is_not_the_crew_even_with_the_title():
    # a terminal titled "The Crew" is not the window we are hiding behind
    assert not overlay.is_crew_window("code.exe", "The Crew")
    assert not overlay.is_crew_window("pythonw.exe", "The Crew")


def test_nothing_at_all_is_not_the_crew():
    assert not overlay.is_crew_window("", "")
    assert not overlay.is_crew_window(None, None)


def test_foreground_is_crew_answers_without_raising():
    # it reads the real desktop; the only promise is that it decides and never throws
    assert isinstance(overlay.foreground_is_crew(), bool)


# ---- how a silent build reads ------------------------------------------------------------

def _touch(path: Path, age_s: float):
    path.write_text("x", encoding="utf-8")
    when = time.time() - age_s
    os.utime(path, (when, when))


def test_a_busy_build_is_not_silent(tmp_path):
    _touch(tmp_path / "status.json", 3)
    assert overlay.build_alive_note(tmp_path, silent_s=120) == ""


def test_a_silent_build_says_for_how_long(tmp_path):
    _touch(tmp_path / "status.json", 8 * 60)
    note = overlay.build_alive_note(tmp_path, silent_s=120)
    assert note.startswith("quiet for "), note
    assert note.endswith("m"), note


def test_the_newest_file_in_the_folder_decides(tmp_path):
    _touch(tmp_path / "old.txt", 30 * 60)
    _touch(tmp_path / "fresh.txt", 2)              # something is still writing
    assert overlay.build_alive_note(tmp_path, silent_s=120) == ""


def test_an_empty_folder_and_a_missing_one_are_quiet_by_saying_nothing(tmp_path):
    assert overlay.build_alive_note(tmp_path) == ""
    assert overlay.build_alive_note(tmp_path / "nope") == ""
