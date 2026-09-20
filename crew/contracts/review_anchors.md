# Contract: review_anchors.py — keeping a note attached to the right line

One self-contained Python module, `review_anchors.py`. Pure text logic for the
part of CrossTalk's review desk Kris asked for: *"I would love to be able to
review it directly through the interface as well, so that notes are direct with
the document or script I am looking at."*

A note that says "line 42" is worthless the moment line 12 changes. So an anchor
stores the lines **and a quote of them**, and can later be re-found in a changed
file, or honestly declared stale.

Allowed imports: `typing`, `re`, `hashlib`. Nothing else. The caller supplies the
file's text; this module never opens anything.

## Public API

```python
CONTEXT_LINES = 2

def make_anchor(text: str, first_line: int, last_line: int) -> dict: ...
def format_anchor(anchor: dict) -> str: ...
def parse_anchor(label: str) -> dict: ...
def excerpt(text: str, anchor: dict) -> str: ...
def relocate(anchor: dict, new_text: str) -> dict: ...
```

Line numbers are **1-based and inclusive**, the way an editor shows them.

## make_anchor(text, first_line, last_line)

Returns:

```python
{"first_line": int, "last_line": int,
 "quote": str,        # exactly those lines, joined with "\n"
 "digest": str}       # first 12 hex characters of the sha256 of the quote
```

- `first_line < 1`, `last_line < first_line`, or `last_line` past the end of the
  text raises `ValueError`.
- An empty `text` raises `ValueError` whatever the numbers.
- The quote keeps the lines' own leading whitespace: indentation is part of code.

## format_anchor(anchor) / parse_anchor(label)

`format_anchor` gives `"L12-L18#a1b2c3d4e5f6"` — the letter L, the first line, a
hyphen, L, the last line, `#`, then the digest. A single-line anchor still shows
both: `"L7-L7#..."`.

`parse_anchor` reads that back into `{"first_line": int, "last_line": int,
"digest": str}` (no quote — the label does not carry one). Anything that does not
match the shape raises `ValueError`. It must accept the exact output of
`format_anchor` for every valid anchor.

## excerpt(text, anchor)

The anchored lines **plus `CONTEXT_LINES` of context on each side**, joined with
`"\n"`, clipped at the start and end of the file. Each line is built exactly like
this, so there is nothing to guess:

```python
f"{mark} {number:>{width}}: {line}"
```

where `mark` is `">"` for an anchored line and `" "` for a context line, `number`
is the 1-based line number, and `width` is `len(str(last_number_shown))`.

For a six-line file `"a\nb\nc\nd\ne\nf"` and an anchor on lines 3-4:

```
  1: a
  2: b
> 3: c
> 4: d
  5: e
  6: f
```

(Here the width is 1, so the numbers are not padded; a file of 100+ lines pads
them.) An anchor outside the text raises `ValueError`.

## relocate(anchor, new_text)

The interesting one. Given an old anchor and the file as it is **now**, returns:

```python
{"first_line": int, "last_line": int, "quote": str, "digest": str,
 "status": str, "moved_by": int}
```

`status` is one of:

- `"unchanged"` — the same lines still hold exactly the anchor's quote.
  `moved_by` is 0.
- `"moved"` — the quote appears exactly once elsewhere in the new text, as a
  consecutive block of lines. The returned anchor points at the new location, and
  `moved_by` is the signed difference in first line (negative when it moved up).
- `"ambiguous"` — the quote appears more than once. Keep the ORIGINAL line
  numbers, `moved_by` 0, and let a human decide.
- `"stale"` — the quote no longer appears at all. Keep the original line numbers,
  `moved_by` 0. The note must be shown against its old position, marked stale,
  never silently re-pointed.

The quote and digest in the result are the anchor's original ones in every case
except `"moved"`, where the block found is identical anyway.

Matching is exact, including indentation. Do not strip, do not normalise
whitespace, do not match partially: a note attached to code must not drift onto
code that merely resembles it.

## Style

Type hints, a one-line docstring per public function naming the rule it
implements, no `print()`. Follow HOUSE_STYLE.md, pasted below this contract when
the task is submitted.
