"""Hidden tests for profiles.py - the author never sees these.

Kris: "the settings should be able to hold a few varieties and volume sets and
locks. It would be nice to be able to reconnect a previously paired headset as
well."  So these tests care about three things above all: that a user's own
volumes survive everything, that a lock actually holds, and that nothing here
retries a Bluetooth pairing in a loop.
"""

import json

import profiles as p
import pytest

BT_STEREO = {"index": 0, "name": "Headphones (M98 Stereo)"}
BT_HFP = {"index": 1, "name": "Headset (M98 Hands-Free AG Audio)"}
USB_CANS = {"index": 2, "name": "Headset (Logitech USB Headset)"}
SPEAKERS = {"index": 3, "name": "Speakers (3- High Definition Audio Device)"}


# -- classify_link -----------------------------------------------------------------

def test_link_words_are_present_and_lowercase():
    for word in ("bluetooth", "hands-free", "hands free", "stereo", "a2dp",
                 "airpod", "wireless"):
        assert word in p.BLUETOOTH_WORDS
    for word in ("usb", "jack", "3.5", "analog", "line in", "line 1", "wired"):
        assert word in p.WIRED_WORDS
    assert all(w == w.lower() for w in p.BLUETOOTH_WORDS + p.WIRED_WORDS)


def test_classify_link_reads_the_real_device_names():
    assert p.classify_link("Headphones (M98 Stereo)") == "bluetooth"
    assert p.classify_link("Headset (M98 Hands-Free AG Audio)") == "bluetooth"
    assert p.classify_link("Speakers (USB Audio Device)") == "wired"
    assert p.classify_link("Speakers (3- High Definition Audio Device)") == "builtin"
    assert p.classify_link("Line 1 (Virtual Audio Cable)") == "wired"
    assert p.classify_link("SteelSeries Arctis") == "unknown"


def test_a_wireless_headset_on_a_usb_dongle_is_still_bluetooth():
    assert p.classify_link("Wireless Headset (USB Dongle)") == "bluetooth"


def test_classify_link_is_case_insensitive_and_survives_an_empty_name():
    assert p.classify_link("HEADPHONES (M98 STEREO)") == "bluetooth"
    assert p.classify_link("") == "unknown"


# -- new_profile -------------------------------------------------------------------

def test_a_new_profile_has_exactly_the_agreed_shape():
    prof = p.new_profile(BT_STEREO["name"])
    assert list(prof) == ["name", "kind", "link", "volumes", "locked", "last_used"]
    assert prof["kind"] == "headset"
    assert prof["link"] == "bluetooth"
    assert prof["volumes"] == {"speech": 45, "alert": 65}
    assert prof["locked"] is False
    assert prof["last_used"] == 0.0


def test_a_profile_needs_a_name():
    with pytest.raises(ValueError):
        p.new_profile("")
    with pytest.raises(ValueError):
        p.new_profile("   ")
    with pytest.raises(ValueError):
        p.new_profile(None)


def test_a_bad_kind_or_link_is_refused():
    with pytest.raises(ValueError):
        p.new_profile("a headset", kind="loudspeaker")
    with pytest.raises(ValueError):
        p.new_profile("a headset", link="carrier pigeon")


def test_a_headset_profile_cannot_hold_a_speaker_volume():
    """The measured ceiling: 70 and 100 were painful in one ear."""
    prof = p.new_profile(BT_STEREO["name"], speech=100, alert=100)
    assert prof["volumes"] == {"speech": 65, "alert": 65}


def test_a_speaker_profile_can_go_loud_but_never_silent():
    prof = p.new_profile(SPEAKERS["name"], speech=100, alert=0)
    assert prof["kind"] == "speakers"
    assert prof["volumes"]["speech"] == 100
    assert prof["volumes"]["alert"] == 1


# -- volumes and the lock ----------------------------------------------------------

def test_volume_for_clamps_what_a_hand_edit_left_behind():
    prof = p.new_profile(BT_STEREO["name"])
    prof["volumes"]["speech"] = 300
    assert p.volume_for(prof, "speech") == 65
    prof["volumes"]["speech"] = "loud"
    assert p.volume_for(prof, "speech") == 45
    del prof["volumes"]["alert"]
    assert p.volume_for(prof, "alert") == 65


def test_an_unknown_purpose_is_refused_both_ways():
    prof = p.new_profile(BT_STEREO["name"])
    with pytest.raises(ValueError):
        p.volume_for(prof, "whisper")
    with pytest.raises(ValueError):
        p.set_volume(prof, "whisper", 40)


def test_set_volume_returns_a_new_profile_and_leaves_the_old_one_alone():
    prof = p.new_profile(BT_STEREO["name"])
    fresh = p.set_volume(prof, "speech", 50)
    assert fresh["volumes"]["speech"] == 50
    assert prof["volumes"]["speech"] == 45
    assert fresh is not prof
    assert fresh["volumes"] is not prof["volumes"]


def test_a_locked_profile_refuses_every_volume_change():
    """Kris's lock: the app raising a volume on its own must not touch a setting
    the user has pinned."""
    prof = p.set_lock(p.new_profile(BT_STEREO["name"]), True)
    assert p.set_volume(prof, "speech", 10)["volumes"]["speech"] == 45
    assert p.set_volume(prof, "alert", 65)["volumes"]["alert"] == 65
    assert p.set_volume(prof, "speech", 64) == prof


def test_a_lock_can_always_be_undone():
    prof = p.set_lock(p.new_profile(BT_STEREO["name"]), True)
    open_again = p.set_lock(prof, False)
    assert open_again["locked"] is False
    assert p.set_volume(open_again, "speech", 50)["volumes"]["speech"] == 50


def test_set_lock_does_not_mutate_and_takes_anything_truthy():
    prof = p.new_profile(BT_STEREO["name"])
    assert p.set_lock(prof, 1)["locked"] is True
    assert p.set_lock(prof, "")["locked"] is False
    assert prof["locked"] is False


# -- remember / known / find -------------------------------------------------------

def test_remember_adds_a_device_it_has_never_seen():
    out = p.remember([], BT_STEREO["name"], now=100.0)
    assert [x["name"] for x in out] == [BT_STEREO["name"]]
    assert out[0]["last_used"] == 100.0


def test_remember_keeps_the_volumes_and_the_lock_of_a_device_replugged():
    first = p.remember([], BT_STEREO["name"], now=1.0)
    first[0] = p.set_lock(p.set_volume(first[0], "speech", 60), True)
    again = p.remember(first, BT_STEREO["name"], now=500.0)
    assert len(again) == 1
    assert again[0]["volumes"]["speech"] == 60
    assert again[0]["locked"] is True
    assert again[0]["last_used"] == 500.0


def test_remember_does_not_mutate_what_it_was_given():
    first = p.remember([], BT_STEREO["name"], now=1.0)
    p.remember(first, BT_STEREO["name"], now=900.0)
    assert first[0]["last_used"] == 1.0


def test_remember_refuses_a_nameless_device():
    with pytest.raises(ValueError):
        p.remember([], "")


def test_known_is_most_recent_first_with_a_stable_tie_break():
    items = [p.new_profile("Zed Headset", last_used=5.0),
             p.new_profile("Alpha Headset", last_used=5.0),
             p.new_profile(BT_STEREO["name"], last_used=50.0),
             p.new_profile(USB_CANS["name"])]
    order = [x["name"] for x in p.known(items)]
    assert order == [BT_STEREO["name"], "Alpha Headset", "Zed Headset",
                     USB_CANS["name"]]


def test_find_matches_exactly_or_returns_none():
    items = [p.new_profile(BT_STEREO["name"])]
    assert p.find(items, BT_STEREO["name"])["kind"] == "headset"
    assert p.find(items, "headphones (m98 stereo)") is None
    assert p.find([], BT_STEREO["name"]) is None


# -- present / missing -------------------------------------------------------------

def test_present_pairs_a_profile_with_the_device_as_windows_reported_it():
    items = p.remember([], BT_STEREO["name"], now=10.0)
    here = p.present(items, [SPEAKERS, BT_STEREO])
    assert len(here) == 1
    assert here[0]["device"] == BT_STEREO
    assert here[0]["profile"]["name"] == BT_STEREO["name"]


def test_present_is_in_most_recently_used_order():
    items = p.remember(p.remember([], USB_CANS["name"], now=1.0),
                       BT_STEREO["name"], now=99.0)
    here = p.present(items, [USB_CANS, BT_STEREO])
    assert [x["profile"]["name"] for x in here] == [BT_STEREO["name"],
                                                    USB_CANS["name"]]


def test_missing_is_what_he_has_used_and_is_not_here():
    items = p.remember([], BT_STEREO["name"], now=10.0)
    assert [x["name"] for x in p.missing(items, [SPEAKERS])] == [BT_STEREO["name"]]
    assert p.missing(items, [BT_STEREO]) == []


def test_a_device_used_at_the_very_first_second_is_still_missing():
    """A seeded defect found this: `last_used > 0` became `> 1` and every test
    still passed, because none of them used the boundary."""
    items = [p.new_profile(BT_STEREO["name"], last_used=1.0)]
    assert [x["name"] for x in p.missing(items, [])] == [BT_STEREO["name"]]


def test_a_device_never_used_is_not_missing():
    items = [p.new_profile(USB_CANS["name"])]
    assert p.missing(items, []) == []


# -- prefer ------------------------------------------------------------------------

def test_prefer_takes_the_one_he_used_last():
    items = p.remember(p.remember([], USB_CANS["name"], now=1.0),
                       BT_STEREO["name"], now=99.0)
    choice = p.prefer(items, [USB_CANS, BT_STEREO])
    assert choice["device"] == BT_STEREO
    assert choice["profile"]["name"] == BT_STEREO["name"]
    assert "remembered" in choice["reason"]


def test_prefer_falls_back_to_a_headset_it_has_never_seen():
    choice = p.prefer([], [SPEAKERS, BT_HFP, USB_CANS])
    assert choice["profile"] is None
    assert choice["device"] == BT_HFP           # lowest index of the headsets
    assert "new headset" in choice["reason"]


def test_prefer_never_reaches_for_the_speakers():
    choice = p.prefer([], [SPEAKERS])
    assert choice == {"profile": None, "device": None,
                      "reason": choice["reason"]}
    assert "nothing known" in choice["reason"]


def test_prefer_on_an_empty_machine_says_so():
    choice = p.prefer(p.remember([], BT_STEREO["name"], now=1.0), [])
    assert choice["device"] is None
    assert "nothing known" in choice["reason"]


def test_prefer_returns_exactly_three_keys():
    assert set(p.prefer([], [])) == {"profile", "device", "reason"}


# -- reconnect ---------------------------------------------------------------------

def test_nothing_to_reconnect_when_it_is_already_here():
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [BT_STEREO], now=100.0)
    assert plan["should_try"] is False
    assert plan["wait_s"] == 0
    assert "already here" in plan["reason"]


def test_a_cable_is_the_users_job():
    prof = p.new_profile(USB_CANS["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [], now=100.0)
    assert plan["link"] == "wired"
    assert plan["should_try"] is False
    assert "plug it in" in plan["reason"]


def test_a_paired_headset_that_is_gone_is_worth_asking_for():
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [SPEAKERS], now=100.0)
    assert plan["should_try"] is True
    assert plan["wait_s"] == 0
    assert "reconnect" in plan["reason"]
    assert plan["name"] == BT_STEREO["name"]
    assert plan["link"] == "bluetooth"


def test_it_will_not_retry_a_pairing_in_a_tight_loop():
    """Measured once already: hammering the radio wedges both endpoints."""
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [], now=100.0, last_attempt=95.0)
    assert plan["should_try"] is False
    assert plan["wait_s"] == 25
    assert "tried" in plan["reason"]


def test_a_device_never_tried_is_worth_asking_for_straight_away():
    """Another seeded defect: `last_attempt > 0` became `>= 0`, which would treat
    "never tried" as "tried at time zero" and wait out the cooldown at startup."""
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [], now=1.0)
    assert plan["should_try"] is True
    assert plan["wait_s"] == 0


def test_the_cooldown_rounds_the_wait_up_to_a_whole_second():
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [], now=100.5, last_attempt=95.0)
    assert plan["wait_s"] == 25


def test_once_the_cooldown_has_passed_it_tries_again():
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [], now=131.0, last_attempt=100.0)
    assert plan["should_try"] is True
    assert plan["wait_s"] == 0


def test_the_cooldown_length_can_be_changed_by_the_caller():
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    plan = p.reconnect_plan(prof, [], now=110.0, last_attempt=100.0,
                            cooldown_s=5)
    assert plan["should_try"] is True
    assert p.RECONNECT_COOLDOWN_S == 30


def test_reconnect_plan_returns_exactly_five_keys():
    prof = p.new_profile(BT_STEREO["name"], last_used=1.0)
    assert set(p.reconnect_plan(prof, [])) == {"name", "link", "should_try",
                                               "wait_s", "reason"}


# -- the settings file -------------------------------------------------------------

def test_the_round_trip_keeps_volumes_locks_and_history():
    items = p.remember([], BT_STEREO["name"], now=42.0)
    items[0] = p.set_lock(p.set_volume(items[0], "speech", 60), True)
    items = p.remember(items, SPEAKERS["name"], now=7.0)
    again = p.load(p.dump(items))
    assert again == items


def test_the_file_is_readable_json_a_person_can_edit():
    items = p.remember([], BT_STEREO["name"], now=1.0)
    text = p.dump(items)
    assert json.loads(text)[0]["name"] == BT_STEREO["name"]
    assert "\n" in text                      # indented, not one long line


def test_unreadable_settings_are_a_valueerror():
    with pytest.raises(ValueError):
        p.load("{not json")
    with pytest.raises(ValueError):
        p.load('{"name": "a headset"}')       # an object, not a list


def test_a_hand_edited_file_is_repaired_rather_than_refused():
    text = json.dumps([
        {"name": "Headphones (M98 Stereo)", "volumes": {"speech": 900},
         "colour": "orange"},
        {"name": "", "volumes": {"speech": 10}},
        {"nickname": "the good ones"},
        "not even a record",
    ])
    out = p.load(text)
    assert len(out) == 1
    assert out[0]["volumes"]["speech"] == 65        # clamped to the headset ceiling
    assert out[0]["volumes"]["alert"] == 65         # the missing key took its default
    assert "colour" not in out[0]


def test_an_empty_list_survives_the_round_trip():
    assert p.load(p.dump([])) == []
