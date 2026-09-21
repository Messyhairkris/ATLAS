import pytest
import quirk_tests

# ---------- python_fail_in_try tests ----------

def test_python_direct_assert_inside_try():
    """assert False directly inside a try block should be reported."""
    src = "try:\n    f()\n    assert False\nexcept Exception:\n    pass"
    assert quirk_tests.python_fail_in_try(src) == [3]

def test_python_assert_in_except_not_reported():
    """assert False inside an except block must not be reported."""
    src = "try:\n    f()\nexcept Exception:\n    assert False"
    assert quirk_tests.python_fail_in_try(src) == []

def test_python_assert_at_module_level_not_reported():
    """assert False at top level (outside any try) must not be reported."""
    src = "assert False"
    assert quirk_tests.python_fail_in_try(src) == []

def test_python_assert_nested_under_if_not_reported():
    """assert False inside an if that is inside a try must not be reported."""
    src = "try:\n    if x:\n        assert False\nexcept Exception:\n    pass"
    assert quirk_tests.python_fail_in_try(src) == []

def test_python_assert_with_blank_lines_and_comments():
    """Blank lines are skipped; commented assert lines are ignored."""
    src = (
        "try:\n"
        "    f()\n"
        "\n"
        "    # assert False\n"
        "    assert False  # real assert\n"
        "except Exception:\n"
        "    pass"
    )
    # The real assert is on line 5 (1-based)
    assert quirk_tests.python_fail_in_try(src) == [5]

def test_python_assert_preceded_by_non_try_less_indented_line():
    """If the first less-indented line above the assert is not a try, it is not reported."""
    src = (
        "def foo():\n"
        "    # comment line with less indent than the assert\n"
        "    assert False\n"
    )
    assert quirk_tests.python_fail_in_try(src) == []

def test_python_multiple_asserts_reported():
    """All qualifying assert False lines should be reported, in order."""
    src = (
        "try:\n"
        "    assert False\n"
        "    if cond:\n"
        "        pass\n"
        "    assert False\n"
        "except Exception:\n"
        "    pass"
    )
    # Lines 2 and 5 qualify
    assert quirk_tests.python_fail_in_try(src) == [2, 5]

# ---------- js_fail_in_try tests ----------

def test_js_assert_fail_inside_try_block():
    """assert.fail inside a multi-line try block should be reported."""
    src = "try {\n  f();\n  assert.fail('no throw');\n} catch (e) {}"
    assert quirk_tests.js_fail_in_try(src) == [3]

def test_js_assert_fail_inside_catch_not_reported():
    """assert.fail inside a catch block must not be reported."""
    src = "try {\n  f();\n} catch (e) {\n  assert.fail('oops');\n}"
    assert quirk_tests.js_fail_in_try(src) == []

def test_js_one_line_try_with_assert_fail():
    """A one-line try that contains assert.fail on the same line should be reported."""
    src = "try { f(); assert.fail('one line'); } catch (e) {}"
    # The whole line is line 1
    assert quirk_tests.js_fail_in_try(src) == [1]

def test_js_assert_fail_nested_inside_if_in_try():
    """assert.fail nested inside an if within a try block should be reported."""
    src = (
        "try {\n"
        "  if (x) {\n"
        "    assert . fail('nested');\n"
        "  }\n"
        "} catch (e) {}"
    )
    assert quirk_tests.js_fail_in_try(src) == [3]

def test_js_assert_fail_after_try_closed_not_reported():
    """assert.fail after the try block has closed must not be reported."""
    src = "try {\n  f();\n} finally {}\nassert.fail('after');"
    assert quirk_tests.js_fail_in_try(src) == []

# ---------- fail_in_try tests ----------

def test_fail_in_try_python_delegates_correctly():
    """fail_in_try with language='python' should delegate to python_fail_in_try."""
    src = "try:\n    assert False\nexcept Exception:\n    pass"
    assert quirk_tests.fail_in_try(src, "python") == [2]

def test_fail_in_try_unknown_language_raises():
    """fail_in_try with an unsupported language must raise ValueError containing the language."""
    with pytest.raises(ValueError) as exc:
        quirk_tests.fail_in_try("x", "ruby")
    assert "ruby" in str(exc.value)
