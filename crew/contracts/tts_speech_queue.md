# Contract: speech_queue.py — the order things get said in, and stopping them

One self-contained Python module, `speech_queue.py`. It holds the **queue** that
sits between VtoT and whatever actually makes sound. It never makes sound
itself: the caller passes a `speak_fn` in.

Two decisions from TTS_SPEC_DRAFT.md drive it. Speech must be cancellable by a
hotkey while dictation is live ("Cancel playback by stopping via another hotkey
or physical button"), and an alert must not wait behind a long read-back.

**You may import `verbalize`** — the module another crew member already had
accepted. It is on the path when your code is tested. Do not rewrite it, do not
copy its code, and do not re-implement punctuation naming yourself.

## Public API

```python
PRIORITIES = ("alert", "normal")
MAX_PENDING = 32

@dataclass
class Utterance:
    id: int
    text: str            # what the voice will say, already verbalized
    priority: str

class SpeechQueue:
    def __init__(self, level: str = "normal", max_pending: int = MAX_PENDING) -> None: ...
    @property
    def pending(self) -> list: ...
    def enqueue(self, text: str, priority: str = "normal"): ...
    def next_utterance(self): ...
    def cancel_current(self) -> bool: ...
    def cancel_all(self) -> int: ...
    def speak_all(self, speak_fn) -> list: ...
```

Allowed imports: `dataclasses`, `typing`, and `verbalize`. Nothing else.

## Construction

`SpeechQueue(level="normal", max_pending=MAX_PENDING)`. Keep `level` on the
instance as `self.level`. Also expose `self.current` (the utterance being spoken,
or `None`), `self.dropped` (an int, starts at 0) and `self.cancelled` (an int,
starts at 0).

An unknown `level` raises `ValueError` — let `verbalize` decide that by calling
it, rather than keeping your own list of levels.

## enqueue(text, priority="normal")

1. `priority` not in `PRIORITIES` raises `ValueError`.
2. The text is turned into speech text with `verbalize.verbalize(text, self.level)`.
3. If the result is empty (which is what `level="off"` always gives, and what
   whitespace-only text gives), **nothing is queued** and `enqueue` returns
   `None`.
4. Otherwise an `Utterance` is created with the next id — ids start at **1** and
   count up for the life of the queue, never reused — and queued:
   - `"normal"` goes after everything already queued;
   - `"alert"` goes after any alerts already queued but **before every normal
     one**, so an alert overtakes a long read-back.
5. Returns the `Utterance`.
6. If the queue already holds `max_pending` utterances, drop the **oldest normal
     one** to make room and add 1 to `self.dropped`. If every queued utterance is
     an alert, drop nothing, queue nothing, and return `None` (alerts are never
     discarded).

## pending

A list of the queued `Utterance` objects in the order they will be spoken. It
does not include `self.current`.

## next_utterance()

Removes and returns the first pending utterance, setting `self.current` to it.
Returns `None` and sets `self.current = None` when nothing is pending.

## cancel_current()

If `self.current` is not `None`, clear it, add 1 to `self.cancelled`, and return
`True`. Otherwise return `False`. (This is the hotkey: stop what is being said
now, keep what is queued.)

## cancel_all()

Clear the pending queue **and** the current utterance. Add the number cleared to
`self.cancelled` and return that number.

## speak_all(speak_fn)

Speak everything queued, in order, and return the list of ids spoken.

- for each utterance: set `self.current`, call `speak_fn(utterance)`;
- if `speak_fn` returns `False` (exactly `False`, not any falsy value), stop
  immediately: that utterance **counts as spoken**, and whatever is still pending
  stays pending. This is how a stop request interrupts a run.
- any other return value continues;
- when the queue empties, `self.current` is `None`.

## Worked example

```python
q = SpeechQueue(level="verbatim")
q.enqueue("Hello, world.")              # id 1, text "Hello comma world period"
q.enqueue("headset lost", "alert")      # id 2, jumps ahead of id 1
[u.id for u in q.pending]               # [2, 1]
q.speak_all(lambda u: True)             # [2, 1]
```

## Style

Type hints, a one-line docstring per public method naming the rule it implements,
no `print()`. Write the complete file.
