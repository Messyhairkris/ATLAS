"""crew/fixers.py - the mechanical repairs a failed build may take itself.

Every test builds its own tiny worktree and a real file, and asserts on the bytes. The point
of the module is restraint, so most of these check what a fixer did NOT touch: a file it was
not handed, a file already valid, a failure it does not recognise. `cargo` and `ruff` are not
assumed to be installed - when they are absent, the fixer must say so and change nothing.

The worktree comes from `tempfile`, not pytest's `tmp_path`: this machine's shared pytest
temp root is not listable, and a test that cannot even make a folder proves nothing.
"""

import importlib.util
import shutil
import tempfile
from pathlib import Path

import pytest

from crew import fixers

BOM = b"\xef\xbb\xbf"


@pytest.fixture()
def worktree():
    """A private worktree the fixers may write in, cleaned up when the test ends."""
    with tempfile.TemporaryDirectory(prefix="fixers-") as home:
        root = Path(home) / "wt"
        root.mkdir()
        yield root


def _ruff_available() -> bool:
    if shutil.which("ruff"):
        return True
    try:
        return importlib.util.find_spec("ruff") is not None
    except (ImportError, ValueError):
        return False


# ---- run_fixers: who tries, and when nothing does ---------------------------------------

def test_run_fixers_returns_nothing_for_an_unrecognised_failure(worktree):
    (worktree / "a.py").write_bytes(b"x = 1\r\n")
    assert fixers.run_fixers(worktree, "unrelated garbage", ["a.py"]) == []


def test_a_fixer_that_matches_nothing_leaves_the_file_byte_identical(worktree):
    target = worktree / "a.py"
    target.write_bytes(b"x = 1\r\n")
    before = target.read_bytes()
    assert fixers.run_fixers(worktree, "unrelated garbage", ["a.py"]) == []
    assert target.read_bytes() == before


def test_run_fixers_never_raises_on_odd_input(worktree):
    assert fixers.run_fixers(worktree, "", []) == []
    assert fixers.run_fixers(worktree, None, None) == []
    assert fixers.run_fixers(worktree, "unrelated garbage", []) == []
    assert fixers.run_fixers(None, "unrelated garbage", []) == []


def test_run_fixers_reports_every_fixer_that_acted_in_the_order_it_ran(worktree):
    (worktree / "a.py").write_bytes(b"x = 1\r\n")
    (worktree / "a.json").write_text('{"a": 1,}', encoding="utf-8")
    out = fixers.run_fixers(
        worktree, "error: CRLF line endings\nerror: Expecting ',' delimiter in a.json",
        ["a.py", "a.json"])
    assert (worktree / "a.py").read_bytes() == b"x = 1\n"
    assert (worktree / "a.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert len(out) == 2
    assert "normalise_newlines" in out[0]
    assert "repair_json_toml" in out[1]


# ---- normalise_newlines -----------------------------------------------------------------

def test_normalise_newlines_touches_only_the_files_it_is_given(worktree):
    given = worktree / "a.txt"
    given.write_bytes(b"one\r\n")
    other = worktree / "b.txt"
    other.write_bytes(b"two\r\n")
    before_other = other.read_bytes()

    sentence = fixers.normalise_newlines(worktree, ["a.txt"])

    assert given.read_bytes() == b"one\n"
    assert other.read_bytes() == before_other        # never handed over: untouched
    assert "a.txt" in sentence


def test_a_crlf_and_bom_repair_changes_only_the_named_file(worktree):
    named = worktree / "a.py"
    named.write_bytes(BOM + b"x = 1\r\n")
    other = worktree / "b.py"
    other.write_bytes(b"y = 2\r\n")                  # the same fault, but not this round's
    before_other = other.read_bytes()

    out = fixers.run_fixers(worktree, "error: CRLF line endings (BOM) in a.py", ["a.py"])

    assert named.read_bytes() == b"x = 1\n"
    assert other.read_bytes() == before_other
    assert len(out) == 1
    assert "normalise_newlines" in out[0]


def test_run_fixers_reads_a_git_status_line_as_a_file_name(worktree):
    target = worktree / "a.py"
    target.write_bytes(b"x = 1\r\n")
    out = fixers.run_fixers(worktree, "error: CRLF line endings in a.py", [" M a.py"])
    assert target.read_bytes() == b"x = 1\n"
    assert out


def test_normalise_newlines_refuses_a_path_outside_the_worktree(worktree):
    outside = worktree.parent / "outside.txt"
    outside.write_bytes(b"keep\r\n")
    before = outside.read_bytes()

    assert fixers.normalise_newlines(worktree, ["../outside.txt"]) == ""
    assert outside.read_bytes() == before


def test_normalise_newlines_skips_a_binary_file(worktree):
    target = worktree / "blob.bin"
    target.write_bytes(b"\x00\x01\r\n\x02")
    before = target.read_bytes()

    assert fixers.normalise_newlines(worktree, ["blob.bin"]) == ""
    assert target.read_bytes() == before


def test_normalise_newlines_reports_nothing_for_a_file_that_is_not_there(worktree):
    assert fixers.normalise_newlines(worktree, ["gone.txt"]) == ""


# ---- repair_json_toml -------------------------------------------------------------------

def test_repair_json_toml_fixes_a_named_trailing_comma(worktree):
    bad = worktree / "data.json"
    bad.write_text('{"a": 1,}\n', encoding="utf-8")

    out = fixers.run_fixers(worktree, "Expecting ',' delimiter: line 1 in data.json", [])

    assert bad.read_text(encoding="utf-8") == '{"a": 1}\n'
    assert len(out) == 1
    assert "repair_json_toml" in out[0]


def test_repair_json_toml_leaves_a_valid_file_byte_identical(worktree):
    good = worktree / "ok.json"
    good.write_bytes(b'{"a": 1}\n')
    before = good.read_bytes()

    assert fixers.run_fixers(worktree, "Expecting ',' delimiter in ok.json", []) == []
    assert good.read_bytes() == before


def test_repair_json_toml_keeps_a_closing_brace_that_sits_inside_a_string(worktree):
    tricky = worktree / "tricky.json"
    tricky.write_text('{"a": "x,}", "b": 2,}', encoding="utf-8")

    out = fixers.repair_json_toml(worktree, ["tricky.json"])

    assert tricky.read_text(encoding="utf-8") == '{"a": "x,}", "b": 2}'
    assert out


def test_repair_json_toml_leaves_an_unrepairable_file_alone(worktree):
    broken = worktree / "broken.json"
    broken.write_bytes(b'{"a": ')
    before = broken.read_bytes()

    assert fixers.repair_json_toml(worktree, ["broken.json"]) == ""
    assert broken.read_bytes() == before


def test_repair_json_toml_ignores_a_file_whose_kind_it_does_not_repair(worktree):
    target = worktree / "notes.txt"
    target.write_bytes(b'{"a": 1,}')
    before = target.read_bytes()

    assert fixers.repair_json_toml(worktree, ["notes.txt"]) == ""
    assert target.read_bytes() == before


# ---- cargo_fix and ruff_fix: absent tools decline, and change nothing -------------------

def test_cargo_fix_declines_without_a_cargo_project_and_changes_nothing(worktree):
    target = worktree / "src" / "main.rs"
    target.parent.mkdir()
    target.write_bytes(b"fn main() {}\n")
    before = target.read_bytes()

    sentence = fixers.cargo_fix(worktree)

    assert sentence != ""                             # no cargo, or no Cargo.toml: it says so
    assert target.read_bytes() == before


def test_ruff_fix_declines_when_ruff_is_absent_and_changes_nothing(worktree):
    target = worktree / "mod.py"
    target.write_bytes(b"value = 1\n")               # clean: even a real ruff changes nothing
    before = target.read_bytes()

    sentence = fixers.ruff_fix(worktree, ["mod.py"])

    assert target.read_bytes() == before
    if not _ruff_available():
        assert sentence != ""                         # no ruff: it says so, never silently


def test_cargo_fix_on_a_missing_worktree_does_not_raise(worktree):
    assert fixers.cargo_fix(worktree / "nope") != ""
