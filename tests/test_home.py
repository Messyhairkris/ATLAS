"""Tests for crew/home.py: the settings placeholders that keep an account name out of the tree."""

import os
from pathlib import Path

import pytest

from crew import home


def test_home_is_replaced():
    assert home.expand("${HOME}/Documents", home="/h/me") == "/h/me/Documents"


def test_repo_is_replaced():
    assert home.expand("${REPO}/runs/crew", repo="/r/x") == "/r/x/runs/crew"


def test_both_in_one_string():
    assert home.expand("${REPO}/a:${HOME}/b", home="/h", repo="/r") == "/r/a:/h/b"


def test_a_leading_tilde_is_replaced():
    assert home.expand("~/Documents", home=r"C:\u\me") == r"C:\u\me/Documents"


def test_a_tilde_inside_the_string_is_left_alone():
    assert home.expand("a~b", home="/h") == "a~b"


def test_without_a_replacement_the_real_paths_are_used():
    got = home.expand("${REPO}")
    assert got == str(home.REPO_ROOT) and os.path.isabs(got)


def test_plain_text_is_unchanged():
    assert home.expand("cargo test -p crew_control") == "cargo test -p crew_control"


@pytest.mark.parametrize("value", [None, 7, True])
def test_a_non_string_is_returned_as_it_is(value):
    assert home.expand(value) is value


def test_expand_all_walks_a_list():
    assert home.expand_all(["${HOME}/a", "plain"], home="/h") == ["/h/a", "plain"]


def test_expand_all_walks_a_dict_without_changing_its_shape():
    got = home.expand_all({"roots": ["${REPO}/runs"], "name": "crew"}, repo="/r")
    assert got == {"roots": ["/r/runs"], "name": "crew"}


def test_expand_all_leaves_numbers_alone():
    assert home.expand_all({"n": 3, "b": None}) == {"n": 3, "b": None}


def test_placeholders_and_relative_paths_are_portable():
    assert home.is_portable("${HOME}/x")
    assert home.is_portable("${REPO}/x")
    assert home.is_portable("runs/crew")
    assert home.is_portable(None)


def test_an_absolute_path_is_not_portable():
    assert not home.is_portable("C:/Users/someone/x")
    assert not home.is_portable("/home/someone/x")
