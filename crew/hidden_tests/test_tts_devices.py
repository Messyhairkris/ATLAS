"""Hidden tests for devices.py. The author never sees these.

Every assertion traces to a line of crew/contracts/tts_devices.md, which traces
to a decision in TTS_SPEC_DRAFT.md section 2.
"""

import dataclasses

import pytest

import devices as d

REAL = [
    {"index": 0, "name": "Speakers (3- High Definition Audio Device)"},
    {"index": 1, "name": "Headset (M98 Hands-Free AG Audio)"},
    {"index": 2, "name": "Headphones (M98 Stereo)"},
]
SPEAKERS_ONLY = [REAL[0], {"index": 1, "name": "Digital Output (S/PDIF)"}]


def test_constants_are_the_measured_numbers():
    assert d.DEFAULT_VOLUME == 45
    assert d.ALERT_VOLUME == 65
    assert (d.HEADSET, d.SPEAKERS, d.UNKNOWN) == ("headset", "speakers", "unknown")


def test_word_lists_cover_the_required_terms():
    for word in ("headset", "headphone", "earphone", "earbud", "airpod",
                 "hands-free", "hands free"):
        assert word in d.HEADSET_WORDS, word
    for word in ("speaker", "hdmi", "display", "monitor", "digital output"):
        assert word in d.SPEAKER_WORDS, word


@pytest.mark.parametrize("name,kind", [
    ("Headset (M98 Hands-Free AG Audio)", "headset"),
    ("Headphones (M98 Stereo)", "headset"),
    ("HEADPHONES (SHOUTING)", "headset"),
    ("Speakers (3- High Definition Audio Device)", "speakers"),
    ("Digital Output (S/PDIF)", "speakers"),
    ("Line 1 (Virtual Audio Cable)", "unknown"),
    ("", "unknown"),
])
def test_classify(name, kind):
    assert d.classify(name) == kind


def test_headset_word_wins_when_both_match():
    assert d.classify("Speakers with Headphones passthrough") == "headset"


@pytest.mark.parametrize("value,expected", [
    (0, 0), (45, 45), (65, 65), (66, 65), (100, 65), (-5, 0), (64.6, 65),
    (None, 45), ("loud", 45),
])
def test_clamp_volume(value, expected):
    got = d.clamp_volume(value)
    assert got == expected and isinstance(got, int)


def test_ceilings_are_per_device():
    assert d.HEADSET_CEILING == 65
    assert d.SPEAKER_CEILING == 100
    assert d.SPEAKER_FLOOR == 1
    assert d.ceiling_for(d.HEADSET) == 65
    assert d.ceiling_for(d.SPEAKERS) == 100
    assert d.ceiling_for(d.UNKNOWN) == 65, "an unidentified device gets the quiet one"
    assert d.ceiling_for("nonsense") == 65


@pytest.mark.parametrize("value,expected", [
    (0, 1), (1, 1), (45, 45), (65, 65), (100, 100), (120, 100), (-5, 1),
    (99.6, 100), (None, 45), ("loud", 45),
])
def test_clamp_volume_for_speakers(value, expected):
    """Kris: speakers run 1 to 100 to be heard over background noise, and a
    speaker channel is never silently muted."""
    got = d.clamp_volume(value, d.SPEAKERS)
    assert got == expected and isinstance(got, int)


def test_a_headset_may_be_muted_but_speakers_may_not():
    assert d.clamp_volume(0, d.HEADSET) == 0
    assert d.clamp_volume(0, d.SPEAKERS) == d.SPEAKER_FLOOR


def test_an_unknown_device_gets_the_headset_ceiling():
    assert d.clamp_volume(100, d.UNKNOWN) == 65


def test_clear_session_returns_a_new_policy_and_does_not_mutate():
    p = d.Policy(allow_speakers_this_session=True, override_device="x")
    q = d.clear_session(p)
    assert p.allow_speakers_this_session is True      # untouched
    assert q.allow_speakers_this_session is False
    assert q.override_device == "x"                   # the rest survives
    assert dataclasses.is_dataclass(q)


def test_default_policy_is_private_and_avoids_hands_free():
    p = d.Policy()
    assert p.allow_speakers_this_session is False
    assert p.avoid_hands_free is True
    assert p.override_device is None


def test_result_shape():
    r = d.choose(REAL)
    assert set(r) == {"device", "speak", "play_fallback_tone", "reason"}
    assert isinstance(r["reason"], str) and r["reason"]


def test_headset_is_the_default_and_speakers_stay_silent():
    r = d.choose(REAL)
    assert r["speak"] is True and r["play_fallback_tone"] is False
    assert d.classify(r["device"]["name"]) == "headset"
    assert "headset" in r["reason"].lower()


def test_the_hands_free_endpoint_is_never_chosen_while_another_exists():
    """Measured 2026-09-20: hands-free speaks once, then blocks forever, and wedges
    the headset for both endpoints. Kris: "hands free is not the method to use."""
    for mic_live in (False, True):
        r = d.choose(REAL, mic_live=mic_live)
        assert r["device"]["index"] == 2, f"mic_live={mic_live}"
        assert "stereo" in r["reason"].lower()
        assert "hands-free" not in r["reason"].lower()


def test_dictating_is_still_reported_in_the_reason():
    assert "while dictating" in d.choose(REAL, mic_live=True)["reason"].lower()
    assert "while dictating" not in d.choose(REAL, mic_live=False)["reason"].lower()


def test_hands_free_is_used_only_when_it_is_the_only_headset():
    only = [{"index": 0, "name": "Speakers (x)"},
            {"index": 1, "name": "Headset (M98 Hands-Free AG Audio)"}]
    r = d.choose(only)
    assert r["device"]["index"] == 1
    assert r["speak"] is True
    assert "hands-free" in r["reason"].lower(), "the reason must carry the warning"


def test_avoiding_hands_free_can_be_turned_off():
    p = d.Policy(avoid_hands_free=False)
    r = d.choose(REAL, policy=p)
    assert r["speak"] is True
    assert d.classify(r["device"]["name"]) == "headset"


def test_lowest_index_headset_when_no_endpoint_name_hints():
    plain = [{"index": 3, "name": "Headphones B"}, {"index": 1, "name": "Headphones A"}]
    assert d.choose(plain, mic_live=True)["device"]["index"] == 1
    assert d.choose(plain, mic_live=False)["device"]["index"] == 1


def test_no_headset_stops_speech_and_plays_one_tone():
    r = d.choose(SPEAKERS_ONLY)
    assert r["speak"] is False
    assert r["play_fallback_tone"] is True
    assert r["device"] is None
    assert "no headset" in r["reason"].lower()


def test_no_devices_at_all_is_the_same_rule():
    r = d.choose([])
    assert r["speak"] is False and r["play_fallback_tone"] is True
    assert r["device"] is None


def test_speakers_only_with_session_permission():
    p = d.Policy(allow_speakers_this_session=True)
    r = d.choose(SPEAKERS_ONLY, policy=p)
    assert r["speak"] is True and r["play_fallback_tone"] is False
    assert r["device"]["index"] == 0
    low = r["reason"].lower()
    assert "speakers" in low and "session" in low


def test_session_permission_does_not_beat_a_present_headset():
    p = d.Policy(allow_speakers_this_session=True)
    r = d.choose(REAL, policy=p)
    assert d.classify(r["device"]["name"]) == "headset"


def test_override_names_a_device_exactly():
    p = d.Policy(override_device="Line 1 (Virtual Audio Cable)")
    devs = REAL + [{"index": 3, "name": "Line 1 (Virtual Audio Cable)"}]
    r = d.choose(devs, policy=p)
    assert r["device"]["index"] == 3
    assert r["speak"] is True and "override" in r["reason"].lower()


def test_override_for_a_missing_device_falls_back_to_the_rules():
    p = d.Policy(override_device="Nonexistent Device")
    r = d.choose(REAL, policy=p)
    assert d.classify(r["device"]["name"]) == "headset"
    r2 = d.choose(SPEAKERS_ONLY, policy=p)
    assert r2["speak"] is False and r2["play_fallback_tone"] is True


def test_unknown_devices_are_never_chosen_automatically():
    devs = [{"index": 0, "name": "Line 1 (Virtual Audio Cable)"}]
    r = d.choose(devs)
    assert r["device"] is None and r["speak"] is False


def test_choose_does_not_mutate_its_input():
    before = [dict(x) for x in REAL]
    d.choose(REAL, mic_live=True)
    assert REAL == before
