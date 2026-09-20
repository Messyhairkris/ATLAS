# Contract: profiles.py — the headsets VtoT remembers

One self-contained Python module, `profiles.py`, holding the **memory** of the
audio devices a user speaks through: which ones are known, what volumes each one
is set to, which of those are locked against change, and whether a device that is
missing right now is worth asking Windows to reconnect.

It touches no hardware and no clock. The caller passes in the device list and the
current time. That is what makes it testable, and it is not negotiable.

Kris asked for it in these words:

> "Its possible folks might hook other types of headsets, wired and bluetooth, so
> the settings should be able to hold a few varieties and volume sets and locks.
> It would be nice to be able to reconnect a previously paired headset as well."

It builds on `devices.py`, which is already accepted and in use. **Import it and
use it** — do not re-implement classification or clamping:

```python
from devices import classify, clamp_volume, HEADSET, SPEAKERS, UNKNOWN
```

## Public API (all of these names must exist)

```python
LINKS = ("bluetooth", "wired", "builtin", "unknown")
PURPOSES = ("speech", "alert")
BLUETOOTH_WORDS = (...)      # lowercase substrings, see below
WIRED_WORDS = (...)          # lowercase substrings, see below
RECONNECT_COOLDOWN_S = 30
DEFAULT_SPEECH = 45
DEFAULT_ALERT = 65

def classify_link(name: str) -> str: ...
def new_profile(name: str, kind: str = "", link: str = "",
                speech: int = DEFAULT_SPEECH, alert: int = DEFAULT_ALERT,
                locked: bool = False, last_used: float = 0.0) -> dict: ...
def volume_for(profile: dict, purpose: str) -> int: ...
def set_volume(profile: dict, purpose: str, value) -> dict: ...
def set_lock(profile: dict, locked: bool) -> dict: ...
def remember(profiles: list, name: str, now: float = 0.0) -> list: ...
def known(profiles: list) -> list: ...
def find(profiles: list, name: str) -> dict | None: ...
def present(profiles: list, devices: list) -> list: ...
def missing(profiles: list, devices: list) -> list: ...
def prefer(profiles: list, devices: list) -> dict: ...
def reconnect_plan(profile: dict, devices: list, now: float = 0.0,
                   last_attempt: float = 0.0,
                   cooldown_s: int = RECONNECT_COOLDOWN_S) -> dict: ...
def dump(profiles: list) -> str: ...
def load(text: str) -> list: ...
```

Allowed imports: `json`, `typing`, `re`, plus `devices` as shown above. Nothing
else.

A profile is a plain `dict`, never a class: it is written to a settings file and
read back, so it must be JSON all the way down. Every function that changes a
profile returns a **new dict** and leaves the one it was given untouched.

## The device list

Everywhere `devices` appears it is a list of dicts as Windows reported them,
`{"index": int, "name": str}` — the same shape `devices.choose` takes. An empty
list means nothing is plugged in or paired right now.

## classify_link(name)

Case-insensitive substring matching on the device name.

- `BLUETOOTH_WORDS` must contain at least: `"bluetooth"`, `"hands-free"`,
  `"hands free"`, `"stereo"`, `"a2dp"`, `"airpod"`, `"wireless"`
- `WIRED_WORDS` must contain at least: `"usb"`, `"jack"`, `"3.5"`, `"analog"`,
  `"line in"`, `"line 1"`, `"wired"`
- Returns `"bluetooth"` if a bluetooth word matches, else `"wired"` if a wired
  word matches, else `"builtin"` if the name contains `"realtek"`,
  `"high definition audio"`, `"internal"` or `"built-in"`, else `"unknown"`.
- A bluetooth word wins if both match: a wireless headset that also says USB is
  the dongle, and the thing that can be reconnected is still the headset.

| name | link |
|---|---|
| `"Headphones (M98 Stereo)"` | `"bluetooth"` |
| `"Headset (M98 Hands-Free AG Audio)"` | `"bluetooth"` |
| `"Speakers (USB Audio Device)"` | `"wired"` |
| `"Speakers (3- High Definition Audio Device)"` | `"builtin"` |
| `"Line 1 (Virtual Audio Cable)"` | `"wired"` |
| `"SteelSeries Arctis"` | `"unknown"` |

## new_profile(...)

- `name` must be a string with something in it. Empty, whitespace-only (`"   "`), or not a string at all is a `ValueError` - a device whose name is three spaces cannot be found again.
- `kind` defaults to `classify(name)` from `devices.py`; if it is given but is not
  one of `HEADSET`, `SPEAKERS`, `UNKNOWN`, that is a `ValueError`.
- `link` defaults to `classify_link(name)`; if given but not in `LINKS`, a
  `ValueError`.
- `speech` and `alert` are each put through `clamp_volume(value, kind)`, so a
  headset profile can never hold 100 and a speaker profile can never hold 0.
- Returns a dict with exactly these keys, in this order: `name`, `kind`, `link`,
  `volumes`, `locked`, `last_used` — where `volumes` is
  `{"speech": int, "alert": int}`.

## volume_for(profile, purpose)

The stored volume for that purpose, put through `clamp_volume` again on the way
out (a settings file edited by hand may hold anything). An unknown `purpose` is a
`ValueError`. A missing or non-numeric stored value gives the default for that
purpose, clamped.

## set_volume(profile, purpose, value)

Returns a **new** profile.

- An unknown `purpose` is a `ValueError`.
- **A locked profile is never changed**: the returned profile equals the one given.
  This is the lock Kris asked for — the app raising a volume on its own must not
  be able to touch a setting the user has pinned.
- Otherwise the new value is `clamp_volume(value, profile["kind"])`.

## set_lock(profile, locked)

Returns a new profile with `locked` set to `bool(locked)`. Locking is always
allowed, and so is unlocking: the lock protects volumes, not itself.

## remember(profiles, name, now=0.0)

The list of profiles with this device recorded as the most recently used.

- If no profile has that name, one is appended by `new_profile(name)`.
- If one does, its `last_used` becomes `now` and **nothing else about it changes**
  — not its volumes, not its lock. A user's settings survive re-plugging the
  device.
- Returns a new list of new dicts; the list passed in is not mutated.
- An empty, whitespace-only or non-string `name` is a `ValueError`, as in `new_profile`.

## known(profiles) / find(profiles, name)

- `known` returns the profiles sorted by `last_used`, **most recent first**, with
  ties broken by name so the order is never arbitrary.
- `find` returns the profile with that name (exact match) or `None`.

## present(profiles, devices) / missing(profiles, devices)

- `present` returns `[{"profile": <profile>, "device": <device dict>}, ...]` for
  every known profile whose name matches a device currently in the list, in
  `known` order.
- `missing` returns the profiles, in `known` order, that are **not** in the list
  and have been used at least once (`last_used > 0`). A profile that has never
  been used is not "missing"; it was only ever a name.

## prefer(profiles, devices)

Which device to speak through now. Returns a dict with exactly these keys:

```python
{"profile": <profile dict, or None>,
 "device":  <device dict, or None>,
 "reason":  "<short lowercase explanation>"}
```

Rules, in this order:

1. **The one he used last, if it is here.** The first entry of
   `present(profiles, devices)` wins; `reason` contains `"remembered"`.
2. **Otherwise a headset that is here but unknown to us.** The lowest-index device
   whose `classify` is `HEADSET`; `profile` is `None`, because we have never seen
   it and the caller decides whether to remember it. `reason` contains
   `"new headset"`.
3. **Otherwise nothing.** `profile` and `device` are both `None`, and `reason`
   contains `"nothing known"`. Speakers are never chosen here: that permission
   belongs to `devices.choose`, and this module does not overrule it.

## reconnect_plan(profile, devices, now=0.0, last_attempt=0.0, cooldown_s=30)

Whether it is worth asking Windows to bring a paired device back. Returns a dict
with exactly these keys:

```python
{"name": <the profile's name>,
 "link": <the profile's link>,
 "should_try": <bool>,
 "wait_s": <int: 0, or how long until it is worth trying again>,
 "reason": "<short lowercase explanation>"}
```

Rules, in this order:

1. The device is in `devices` now → `should_try=False`, `wait_s=0`, `reason`
   contains `"already here"`.
2. `profile["link"]` is not `"bluetooth"` → `should_try=False`, `wait_s=0`,
   `reason` contains `"plug it in"`. A cable is the user's job; only a radio link
   can be reconnected by software.
3. `last_attempt > 0` and `now - last_attempt < cooldown_s` → `should_try=False`,
   `wait_s` is the whole seconds remaining, rounded **up**, and `reason` contains
   `"tried"`. Retrying a pairing in a tight loop is how you wedge a Bluetooth
   radio, which this project has already measured once.
4. Otherwise `should_try=True`, `wait_s=0`, `reason` contains `"reconnect"`.

The module never performs the reconnection: it says whether to, and the caller
does it.

## dump(profiles) / load(text)

The round trip through a settings file.

- `dump` returns JSON text: a list of profiles, in the order given, indented by 2
  so a human can read it in Notepad.
- `load` parses it back. Text that is not JSON, or JSON that is not a list, is a
  `ValueError`.
- `load` is forgiving about content, because a human may have edited it: each
  entry is normalised through `new_profile`, unknown keys are dropped, missing
  keys take their defaults, and an entry without a usable `name` is **skipped**
  rather than raising.
- `load(dump(profiles))` must give back the same profiles, including locks and
  `last_used`.

## Style

See `HOUSE_STYLE.md`, which is part of this contract. In short: type hints on
every public function, a one-line docstring saying which rule it implements, no
`print()`, no module-level side effects, lines under 88 characters, and modern
type syntax (`list[dict]`, `str | None`, never `typing.List`). Write the complete
file; it must run as-is.
