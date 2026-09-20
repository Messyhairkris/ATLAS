# Contract: review_index.py — the review queue's index file

One self-contained Python module, `review_index.py`. It converts between review
records and the **INI text** that stores them, and nothing else: no file access,
no timestamps of its own, no GUI.

This is the index behind CrossTalk's review desk. Kris: *"I could approve and
write them with the item, indexed somehow maybe an ini?"* An INI file is chosen
because a human can open it in Notepad and read the whole queue, and because a
half-written file is obvious rather than corrupt.

Allowed imports: `configparser`, `typing`, `re`. Nothing else. **The caller reads
and writes the file** — you are given text and you return text.

## The record

A review item is a dict. These keys always exist:

| key | type | meaning |
|---|---|---|
| `item_id` | `str` | unique, e.g. `"job-20260920-042420-dc05:test_speech_queue.py"` |
| `title` | `str` | what the human sees in the list |
| `path` | `str` | the file to open for review |
| `origin` | `str` | where it came from, e.g. `"crew:code_tests:Hoss"` |
| `state` | `str` | one of `STATES` |
| `decision` | `str` | `""` until a human decides; then one of `DECISIONS` |
| `note` | `str` | the human's words; `""` when there are none |
| `anchor` | `str` | `""`, or `"L12-L18"`-style location inside the file |
| `decided_at` | `str` | `""` or an ISO timestamp the caller supplies |

## Public API

```python
STATES = ("pending", "decided", "answered", "closed")
DECISIONS = ("approve", "reject", "question", "defer")
FIELDS = ("item_id", "title", "path", "origin", "state", "decision", "note",
          "anchor", "decided_at")

def new_item(item_id: str, title: str, path: str, origin: str = "",
             anchor: str = "") -> dict: ...
def render(items: list) -> str: ...
def parse(text: str) -> list: ...
def merge(existing: list, incoming: list) -> list: ...
def pending(items: list) -> list: ...
def find(items: list, item_id: str) -> dict | None: ...
```

## new_item(...)

Returns a complete record: the arguments as given, `state="pending"`,
`decision=""`, `note=""`, `decided_at=""`, and `anchor` as passed. An empty
`item_id` or an empty `title` raises `ValueError`.

## render(items)

Returns INI text. One section per item, named by `item_id`. Every field in
`FIELDS` except `item_id` appears as a key, in the order `FIELDS` gives, even
when its value is empty. A record whose `state` is not in `STATES`, or whose
`decision` is neither `""` nor in `DECISIONS`, raises `ValueError`.

A **newline inside a note** must survive a round trip. Write it as the escape
`\n` (backslash then n) rather than a real line break, because a real line break
would end the INI value.

`render([])` returns `""`.

## parse(text)

The inverse. Returns a list of complete records, in the order the sections
appear, `item_id` taken from the section name, any missing key defaulting to
`""` (and `state` defaulting to `"pending"` when absent or empty). `\n` in a note
becomes a real newline again. Text that `configparser` cannot read raises
`ValueError`.

`parse("")` returns `[]`. Unknown keys in a section are ignored, not an error:
a human editing the file by hand may leave a comment key behind.

**Round trip:** for any list of valid records, `parse(render(items)) == items`.
The tests check this with a note containing a newline, an `=` sign and a `;`.

## merge(existing, incoming)

Adds items that are new, keeps the ones already there, and **never overwrites a
human decision**. For an `item_id` present in both:

- if the existing record has a non-empty `decision`, the existing record wins
  entirely;
- otherwise fields from `incoming` that are non-empty replace the existing ones,
  and the existing `state` is kept if `incoming`'s is empty.

Order: the existing items first, in their order, then genuinely new ones in
`incoming` order. Neither input list is modified.

## pending(items)

The records whose `state` is `"pending"`, in order. `[]` when there are none.

## find(items, item_id)

The record with that id, or `None`.

## Style

Type hints, a one-line docstring per public function naming the rule it
implements, no `print()`. Follow HOUSE_STYLE.md, which is pasted below this
contract when the task is submitted.
