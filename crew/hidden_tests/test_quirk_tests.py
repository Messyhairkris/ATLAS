"""Hidden tests for quirk_tests.py. Every contract row, plus real crew habits."""

import pytest

import quirk_tests as qt

PY_ROWS = [
    ("try:\n    f()\n    assert False\nexcept ValueError:\n    pass", [3]),
    ("try:\n    f()\nexcept ValueError:\n    assert False", []),
    ("assert False", []),
    ("try:\n    if x:\n        assert False\nexcept E:\n    pass", []),
    ("try:\n    f()\n\n    assert False  # no raise\nexcept E:\n    pass", [4]),
    ("try:\n    # assert False\n    f()\nexcept E:\n    pass", []),
    ("def t():\n    try:\n        g()\n        assert  False\n    except E:\n        pass", [4]),
]
JS_ROWS = [
    ('try {\n  f();\n  assert.fail("no throw");\n} catch (e) {}', [3]),
    ('try {\n  f();\n} catch (e) {\n  assert.fail("x");\n}', []),
    ('assert.fail("plain");', []),
    ('try { f(); assert.fail("one line"); } catch (e) {}', [1]),
    ('try {\n  if (x) {\n    assert . fail("nested");\n  }\n} catch (e) {}', [3]),
    ('try {\n  f();\n} finally {}\nassert.fail("after");', []),
]


@pytest.mark.parametrize("source,expected", PY_ROWS)
def test_python_table(source, expected):
    assert qt.python_fail_in_try(source) == expected


@pytest.mark.parametrize("source,expected", JS_ROWS)
def test_js_table(source, expected):
    assert qt.js_fail_in_try(source) == expected


def test_dispatch():
    assert qt.fail_in_try(PY_ROWS[0][0], "python") == [3]
    assert qt.fail_in_try(JS_ROWS[0][0], "javascript") == [3]


def test_unknown_language_raises_naming_it():
    with pytest.raises(ValueError, match="ruby"):
        qt.fail_in_try("x", "ruby")


def test_assert_false_not_a_word_is_ignored():
    assert qt.python_fail_in_try("try:\n    assert Falsey\nexcept E:\n    pass") == []


def test_several_in_one_file_in_order():
    source = ("def a():\n    try:\n        f()\n        assert False\n    except E:\n        pass\n"
              "\n\ndef b():\n    try:\n        g()\n        assert False\n    except E:\n"
              "        pass\n")
    assert qt.python_fail_in_try(source) == [4, 12]


NEMOTRON_STYLE = '''test("packedPage throws for a missing entry", () => {
  try {
    mod.packedPage({ ...site, entry: "x:nope" });
    assert.fail("expected a throw");
  } catch (e) {
    assert.ok(/x:nope/.test(e.message));
  }
});

test("good style", () => {
  assert.throws(() => mod.packedPage({ ...site, entry: "x:nope" }), /x:nope/);
});
'''


def test_a_real_crew_test_file():
    assert qt.js_fail_in_try(NEMOTRON_STYLE) == [4]


def test_two_tries_back_to_back():
    source = ('try {\n  a();\n} catch (e) {}\ntry {\n  b();\n  assert.fail("b");\n}'
              ' catch (e) {}\nassert.fail("outside");')
    assert qt.js_fail_in_try(source) == [6]
