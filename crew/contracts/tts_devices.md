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
ALERT_VOLUME = 65            # an alert in a headset; also the headset ceiling
HEADSET_CEILING = 65         # measured: 70 and 100 were painful in one ear
SPEAKER_CEILING = 100        # speakers compete with room noise
SPEAKER_FLOOR = 1            # a speaker channel is never silently muted
HEADSET_WORDS = (...)        # tuple of lowercase substrings, see below
SPEAKER_WORDS = (...)        # tuple of lowercase substrings, see below

def classify(name: str) -> str: ...
def ceiling_for(kind: str) -> int: ...
def clamp_volume(value, kind: str = HEADSET) -> int: ...

@dataclass
class Policy:
    allow_speakers_this_session: bool = False
    avoid_hands_free: bool = True
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

## ceiling_for(kind)

The loudest volume allowed for that kind of device:

| kind | ceiling | why |
|---|---|---|
| `HEADSET` | `HEADSET_CEILING` (65) | measured in one ear: 70 and 100 were painful |
| `SPEAKERS` | `SPEAKER_CEILING` (100) | speakers must carry over room noise |
| `UNKNOWN`, or anything else | `HEADSET_CEILING` | the quiet one is the safe default: a device we cannot identify might be on someone's head |

## clamp_volume(value, kind=HEADSET)

Returns an `int` inside the range for that kind of device.

- above `ceiling_for(kind)` becomes the ceiling;
- a float is rounded to the nearest int;
- anything that is not a number (including `None` and `"loud"`) returns
  `DEFAULT_VOLUME` **clamped to that kind's range**;
- the floor depends on the device: a **headset** may go to 0 (the user can mute
  it), while **speakers** floor at `SPEAKER_FLOOR` (1). A speaker channel you
  deliberately chose in order to be heard is never silently muted; if the user
  wants silence there, they turn speech off, which is a different decision.

Examples the tests use:

| call | result |
|---|---|
| `clamp_volume(45)` | 45 |
| `clamp_volume(100)` | 65 |
| `clamp_volume(100, SPEAKERS)` | 100 |
| `clamp_volume(120, SPEAKERS)` | 100 |
| `clamp_volume(0, SPEAKERS)` | 1 |
| `clamp_volume(0)` | 0 |
| `clamp_volume(-5, SPEAKERS)` | 1 |
| `clamp_volume(None, SPEAKERS)` | 45 |
| `clamp_volume(70, UNKNOWN)` | 65 |

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
2. **Headset by default, and never its hands-free endpoint.** Among devices that
   `classify` as `HEADSET`:
   - when `policy.avoid_hands_free` is true (the default), **discard** any whose
     lowercase name contains `"hands-free"` or `"hands free"` - unless that would
     leave nothing, in which case the last one is used and `reason` contains
     `"hands-free"` as a warning.
     (Measured on the real headset, 2026-09-20: the hands-free endpoint speaks one
     utterance and then never returns, and it wedges the radio for BOTH endpoints
     until the headset is reconnected. A Bluetooth headset carries one profile at a
     time. `mic_live` does not change this - there is no safe way to speak through
     hands-free.)
   - among what remains, prefer one whose lowercase name contains `"stereo"`;
     otherwise take the lowest `index`. `reason` contains `"stereo"` when that
     preference decided it. On a mono headset the A2DP endpoint is still the one
     Windows calls "Stereo"; the word describes the Bluetooth profile, not the
     number of speakers.
   - `speak=True`, `play_fallback_tone=False`, and `reason` contains `"headset"`.
   - `mic_live` is still an argument, and still reported: when it is true, `reason`
     also contains `"while dictating"`, because whether speech disturbs capture on
     this profile is still an open question in the spec.
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
