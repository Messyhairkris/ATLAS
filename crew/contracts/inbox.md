# Contract: inbox.py - the cards Kris lands on in The Crew

Part of the crew harness. The Crew window opens on an Inbox: one list of everything that needs
Kris or happened while he was away - a stuck member's question, Review Desk items, reminders,
failed jobs, campaigns nobody has touched for days, the night shift's fixer candidates, and the
jobs that finished since he last looked. The harness gathers the inputs; this module is the pure
part that turns them into ordered cards. No I/O, no clock (the caller passes `now`).

## Public API

```python
RANKS = {"question": 0, "decide": 1, "reminder": 2, "failed": 3, "stale_campaign": 4,
         "fixer": 5, "try": 6, "finished": 7, "read": 8}

def cards(desk: list[dict], jobs: list[dict], campaigns: list[dict], fired: list[dict],
          night: dict | None, now: datetime, seen_at: str, stale_hours: int = 48) -> list[dict]: ...
def counts(cards: list[dict]) -> dict[str, int]: ...
```

Allowed imports: `datetime`. Nothing else. Spell every name exactly as above.

Times are ISO strings like `2026-10-26T09:05:00` (seconds optional). `seen_at` is when Kris last
looked (`""` = never: everything counts as new). "After seen_at" means the time string is
non-empty and `> seen_at` as plain strings (`""` for seen_at makes every non-empty time after).

A card is `{"kind": str, "title": str, "detail": str, "ref": str, "when": str}`.

## The rules (each input item gives at most one card)

1. **question** - a job with `status == "review"`, a truthy `question` and a falsy `asked`:
   title = job `title`; detail = `question["question"]`, plus `" | " + " / ".join(options)`
   when `question["options"]` is a non-empty list; ref = `task_id`; when = `finished_at` or "".
   (Always shown, new or not.)
2. **desk** items waiting - `decision` is `""` (or missing) and `state != "closed"`: kind is the
   item's `kind` (`decide`, `try` or `read`; anything else counts as `decide`); title = `title`;
   detail = `""`; ref = `item_id`; when = `added` or "". (Always shown.)
3. **reminder** - a `fired` entry with `kind == "reminder"` and `fired_at` after seen_at:
   title = `title`; detail = `"at " + fired_at[11:16]`; ref = `id`; when = `fired_at`.
4. **failed** - a job with `status == "failed"` and `finished_at` after seen_at: title = job
   title; detail = `assigned_to + ": " + result["stop_reason"]` (result may be missing: use
   `"failed"` as the stop reason; a missing assigned_to is `"?"`); ref = `task_id`;
   when = `finished_at`.
5. **stale_campaign** - a campaign with `state == "active"` whose `updated` is more than
   `stale_hours` hours before `now`: title = `name`; detail = `"no change for N h"` with N the
   whole number of hours (floor); ref = `name`; when = `updated`. A campaign without a
   parseable `updated` is skipped. (Always shown while it is stale.)
6. **fixer** - when `night` is not None and `night["at"]` is after seen_at: one card per entry of
   `night["fixer_candidates"]` (missing = none): title = `signature`; detail =
   `f"{count} failures, e.g. {example_job}"`; ref = `example_job`; when = `night["at"]`.
7. **finished** - a job with status `review` or `completed`, NOT a question card, and
   `finished_at` after seen_at: title = job title; detail = `assigned_to + " - " + status`;
   ref = `task_id`; when = `finished_at`.

A job title that is missing or empty becomes its `task_id`. Other jobs give no card.

## Order and counts

Sort by `RANKS[kind]`, then by `when` newest first (a plain string comparison; `""` sorts
last within its kind), then by `title`. `counts(cards)` -> `{kind: number}` for the kinds present.

## Worked examples (the hidden tests walk every row)

With `now = datetime(2026, 10, 26, 12, 0)` and `seen_at = "2026-10-26T08:00"`:

| input | card |
|---|---|
| job `{"task_id": "j1", "title": "Digest", "status": "review", "question": {"question": "Which run?", "options": ["a", "b"]}, "finished_at": "2026-10-25T10:00"}` | `{"kind": "question", "title": "Digest", "detail": "Which run? \| a / b", "ref": "j1", "when": "2026-10-25T10:00"}` |
| same job with `"asked": True` and finished_at `2026-10-26T09:00` | a `finished` card (`detail` `"? - review"`) |
| job `{"task_id": "j2", "status": "failed", "assigned_to": "Qwen", "result": {"stop_reason": "budget_tokens"}, "finished_at": "2026-10-26T09:30"}` | `failed`, title `j2`, detail `"Qwen: budget_tokens"` |
| same job finished `2026-10-26T07:00` | no card (before seen_at) |
| desk `{"item_id": "d1", "title": "TRY - pass", "kind": "try", "decision": ""}` | `try`, title `TRY - pass`, ref `d1`, when `""` |
| desk `{"item_id": "d2", "title": "x", "kind": "decide", "decision": "approve"}` | no card |
| desk `{"item_id": "d3", "title": "y", "kind": "odd", "state": "open"}` | `decide` |
| campaign `{"name": "outline", "state": "active", "updated": "2026-10-23T11:30:00"}` | `stale_campaign`, detail `"no change for 72 h"` |
| campaign `{"name": "fresh", "state": "active", "updated": "2026-10-26T11:00"}` | no card |
| fired `{"id": "s-1", "title": "Stand-up", "kind": "reminder", "fired_at": "2026-10-26T09:00:00"}` | `reminder`, detail `"at 09:00"` |
| night `{"at": "2026-10-26T03:00", "fixer_candidates": [{"signature": "budget_tokens x3", "count": 3, "example_job": "j7"}]}` with seen_at `"2026-10-25T20:00"` | `fixer`, detail `"3 failures, e.g. j7"`, ref `j7` |
