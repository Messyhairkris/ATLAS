# House style for crew-written code

Paste this section into every `code_task` and `code_tests` contract. It exists
because the first campaign produced **correct** code with 64 lint findings, and
every one of them was something nobody had asked for in writing.

Most of this is now enforced mechanically by `python -m crew unify`, which runs
`ruff` over staged output and keeps a fix only if the tests still pass. Stating it
here anyway is not redundant: a member that writes it correctly the first time
costs nothing, and the tool cannot fix the last two items at all.

## Layout

- **88 characters** maximum per line, including comments and docstrings.
- Two blank lines between top-level functions and classes, one between methods.
- Imports: standard library first, then the modules this task may use, each group
  alphabetical, no unused imports.
- No banner comments (`# ---- Constants ----`). If a file needs signposting to be
  readable, it is too long.

## Typing

- Built-in generics: `list[dict[str, int]]`, not `List[Dict[str, int]]`.
- `str | None`, not `Optional[str]` or `Union[str, None]`.
- Annotate every public function's arguments and return type. Do not annotate a
  pytest test function's return type.
- A type hint must be **true**: if the contract says any object is acceptable and
  only `False` is special, the hint is `object`, not `bool`.

## Structure

- Do not repeat a literal structure. If the same dict shape is returned from four
  places, write one small helper that builds it - four copies means four things to
  edit when the shape changes.
- Do not wrap a one-line expression in a helper used twice.
- Prefer one clear pass over a clever one. This code is read by people who did not
  write it, including other crew members.

## Docstrings

- Every module, public function and public class gets one.
- A docstring says **why or what rule**, never what the filename already says.
  `"""chattiness.py - deciding what the voice mentions"""` tells the reader
  nothing.
- **Never invent a reason.** If you do not know why a rule exists, describe the
  rule and stop. A fabricated rationale costs the next reader more time than no
  rationale at all. (In the first campaign one test was documented as
  "addressing empty_replies failure" - an internal harness detail that had nothing
  to do with the function under test.)

## Tests

- `pytest` style: plain functions named `test_*`, bare `assert`, no classes.
- **`pytest.raises`, never `try/except` with `assert False`.** Under `python -O`
  an `assert` is removed, so that test passes even when nothing is raised.
- One rule per test, and name the test after the rule it checks.
- Construct the case so it can only pass for the right reason. If you are testing
  that a preference is applied, put the preferred item where a naive
  implementation would not find it.
- Do not assign a result you never read.

## The two things no tool can check for you

1. **Say when the contract is wrong.** If a rule is ambiguous or contradicts
   another, write a NOTE line at the end of your answer AND implement it as
   written. The note reaches a human; guessing does not.
2. **Order operations so nothing is consumed by a failure.** Do not allocate an
   id, take a slot, or record a count before the check that might reject the work.
   (In the first campaign a refused `enqueue` still consumed an utterance id, so
   ids jumped from 2 to 5. No test caught it; a reader did.)
