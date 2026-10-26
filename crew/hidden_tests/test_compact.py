"""Hidden tests for compact.py. Every contract row, plus the edges a long job meets."""

import pytest

import compact as cp

H = cp.NOTES_HEADER
LAST_TAIL = " SUBMIT your best complete file(s) now; a tool call here is wasted."


def test_constants():
    assert (cp.NOTE_MAX_CHARS, cp.NOTES_MAX_CHARS, cp.WARN_AT) == (300, 3000, 0.75)
    assert H == "YOUR NOTES FROM THE EARLIER RUN (you wrote these; do not redo that work):"


@pytest.mark.parametrize("text, want", [
    (42, None),
    (None, None),
    (["a"], None),
    ("  a\n\tb   c ", "a b c"),
    (" \n ", None),
    ("", None),
    ("x" * 301, "x" * 297 + "..."),
    ("x" * 300, "x" * 300),
    ("abc " * 100, "abc " * 74 + "a..."),
])
def test_clean_note(text, want):
    assert cp.clean_note(text) == want


def test_clean_note_right_strips_before_the_ellipsis():
    text = "y" * 296 + " " + "z" * 50           # char 297 is the space
    assert cp.clean_note(text) == "y" * 296 + "..."


def test_add_note_rejects_repeats_and_empties():
    notes = ["a"]
    assert cp.add_note(notes, "a") is False
    assert cp.add_note(notes, "  a  ") is False   # cleaned before the comparison
    assert notes == ["a"]
    assert cp.add_note(notes, " b ") is True
    assert notes == ["a", "b"]
    assert cp.add_note([], None) is False
    assert cp.add_note(notes, "\n") is False
    assert notes == ["a", "b"]


def test_add_note_mutates_the_given_list():
    notes = []
    same = notes
    cp.add_note(notes, "found it")
    assert same == ["found it"]


@pytest.mark.parametrize("notes, max_chars, want", [
    ([], 3000, ""),
    (["a", "b"], 3000, H + "\n- a\n- b"),
    (["aaaa", "bbbb", "cccc"], 13, H + "\n(1 older note folded away)\n- bbbb\n- cccc"),
    (["aaaa", "bbbb", "cccc"], 12, H + "\n(2 older notes folded away)\n- cccc"),
    (["aaaa", "bbbb", "cccc"], 6, H + "\n(2 older notes folded away)\n- cccc"),
    (["aaaa", "bbbb", "cccc"], 20, H + "\n- aaaa\n- bbbb\n- cccc"),
    (["a" * 50], 10, H + "\n- " + "a" * 50),
])
def test_render_notes(notes, max_chars, want):
    assert cp.render_notes(notes, max_chars) == want


def test_render_notes_keeps_a_newest_run_not_a_best_fit():
    # the second-newest does not fit, so the short oldest one is dropped too
    notes = ["a", "b" * 20, "c"]
    assert cp.render_notes(notes, 10) == H + "\n(2 older notes folded away)\n- c"


def test_render_notes_default_cap():
    notes = [f"note {i:03d} " + "x" * 90 for i in range(40)]
    out = cp.render_notes(notes)
    kept = out.split("\n")[2:]
    assert "\n".join(kept) == "\n".join(f"- {n}" for n in notes[-len(kept):])
    assert len("\n".join(kept)) <= 3000
    assert len("\n".join(f"- {n}" for n in notes[-len(kept) - 1:])) > 3000
    assert out.split("\n")[1] == f"({40 - len(kept)} older notes folded away)"


def test_render_notes_does_not_change_its_input():
    notes = ["aaaa", "bbbb", "cccc"]
    cp.render_notes(notes, 6)
    assert notes == ["aaaa", "bbbb", "cccc"]


def test_stub_short_content_unchanged():
    assert cp.stub("read_file", {"path": "x.md"}, "short", 400) == "short"
    assert cp.stub("read_file", {"path": "x.md"}, "abcd", 4) == "abcd"


def test_stub_row():
    want = ('abcd\n...[trimmed: read_file({"path": "x.md", "start": 5}) gave 10 chars; '
            'call it again to re-read a part]')
    assert cp.stub("read_file", {"start": 5, "path": "x.md"}, "abcdefghij", 4) == want


def test_stub_default_keep_and_other_tools():
    content = "z" * 1000
    out = cp.stub("fetch_url", {"url": "https://example.com/a"}, content)
    assert out.startswith("z" * 400 + "\n...[trimmed: fetch_url(")
    assert '{"url": "https://example.com/a"}' in out
    assert "gave 1000 chars" in out
    assert cp.stub("search", {}, "q" * 401) == ("q" * 400
                                                + "\n...[trimmed: search({}) gave 401 chars; "
                                                  "call it again to re-read a part]")


@pytest.mark.parametrize("args, want", [
    ((1000, 10000, 500, 5), ("", False)),
    ((7400, 10000, 500, 5), ("", False)),
    ((7500, 10000, 500, 5),
     ("TOKENS: 75% of this job's token budget is spent. Note what you still need and "
      "SUBMIT soon.", False)),
    ((8999, 10000, 1000, 5),
     ("TOKENS: 89% of this job's token budget is spent. Note what you still need and "
      "SUBMIT soon.", False)),
    ((9000, 10000, 1000, 5),
     ("LAST REPLY: 90% of this job's token budget is spent and one more reply this size "
      "would use the rest." + LAST_TAIL, True)),
    ((12000, 10000, 10, 3),
     ("LAST REPLY: 100% of this job's token budget is spent and one more reply this size "
      "would use the rest." + LAST_TAIL, True)),
    ((100, 10000, 50, 1), ("LAST REPLY: this is your last reply." + LAST_TAIL, True)),
    ((100, 10000, 50, 0), ("LAST REPLY: this is your last reply." + LAST_TAIL, True)),
    ((5000, 0, 9999, 5), ("", False)),
    ((5000, 0, 9999, 1), ("LAST REPLY: this is your last reply." + LAST_TAIL, True)),
])
def test_budget_line(args, want):
    assert cp.budget_line(*args) == want


def test_budget_line_requests_rule_wins_over_tokens():
    line, last = cp.budget_line(9900, 10000, 5000, 1)
    assert last and line.startswith("LAST REPLY: this is your last reply.")


def test_budget_line_percent_is_floored():
    line, _ = cp.budget_line(7999, 10000, 1, 9)
    assert line.startswith("TOKENS: 79% ")


@pytest.mark.parametrize("line, content, want", [
    ("", "body", "body"),
    ("TOKENS: 80%", "body", "TOKENS: 80%\n\nbody"),
    ("x", "", "x\n\n"),
])
def test_lead_with(line, content, want):
    assert cp.lead_with(line, content) == want
