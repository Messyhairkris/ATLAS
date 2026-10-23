# Contract: night_signatures.py - sorting the day's failed crew jobs

One self-contained Python module, `night_signatures.py`. Every night at 3 AM a script
(the "night shift") collects the crew jobs that failed that day and asks this module to
sort them: WHY did each fail (a category), and which failures are the same failure (a
signature). Repeated mechanical failures become candidates for an automatic fixer. The
module only computes on the dictionaries it is given: no files, no clock, no printing.

## Public API (all of these names must exist)

```python
CATEGORIES = ("provider", "stopped", "harness", "ceiling", "mechanical", "gate",
              "stuck", "unknown")

def head(text) -> str: ...
def classify(job: dict) -> list[tuple[str, str]]: ...
def group(jobs: list[dict], threshold: int = 3) -> list[dict]: ...
def advice(category: str) -> str: ...
```

Allowed imports: `re`. Nothing else.

## The job dictionary

Each job looks like this (any key may be missing; treat a missing or None value as empty):

```python
{"task_id": "job-20261023-124106-a483", "task_type": "code_task", "assigned_to": "Hoss",
 "status": "failed",
 "result": {"error": "...", "stop_reason": "budget_tokens",
            "steps": [{"rung": "hidden tests", "ok": False, "detail": "3 failed, 30 passed"}]}}
```

Defaults: a missing `task_type` or `assigned_to` is `"?"`; a missing `task_id` is `"?"`;
a missing `result` is `{}`; missing `steps` is `[]`; missing `rung` is `"?"`; missing
`detail` is `""`.

## Rule H - `head(text)`: a short, stable label

Apply in order:
1. Convert `text` with `str(text)` and keep only the FIRST line (everything before the
   first `"\n"`).
2. Replace every run of digits with a single `N` (`re.sub(r"\d+", "N", line)`).
3. Look for each of these three markers starting at index 20 (`line.find(marker, 20)`):
   `": "`, `", e.g."`, `" ("`. If one or more are found, cut the line at the SMALLEST
   index found (keep the text before it). A marker that starts before index 20 does not
   count.
4. Strip whitespace from both ends, keep at most the first 60 characters, then strip
   trailing whitespace again.

## Rule C - `classify(job)`: findings for one job, apply in order

1. If `job["status"]` is not exactly `"failed"`: return `[]`.
2. If `result["error"]` is a non-empty string (`str(...)`), it decides alone:
   a. it starts with `"stopped by the PA"` -> `[("stopped", f"{task_type}|stopped")]`
   b. it contains any PROVIDER marker (below) -> `[("provider", f"provider|{member}")]`
      (member = `assigned_to`)
   c. otherwise -> `[("harness", f"{task_type}|error|{head(error)}")]`
3. If `stop_reason` is a CEILING stop (below) ->
   `[("ceiling", f"{task_type}|ceiling|{stop_reason}|{member}")]`
4. Otherwise, one finding PER failed step (`ok` is falsy), in the order of `steps`:
   label = `head(detail)`; the finding is
   `("mechanical", f"{task_type}|{rung}|{label}")` when the rung is MECHANICAL (below), or
   when the rung is `"output"` and the label starts with `"bad output paths"`;
   otherwise `("gate", f"{task_type}|{rung}|{label}")`. If there was at least one
   finding, return them.
5. If `stop_reason` is a STUCK stop -> `[("stuck", f"{task_type}|stuck|{stop_reason}|{member}")]`
6. Otherwise -> `[("unknown", f"{task_type}|unknown")]`

PROVIDER markers (substring match): `HTTPStatusError`, `ReadTimeout`, `ConnectTimeout`,
`ConnectError`, `RemoteProtocolError`, `504 Gateway`, `502 Bad Gateway`, `503 Service`,
`429 Too Many`.

CEILING stops: `budget_requests`, `budget_tokens`, `output_truncated`, `empty_replies`,
`thinking_cut_off`.

STUCK stops: `no_progress`, `no_change`, `loop_repeat`, `contract_abandoned`.

MECHANICAL rungs: `frontmatter`, `ascii`, `quirks`.

## Rule G - `group(jobs, threshold=3)`

1. For every job, for every finding of `classify(job)`, add it to the entry for its
   `(category, signature)`. An entry is a dict with EXACTLY these keys:
   `category`, `signature`, `count` (number of findings), `members` (the members whose
   jobs gave a finding - each once), `job_ids` (each job id once, in the order first
   seen), `candidate`.
2. `members` is sorted alphabetically. `job_ids` keeps first-seen order.
3. `candidate` is `True` only when the category is `"mechanical"` and `count >= threshold`.
4. Sort the entries by: the category's position in `CATEGORIES`, then `count` from high
   to low, then `signature` alphabetically. Return the list (empty input -> `[]`).

## Rule A - `advice(category)`

Exact text per category; any other value gives the `"unknown"` text.

| category | advice |
|---|---|
| provider | `the member's endpoint failed; relay or wait, nothing to fix in the work` |
| stopped | `stopped by a person; nothing to fix` |
| harness | `our harness raised an error; read the traceback in the job` |
| ceiling | `our budget ended the job; check the member's ceilings before blaming them` |
| mechanical | `a format miss a program can repair; candidate for a zero-token fixer` |
| gate | `a gate refused the content; needs a reader (model error or contract wording)` |
| stuck | `the member looped without progress; rescope the task or relay it sooner` |
| unknown | `failed with no recorded reason; read the job` |

## Worked examples

`head`:

| text | head(text) |
|---|---|
| `"cited but never opened this job: backend/main.rs"` | `"cited but never opened this job"` |
| `"claims not found in what you read: '12' in: - x"` | `"claims not found in what you read"` |
| `"tests_failed: 3 failed\nThe hidden tests fail."` | `"tests_failed: N failed"` (the `": "` is at index 12, before 20) |
| `"compile_failed: error[E0308]: mismatched types"` | `"compile_failed: error[EN]"` |
| `"bad output paths: python (not a declared output)"` | `"bad output paths: python"` |
| `"4 item line(s) without a citation, e.g. - **Missing"` | `"N item line(s) without a citation"` |
| `"no YAML frontmatter (--- ... ---) at top"` | unchanged: its `" ("` starts at index 19 |
| `"2026-10-23 at 12:41"` | `"N-N-N at N:N"` |
| `""` | `""` |

`classify` (all with `status: "failed"`, task_type `code_task`, member `Hoss` unless shown):

(Signatures contain `|` characters, so these are a list, not a table.)

- `error: "stopped by the PA on 2026-10-20: x"`
  -> `[("stopped", "code_task|stopped")]`
- `error: "ReadTimeout: The read operation timed out"`, member Larry
  -> `[("provider", "provider|Larry")]`
- `error: "ValueError: bad"`, plus a stop_reason and failed steps
  -> `[("harness", "code_task|error|ValueError: bad")]` (the error decides alone)
- `stop_reason: "budget_tokens"`, member Qwen, plus failed steps
  -> `[("ceiling", "code_task|ceiling|budget_tokens|Qwen")]`
- steps: `frontmatter` failed with `"no YAML frontmatter (--- ... ---) at top"`
  -> `[("mechanical", "code_task|frontmatter|no YAML frontmatter (--- ... ---) at top")]`
- steps: `output` failed with `"bad output paths: python (not a declared output)"`
  -> `[("mechanical", "code_task|output|bad output paths: python")]`
- steps: `output` failed with `"missing output: a.py"`
  -> `[("gate", "code_task|output|missing output: a.py")]`
- `stop_reason: "no_change"`, no failed step
  -> `[("stuck", "code_task|stuck|no_change|Hoss")]`
- `stop_reason: "submitted"`, no failed step
  -> `[("unknown", "code_task|unknown")]`
- `status: "completed"` -> `[]`

`group`: two provider failures by Larry (jobs `a`, `b`) and one `budget_tokens` stop by
Qwen (job `c`) give

```python
[{"category": "provider", "signature": "provider|Larry", "count": 2,
  "members": ["Larry"], "job_ids": ["a", "b"], "candidate": False},
 {"category": "ceiling", "signature": "code_task|ceiling|budget_tokens|Qwen", "count": 1,
  "members": ["Qwen"], "job_ids": ["c"], "candidate": False}]
```

Three jobs failing the `frontmatter` rung with the same detail give one `mechanical`
entry with `count` 3 and `candidate` True (False when `threshold=4`).
