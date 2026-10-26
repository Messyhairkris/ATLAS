"""Tests for crew/gitstatus.py and crew/runners/changes.py - the Changes pane.

Run: python -m pytest tests/test_changes.py -q
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from crew import gitstatus  # noqa: E402
from crew.runners import changes  # noqa: E402

SHA = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
ZERO = "0000000000000000000000000000000000000000"


# --- unquote ---------------------------------------------------------------


def test_unquote_plain_path_is_unchanged():
    assert gitstatus.unquote("src/a file.txt") == "src/a file.txt"
    assert gitstatus.unquote("café.md") == "café.md"


def test_unquote_strips_surrounding_quotes():
    assert gitstatus.unquote('"plain.txt"') == "plain.txt"
    assert gitstatus.unquote('"my file.txt"') == "my file.txt"


def test_unquote_escapes():
    assert gitstatus.unquote('"a\\tb.txt"') == "a\tb.txt"
    assert gitstatus.unquote('"a\\nb.txt"') == "a\nb.txt"
    assert gitstatus.unquote('"a\\\\b.txt"') == "a\\b.txt"
    assert gitstatus.unquote('"say \\"hi\\""') == 'say "hi"'


def test_unquote_octal_is_bytes_decoded_utf8():
    assert gitstatus.unquote('"caf\\303\\251.md"') == "café.md"


# --- parse_status ----------------------------------------------------------


def test_parse_status_branch_headers():
    status = gitstatus.parse_status(
        "# branch.oid 9fceb02d0ae598e95dc970b74767f19372d61af8\n"
        "# branch.head main\n"
        "# branch.upstream origin/main\n"
        "# branch.ab +2 -1\n"
    )
    assert status["oid"] == "9fceb02d0ae598e95dc970b74767f19372d61af8"
    assert status["branch"] == "main"
    assert status["upstream"] == "origin/main"
    assert status["ahead"] == 2
    assert status["behind"] == 1


def test_parse_status_detached_head_is_kept():
    status = gitstatus.parse_status(f"# branch.oid {SHA}\n# branch.head (detached)\n")
    assert status["branch"] == "(detached)"
    assert status["oid"] == SHA


def test_parse_status_missing_headers_give_empty_and_zero():
    status = gitstatus.parse_status("? a.txt\n")
    assert status["branch"] == ""
    assert status["oid"] == ""
    assert status["upstream"] == ""
    assert status["ahead"] == 0
    assert status["behind"] == 0


def test_parse_status_every_line_kind():
    text = (
        "# branch.oid (initial)\n"
        "# branch.head main\n"
        f"1 .M N... 100644 100644 100644 {SHA} {SHA} src/modified.py\n"
        f"1 M. N... 100644 100644 100644 {SHA} {SHA} src/staged.py\n"
        f"1 A. N... 000000 100644 100644 {ZERO} {SHA} src/added.py\n"
        f"1 .D N... 100644 000000 000000 {SHA} {ZERO} src/deleted.py\n"
        f"1 T. N... 100644 120000 120000 {SHA} {SHA} link.sh\n"
        f"2 R. N... 100644 100644 100644 {SHA} {SHA} R100 src/newname.py\tsrc/oldname.py\n"
        f"2 C. N... 100644 100644 100644 {SHA} {SHA} C100 src/copy.py\tsrc/original.py\n"
        f"u UU N... 100644 100644 100644 100644 {SHA} {SHA} {SHA} src/conflicted.py\n"
        "? notes.txt\n"
        "! build/output.bin\n"
        "x an unknown line\n"
    )
    status = gitstatus.parse_status(text)
    files = {f["path"]: f for f in status["files"]}
    assert status["oid"] == "(initial)"
    assert len(files) == 9, "ignored and unknown lines are skipped"

    assert files["src/modified.py"] == {
        "path": "src/modified.py",
        "orig": "",
        "staged": ".",
        "unstaged": "M",
        "kind": "modified",
    }
    assert files["src/staged.py"]["kind"] == "modified"
    assert files["src/staged.py"]["staged"] == "M"
    assert files["src/added.py"]["kind"] == "added"
    assert files["src/deleted.py"]["kind"] == "deleted"
    assert files["link.sh"]["kind"] == "typechange"

    renamed = files["src/newname.py"]
    assert renamed["kind"] == "renamed"
    assert renamed["orig"] == "src/oldname.py"

    copied = files["src/copy.py"]
    assert copied["kind"] == "copied"
    assert copied["orig"] == "src/original.py"

    conflict = files["src/conflicted.py"]
    assert conflict["kind"] == "conflict"
    assert conflict["staged"] == "U" and conflict["unstaged"] == "U"

    untracked = files["notes.txt"]
    assert untracked["kind"] == "untracked"
    assert untracked["staged"] == "?" and untracked["unstaged"] == "?"


def test_parse_status_unknown_xy_letter_is_modified():
    status = gitstatus.parse_status(
        f"1 Q. N... 100644 100644 100644 {SHA} {SHA} odd.txt\n"
    )
    assert status["files"][0]["kind"] == "modified"


def test_parse_status_quoted_paths():
    status = gitstatus.parse_status(
        '? "a\\tb.txt"\n'
        '? "caf\\303\\251.md"\n'
        f'1 .M N... 100644 100644 100644 {SHA} {SHA} "my file.txt"\n'
    )
    paths = [f["path"] for f in status["files"]]
    assert paths == ["a\tb.txt", "café.md", "my file.txt"]


# --- parse_numstat ---------------------------------------------------------


def test_parse_numstat():
    stats = gitstatus.parse_numstat(
        "3\t2\tsrc/a.py\n"
        "-\t-\timg/logo.png\n"
        "0\t0\tdocs/{old.md => new.md}\n"
        "1\t1\ta.txt => b.txt\n"
        "\n"
    )
    assert stats == {
        "src/a.py": [3, 2],
        "img/logo.png": None,  # binary
        "docs/{old.md => new.md}": [0, 0],  # rename kept as printed
        "a.txt => b.txt": [1, 1],
    }


# --- summary ---------------------------------------------------------------


def _status(kinds, ahead=0, behind=0):
    files = [
        {
            "path": f"{kind}{i}.txt",
            "orig": "",
            "staged": "?",
            "unstaged": "?",
            "kind": kind,
        }
        for i, kind in enumerate(kinds)
    ]
    return {
        "branch": "main",
        "oid": SHA,
        "upstream": "",
        "ahead": ahead,
        "behind": behind,
        "files": files,
    }


def test_summary_clean():
    assert gitstatus.summary(_status([])) == "clean"
    assert gitstatus.summary(gitstatus.parse_status("# branch.head main\n")) == "clean"


def test_summary_changed_and_untracked():
    assert (
        gitstatus.summary(_status(["modified", "added", "deleted", "untracked"]))
        == "3 changed, 1 untracked"
    )


def test_summary_conflicts_count_separately_and_inside_changed():
    assert (
        gitstatus.summary(_status(["modified", "conflict"])) == "2 changed, 1 conflict"
    )
    assert (
        gitstatus.summary(_status(["conflict", "conflict"])) == "2 changed, 2 conflicts"
    )


def test_summary_ahead_and_behind():
    assert gitstatus.summary(_status([], ahead=2)) == "ahead 2"
    assert gitstatus.summary(_status([], behind=1)) == "behind 1"
    assert (
        gitstatus.summary(_status(["modified"], ahead=2, behind=1))
        == "1 changed, ahead 2, behind 1"
    )


def test_summary_every_part_in_order():
    assert (
        gitstatus.summary(
            _status(
                ["modified", "modified", "conflict", "untracked"], ahead=2, behind=1
            )
        )
        == "3 changed, 1 untracked, 1 conflict, ahead 2, behind 1"
    )


# --- integration: the runner against a real repository ---------------------


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _rmtree(path):
    """rmtree that survives git's read-only object files on Windows."""

    def onexc(func, p, _exc_info):
        os.chmod(p, 0o666)
        func(p)

    shutil.rmtree(path, onexc=onexc)


def test_runner_collect_integration():
    # The sandbox may deny pytest's tmp_path base temp; build the throwaway
    # repo inside the worktree and always remove it.
    repo = Path(tempfile.mkdtemp(prefix="changes-test-", dir=REPO))
    try:
        _integration_body(repo)
    finally:
        _rmtree(repo)


def _integration_body(repo):
    init = subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True)
    if init.returncode != 0:  # git < 2.28: no -b
        _git(repo, "init")
        _git(repo, "checkout", "-b", "main")

    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init")

    (repo / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
    (repo / "loose.txt").write_text("new\n", encoding="utf-8")

    data = changes.collect([str(repo)])
    entry = data["repos"][0]
    assert "error" not in entry
    assert entry["name"] == repo.name
    assert entry["branch"] == "main"
    assert entry["upstream"] == ""
    assert entry["ahead"] == 0 and entry["behind"] == 0
    assert entry["summary"] == "1 changed, 1 untracked"

    files = {f["path"]: f for f in entry["files"]}
    assert set(files) == {"tracked.txt", "loose.txt"}

    tracked = files["tracked.txt"]
    assert tracked["kind"] == "modified"
    assert tracked["staged"] == "." and tracked["unstaged"] == "M"
    assert tracked["added"] == 1 and tracked["deleted"] == 0

    loose = files["loose.txt"]
    assert loose["kind"] == "untracked"
    assert loose["added"] is None and loose["deleted"] is None
