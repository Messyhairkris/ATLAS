# Contract: devices.py — where VtoT's speech goes

One self-contained Python module, `devices.py`, holding the **decision logic**
for VtoT's text-to-speech output device. It touches no hardware: the caller
passes the device list in. That is what makes it testable, and it is not
negotiable.

Everything below comes from the project's decisions (TTS_SPEC_DRAFT.md section
2), including the volume numbers, which were measured on the real headset.

## Public API (all of these names must exist)

```python
HEADSET = "headset"
SPEAKERS = "speakers"
UNKNOWN = "unknown"
DEFAULT_VOLUME = 45          # measured as comfortable in a single-ear headset
ALERT_VOLUME = 65            # the ceiling; only for an emergency alert
HEADSET_WORDS = (...)        # tuple of lowercase substrings, see below
SPEAKER_WORDS = (...)        # tuple of lowercase substrings, see below

def classify(name: str) -> str: ...
def clamp_volume(value) -> int: ...

@dataclass
class Policy:
    allow_speakers_this_session: bool = False
    prefer_hands_free_while_live: bool = True
    override_device: str | None = None

def clear_session(policy: Policy) -> Policy: ...
def choose(devices, mic_live: bool = False, policy: Policy | None = None) -> dict: ...
```

Allowed imports: `dataclasses`, `typing`, `re`, `enum`. Nothing else.

## classify(name)

Case-insensitive substring matching on the device name as Windows spells it.

- `HEADSET_WORDS` must contain at least: `"headset"`, `"headphone"`, `"earphone"`,
  `"earbud"`, `"airpod"`, `"hands-free"`, `"hands free"`
- `SPEAKER_WORDS` must contain at least: `"speaker"`, `"hdmi"`, `"display"`,
  `"monitor"`, `"digital output"`
- Returns `HEADSET` if a headset word matches, else `SPEAKERS` if a speaker word
  matches, else `UNKNOWN`. A headset word wins if both match.

Examples, from the real machine:

| name | result |
|---|---|
| `"Headset (M98 Hands-Free AG Audio)"` | `"headset"` |
| `"Headphones (M98 Stereo)"` | `"headset"` |
| `"Speakers (3- High Definition Audio Device)"` | `"speakers"` |
| `"Digital Output (S/PDIF)"` | `"speakers"` |
| `"Line 1 (Virtual Audio Cable)"` | `"unknown"` |

## clamp_volume(value)

Returns an `int` in `0..ALERT_VOLUME`. Below 0 becomes 0, above `ALERT_VOLUME`
becomes `ALERT_VOLUME`, a float is rounded to the nearest int, and anything that
is not a number (including `None` and `"loud"`) returns `DEFAULT_VOLUME`. The
ceiling exists because 70 and 100 were both judged too loud in a single-ear
headset; nothing may exceed 65.

## clear_session(policy)

Returns a **new** `Policy` that is the same except `allow_speakers_this_session`
is `False`. It must not mutate the policy it was given. This is what runs when
VtoT next starts: permission to use the speakers never survives a session.

## choose(devices, mic_live=False, policy=None)

`devices` is a list of dicts, each `{"index": int, "name": str}`, in the order
Windows reported them. `policy=None` means `Policy()` (the defaults).

Returns a dict with exactly these keys:

```python
{"device": <the chosen device dict, or None>,
 "speak": <bool: may speech play at all>,
 "play_fallback_tone": <bool: play the single tone from the sounds folder>,
 "reason": "<short lowercase explanation>"}
```

Rules, in this order:

1. **Override wins.** If `policy.override_device` is set and some device's name
   equals it exactly, choose that device, `speak=True`,
   `play_fallback_tone=False`, `reason` contains `"override"`.
   If the named device is **not** present, ignore the override and carry on with
   the rules below.
2. **Headset by default.** Among devices that `classify` as `HEADSET`:
   - if `mic_live` and `policy.prefer_hands_free_while_live`, prefer one whose
     lowercase name contains `"hands-free"` or `"hands free"`; if none does, take
     the lowest `index`. `reason` contains `"hands-free"` when that preference
     decided it.
     (Why: the hands-free profile coexists with the headset microphone. Selecting
     the stereo endpoint while dictating can make Windows switch profiles and
     damage capture.)
   - if not `mic_live`, prefer one whose lowercase name contains `"stereo"`; if
     none does, take the lowest `index`. `reason` contains `"stereo"` when that
     preference decided it.
   - `speak=True`, `play_fallback_tone=False`, and `reason` contains `"headset"`.
3. **No headset, speakers allowed.** If no device classifies as `HEADSET` and
   `policy.allow_speakers_this_session` is true, choose the lowest-index device
   that classifies as `SPEAKERS`; `speak=True`, `play_fallback_tone=False`,
   `reason` contains `"speakers"` and `"session"`.
4. **No headset, speakers not allowed.** `device=None`, `speak=False`,
   `play_fallback_tone=True`, and `reason` contains `"no headset"`. This is the
   spec's rule: speech stops rather than moving to the speakers, and one tone
   says so.
5. **Empty list** (`devices == []`) is rule 4 as well: nothing to speak through.

An `UNKNOWN` device is never chosen automatically. It can only be chosen through
`policy.override_device`, because the user named it.

## Style

Type hints on every public function, a one-line docstring on each explaining the
rule it implements, and no `print()`. Write the complete file; it must run as-is.
