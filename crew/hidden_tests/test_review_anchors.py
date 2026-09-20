"""Hidden tests for review_anchors.py. The author never sees these."""

import pytest

import review_anchors as an

SIX = "a\nb\nc\nd\ne\nf"
CODE = ("def pick(items):\n"
        "    if not items:\n"
        "        return None\n"
        "    return items[0]\n")


def test_context_lines_constant():
    assert an.CONTEXT_LINES == 2


def test_make_anchor_quotes_exactly_those_lines():
    a = an.make_anchor(SIX, 3, 4)
    assert a["first_line"] == 3 and a["last_line"] == 4
    assert a["quote"] == "c\nd"
    assert len(a["digest"]) == 12
    assert all(ch in "0123456789abcdef" for ch in a["digest"])


def test_make_anchor_keeps_indentation():
    a = an.make_anchor(CODE, 2, 3)
    assert a["quote"] == "    if not items:\n        return None"


def test_single_line_anchor():
    a = an.make_anchor(SIX, 1, 1)
    assert a["quote"] == "a"


def test_the_digest_follows_the_quote():
    assert an.make_anchor(SIX, 1, 1)["digest"] != an.make_anchor(SIX, 2, 2)["digest"]
    assert an.make_anchor(SIX, 3, 4)["digest"] == an.make_anchor("c\nd", 1, 2)["digest"]


@pytest.mark.parametrize("first,last", [(0, 2), (3, 2), (1, 99), (-1, 1)])
def test_make_anchor_rejects_impossible_lines(first, last):
    with pytest.raises(ValueError):
        an.make_anchor(SIX, first, last)


def test_make_anchor_rejects_empty_text():
    with pytest.raises(ValueError):
        an.make_anchor("", 1, 1)


def test_format_and_parse_round_trip():
    a = an.make_anchor(SIX, 3, 4)
    label = an.format_anchor(a)
    assert label == f"L3-L4#{a['digest']}"
    back = an.parse_anchor(label)
    assert back["first_line"] == 3 and back["last_line"] == 4
    assert back["digest"] == a["digest"]
    assert "quote" not in back


def test_format_shows_both_numbers_even_for_one_line():
    a = an.make_anchor(SIX, 7 - 5, 2)
    assert an.format_anchor(a).startswith("L2-L2#")


@pytest.mark.parametrize("label", ["", "L3-L4", "3-4#abc123abc123", "L3#abc",
                                  "LA-LB#abc123abc123", "L3-L4#xyz",
                                  "L3-L4#abc123abc12"])
def test_parse_anchor_rejects_rubbish(label):
    with pytest.raises(ValueError):
        an.parse_anchor(label)


def test_excerpt_marks_the_anchored_lines_and_shows_context():
    a = an.make_anchor(SIX, 3, 4)
    assert an.excerpt(SIX, a) == ("  1: a\n"
                                  "  2: b\n"
                                  "> 3: c\n"
                                  "> 4: d\n"
                                  "  5: e\n"
                                  "  6: f")


def test_excerpt_clips_at_the_start_and_end():
    top = an.excerpt(SIX, an.make_anchor(SIX, 1, 1))
    assert top.splitlines()[0] == "> 1: a"
    assert len(top.splitlines()) == 3
    bottom = an.excerpt(SIX, an.make_anchor(SIX, 6, 6))
    assert bottom.splitlines()[-1] == "> 6: f"
    assert len(bottom.splitlines()) == 3


def test_excerpt_pads_wider_numbers():
    text = "\n".join(str(n) for n in range(1, 13))
    out = an.excerpt(text, an.make_anchor(text, 10, 10))
    assert "  8: 8" in out
    assert "> 10: 10" in out


def test_excerpt_rejects_an_anchor_outside_the_text():
    with pytest.raises(ValueError):
        an.excerpt("a\nb", {"first_line": 5, "last_line": 6, "quote": "x",
                            "digest": "0" * 12})


def test_relocate_unchanged():
    a = an.make_anchor(SIX, 3, 4)
    out = an.relocate(a, SIX)
    assert out["status"] == "unchanged"
    assert out["moved_by"] == 0
    assert (out["first_line"], out["last_line"]) == (3, 4)


def test_relocate_moved_down_reports_the_offset():
    a = an.make_anchor(SIX, 3, 4)
    out = an.relocate(a, "x\ny\n" + SIX)
    assert out["status"] == "moved"
    assert (out["first_line"], out["last_line"]) == (5, 6)
    assert out["moved_by"] == 2
    assert out["quote"] == "c\nd"


def test_relocate_moved_up_reports_a_negative_offset():
    a = an.make_anchor("x\ny\nc\nd\ne", 3, 4)
    out = an.relocate(a, "c\nd\ne")
    assert out["status"] == "moved"
    assert out["first_line"] == 1
    assert out["moved_by"] == -2


def test_relocate_stale_keeps_the_old_position():
    a = an.make_anchor(SIX, 3, 4)
    out = an.relocate(a, "a\nb\nTOTALLY\nDIFFERENT\ne\nf")
    assert out["status"] == "stale"
    assert (out["first_line"], out["last_line"]) == (3, 4)
    assert out["moved_by"] == 0
    assert out["quote"] == "c\nd"


def test_relocate_ambiguous_refuses_to_guess():
    a = an.make_anchor(SIX, 3, 4)
    out = an.relocate(a, "c\nd\nx\nc\nd")
    assert out["status"] == "ambiguous"
    assert (out["first_line"], out["last_line"]) == (3, 4)
    assert out["moved_by"] == 0


def test_relocate_matches_indentation_exactly():
    a = an.make_anchor(CODE, 2, 3)
    dedented = CODE.replace("    if not items:", "if not items:")
    assert an.relocate(a, dedented)["status"] == "stale"
