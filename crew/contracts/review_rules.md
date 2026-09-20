# Contract: review_rules.py — what a review must say before it counts

One self-contained Python module, `review_rules.py`. Pure decision logic for
CrossTalk's review desk: whether a human's verdict is complete, what it means for
the agent, and what the agent has to do next.

Kris's rule, which is the whole point: **"Approval needs no explanation, but
rejections and questions do."** A reject or a question without words is not a
review — it is a dead end that costs another round trip.

Allowed imports: `typing`, `re`. Nothing else. No files, no time, no printing.

## Public API

```python
DECISIONS = ("approve", "reject", "question", "defer")
NEEDS_NOTE = ("reject", "question", "defer")
MIN_NOTE_CHARS = 12

def validate(decision: str, note: str) -> list: ...
def is_complete(item: dict) -> bool: ...
def next_action(item: dict) -> str: ...
def summarize(items: list) -> dict: ...
def agent_digest(items: list) -> dict: ...
```

## validate(decision, note)

Returns a list of problem strings — **empty means the review is acceptable**.

1. `decision` not in `DECISIONS` -> one problem mentioning `"decision"`.
2. `decision` in `NEEDS_NOTE` and the note, stripped, is shorter than
   `MIN_NOTE_CHARS` -> one problem mentioning `"note"`. (Twelve characters is
   deliberately low: it stops `"no"` and `"bad"`, not genuine brevity.)
3. `decision == "approve"` and there is a note -> **no problem at all.** An
   approval may carry a note; it simply does not need one.
4. A note that is only whitespace counts as absent.

An unknown decision produces **only** the decision problem: the note rule
applies to `reject`, `question` and `defer`, and an unrecognised decision is
not one of them. When two problems ever do apply, the decision one comes first.

## is_complete(item)

`True` when `validate(item["decision"], item["note"])` is empty **and** the
decision is non-empty. A record with no decision yet is not complete (and not an
error). A missing `note` key counts as `""`; a missing `decision` key counts as
`""`.

## next_action(item)

One short lowercase string saying what happens next. Exactly these:

| condition | returns |
|---|---|
| no decision yet | `"wait for the human"` |
| `approve` | `"apply the work"` |
| `reject` | `"revise the work using the note"` |
| `question` | `"answer the question, then ask again"` |
| `defer` | `"leave it queued"` |
| a decision that needs a note and has none | `"ask the human for a reason"` |

The incomplete case wins over the decision case: a `reject` with no note returns
`"ask the human for a reason"`, not `"revise the work using the note"`.

## summarize(items)

```python
{"total": int, "pending": int, "approve": int, "reject": int,
 "question": int, "defer": int, "incomplete": int}
```

`pending` counts records with no decision. `incomplete` counts records that have
a decision but fail `validate`. Every key is present even when zero.
`summarize([])` gives all zeros.

## agent_digest(items)

What the agent reads to find out whether there is anything to do:

```python
{"needs_agent": bool,          # any complete approve / reject / question
 "waiting_on_human": int,      # records with no decision
 "waiting_on_agent": list,     # item_ids of complete approve/reject/question,
                               # in the order they appear
 "needs_human_again": list,    # item_ids of incomplete decisions
 "actions": dict}              # item_id -> next_action(item), for every record
```

A `defer` never makes `needs_agent` true and never appears in
`waiting_on_agent`: deferring is the human saying "not now".

Worked example the tests use:

```python
items = [
    {"item_id": "a", "decision": "approve", "note": ""},
    {"item_id": "b", "decision": "reject", "note": "the queue drops alerts"},
    {"item_id": "c", "decision": "reject", "note": "no"},
    {"item_id": "d", "decision": "", "note": ""},
    {"item_id": "e", "decision": "defer", "note": "after the release"},
]
agent_digest(items) == {
    "needs_agent": True,
    "waiting_on_human": 1,
    "waiting_on_agent": ["a", "b"],
    "needs_human_again": ["c"],
    "actions": {"a": "apply the work",
                "b": "revise the work using the note",
                "c": "ask the human for a reason",
                "d": "wait for the human",
                "e": "leave it queued"},
}
```

## Style

Type hints, a one-line docstring per public function naming the rule it
implements, no `print()`. Follow HOUSE_STYLE.md, pasted below this contract when
the task is submitted.
