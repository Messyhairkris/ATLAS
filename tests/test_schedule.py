"""The schedule: every `when` form, latest/next_after, due, fire_once, tick
and the CLI - all with fixed datetimes, tmp_path homes and fake notify/submit.

October 2026: Fri 23, Sat 24, Sun 25, Mon 26, Tue 27, Wed 28, Thu 29, Fri 30.
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# %TEMP%\pytest-of-<user> is not readable from the sandbox these tests run in
# (WinError 5, 2026-10-26), so pytest's tmp_path dirs live inside the worktree.
TMP_ROOT = REPO / ".pytest-tmp"
TMP_ROOT.mkdir(exist_ok=True)
tempfile.tempdir = str(TMP_ROOT)

from crew import schedule  # noqa: E402
from crew.runners import schedule as sched_cli  # noqa: E402

FRI = datetime(2026, 10, 23)
SAT = datetime(2026, 10, 24)
SUN = datetime(2026, 10, 25)
MON = datetime(2026, 10, 26)
TUE = datetime(2026, 10, 27)
WED = datetime(2026, 10, 28)
THU = datetime(2026, 10, 29)


def at(day: datetime, h: int, m: int = 0) -> datetime:
    return day.replace(hour=h, minute=m)


def entry(**kw) -> dict:
    e = {
        "id": "s-test0001",
        "title": "stand up",
        "kind": "reminder",
        "when": "daily 09:00",
        "created_at": FRI.isoformat(),
        "enabled": True,
        "note": "stretch",
        "spec": None,
    }
    e.update(kw)
    return e


# parse_when ---------------------------------------------------------------


def test_parse_once():
    assert schedule.parse_when("2026-10-27 09:00") == {"type": "once", "at": at(TUE, 9)}


def test_parse_daily_case_insensitive():
    assert schedule.parse_when("DAILY 09:00") == {
        "type": "days",
        "days": [0, 1, 2, 3, 4, 5, 6],
        "time": (9, 0),
    }


def test_parse_weekdays():
    assert schedule.parse_when("Weekdays 09:00") == {
        "type": "days",
        "days": [0, 1, 2, 3, 4],
        "time": (9, 0),
    }


def test_parse_named_days():
    assert schedule.parse_when("mon,thu 14:30") == {
        "type": "days",
        "days": [0, 3],
        "time": (14, 30),
    }


def test_parse_every_minutes_and_hours():
    assert schedule.parse_when("every 30m") == {"type": "every", "minutes": 30}
    assert schedule.parse_when("every 2h") == {"type": "every", "minutes": 120}


def test_parse_rejects_bad_input():
    for bad in (
        "",
        "daily 25:00",
        "daily 09:60",
        "every 0m",
        "every -5m",
        "mon,funday 09:00",
        "2026-13-01 09:00",
        "2026-10-32 09:00",
        "whenever",
        "tuesday 09:00",
        "every 30d",
    ):
        assert schedule.parse_when(bad) is None, bad


# latest -------------------------------------------------------------------


def test_latest_once():
    when = schedule.parse_when("2026-10-27 09:00")
    assert schedule.latest(when, at(TUE, 9), FRI) == at(TUE, 9)
    assert schedule.latest(when, at(TUE, 23), FRI) == at(TUE, 9)
    assert schedule.latest(when, at(TUE, 8, 59), FRI) is None  # not yet
    assert schedule.latest(when, at(TUE, 23), WED) is None  # created after at


def test_latest_days_across_midnight():
    when = schedule.parse_when("daily 09:00")
    assert schedule.latest(when, at(TUE, 0, 30), FRI) == at(MON, 9)


def test_latest_weekdays_over_a_weekend():
    when = schedule.parse_when("weekdays 09:00")
    assert schedule.latest(when, at(MON, 8), FRI) == at(FRI, 9)  # before Monday's time
    assert schedule.latest(when, at(MON, 10), FRI) == at(MON, 9)
    assert schedule.latest(when, at(SUN, 12), FRI) == at(FRI, 9)


def test_latest_named_days_pick_most_recent():
    when = schedule.parse_when("mon,thu 14:30")
    # Friday noon: the most recent listed day is the day before, Thursday 22nd.
    assert schedule.latest(when, at(FRI, 12), FRI.replace(day=16)) == datetime(
        2026, 10, 22, 14, 30
    )


def test_latest_every_counts_from_created():
    when = schedule.parse_when("every 30m")
    created = at(MON, 9)
    assert schedule.latest(when, at(MON, 10, 15), created) == at(MON, 10)
    assert schedule.latest(when, at(MON, 10), created) == at(MON, 10)  # exact boundary
    assert schedule.latest(when, at(MON, 9, 29), created) is None  # k = 0


def test_latest_created_in_the_future():
    when = schedule.parse_when("daily 09:00")
    assert schedule.latest(when, at(TUE, 10), WED) is None


# next_after ---------------------------------------------------------------


def test_next_once():
    when = schedule.parse_when("2026-10-27 09:00")
    assert schedule.next_after(when, at(MON, 9), FRI) == at(TUE, 9)
    assert schedule.next_after(when, at(TUE, 9), FRI) is None  # not > now
    assert schedule.next_after(when, at(WED, 9), FRI) is None


def test_next_daily_across_midnight():
    when = schedule.parse_when("daily 09:00")
    assert schedule.next_after(when, at(MON, 8), FRI) == at(MON, 9)
    assert schedule.next_after(when, at(MON, 23), FRI) == at(TUE, 9)


def test_next_weekdays_over_a_weekend():
    when = schedule.parse_when("weekdays 09:00")
    assert schedule.next_after(when, at(FRI, 18), FRI) == at(MON, 9)


def test_next_every():
    when = schedule.parse_when("every 30m")
    created = at(MON, 9)
    assert schedule.next_after(when, at(MON, 10, 15), created) == at(MON, 10, 30)
    assert schedule.next_after(when, at(MON, 10), created) == at(MON, 10, 30)


def test_next_every_created_in_the_future():
    when = schedule.parse_when("every 2h")
    created = at(THU, 9)  # 2026-10-29 09:00
    assert schedule.next_after(when, at(MON, 9), created) == created + timedelta(
        hours=2
    )


def test_next_days_created_in_the_future():
    when = schedule.parse_when("daily 09:00")
    # created at noon Wednesday: Wednesday's 09:00 is before created, next is Thursday
    created = at(WED, 12)
    assert schedule.next_after(when, at(MON, 10), created) == at(THU, 9)


# due ----------------------------------------------------------------------


def test_due_respects_enabled_and_parse():
    base = entry()
    assert schedule.due(base, at(MON, 10), None) == at(MON, 9)
    assert schedule.due(entry(enabled=False), at(MON, 10), None) is None
    assert schedule.due(entry(**{"when": "whenever"}), at(MON, 10), None) is None


def test_due_against_last_fired():
    e = entry()
    assert schedule.due(e, at(MON, 10), at(MON, 9)) is None  # equal: already fired
    assert schedule.due(e, at(MON, 10), at(SUN, 9)) == at(MON, 9)  # older: owes Monday


def test_due_collapses_a_missed_weekend():
    # PC off all weekend: one occurrence on Monday, not three.
    e = entry(**{"when": "daily 09:00"})
    assert schedule.due(e, at(MON, 10), at(FRI, 9)) == at(MON, 9)
    weekdays = entry(**{"when": "weekdays 09:00"})
    assert schedule.due(weekdays, at(MON, 10), at(FRI, 9)) == at(MON, 9)


# fire_once ----------------------------------------------------------------


def test_fire_once_only_once(tmp_path):
    occurrence = at(MON, 9)
    assert schedule.fire_once(tmp_path, "s-test0001", occurrence) is True
    assert schedule.fire_once(tmp_path, "s-test0001", occurrence) is False
    assert (tmp_path / "fired" / "s-test0001@20261026T0900").is_file()
    # a different occurrence still fires
    assert schedule.fire_once(tmp_path, "s-test0001", at(TUE, 9)) is True


# storage ------------------------------------------------------------------


def test_load_missing_gives_empty_and_save_roundtrips(tmp_path):
    assert schedule.load(tmp_path) == []
    entries = [entry()]
    schedule.save(tmp_path, entries)
    assert schedule.load(tmp_path) == entries
    schedule.save(tmp_path, [])  # atomic overwrite
    assert schedule.load(tmp_path) == []


# tick ---------------------------------------------------------------------


def test_tick_fires_reminder_and_job_once(tmp_path):
    job = entry(
        id="s-job00001",
        kind="job",
        title="nightly",
        spec={"task_type": "report"},
        **{"when": "weekdays 09:00"},
    )
    schedule.save(tmp_path, [entry(), job])
    notified, submitted = [], []

    def notify(title, note):
        notified.append((title, note))

    def submit(spec):
        submitted.append(spec)
        return "job-123"

    firings = schedule.tick(tmp_path, at(MON, 10), notify, submit)
    assert len(firings) == 2
    assert notified == [("stand up", "stretch")]
    assert submitted == [{"task_type": "report"}]
    by_id = {f["id"]: f for f in firings}
    assert by_id["s-test0001"]["occurrence"] == at(MON, 9).isoformat()
    assert by_id["s-job00001"]["job_id"] == "job-123"

    last = schedule.load_last_fired(tmp_path)
    assert last["s-test0001"] == at(MON, 9).isoformat()
    assert last["s-job00001"] == at(MON, 9).isoformat()

    rows = schedule.fired_log(tmp_path)
    assert [r["id"] for r in rows] == ["s-test0001", "s-job00001"]

    notified.clear()
    assert schedule.tick(tmp_path, at(MON, 10), notify, submit) == []  # not again
    assert notified == []


def test_tick_failing_notify_does_not_stop_a_job(tmp_path):
    job = entry(id="s-job00001", kind="job", spec={"task_type": "report"})
    schedule.save(tmp_path, [entry(), job])

    def bad_notify(title, note):
        raise RuntimeError("toast broke")

    def submit(spec):
        return "job-9"

    firings = schedule.tick(tmp_path, at(MON, 10), bad_notify, submit)
    assert len(firings) == 2
    by_id = {f["id"]: f for f in firings}
    assert "toast broke" in by_id["s-test0001"]["error"]
    assert by_id["s-job00001"]["job_id"] == "job-9"
    assert "error" not in by_id["s-job00001"]
    # both were still recorded as fired
    assert set(schedule.load_last_fired(tmp_path)) == {"s-test0001", "s-job00001"}


def test_tick_due_occurrence_locked_by_another_worker(tmp_path):
    schedule.save(tmp_path, [entry()])
    schedule.fire_once(tmp_path, "s-test0001", at(MON, 9))
    assert schedule.tick(tmp_path, at(MON, 10), lambda t, n: None, lambda s: "x") == []


# the CLI -------------------------------------------------------------------


def _run_cli(monkeypatch, capsys, tmp_path, argv):
    monkeypatch.setenv("CREW_SCHEDULE_HOME", str(tmp_path))
    sched_cli.main(argv)
    return json.loads(capsys.readouterr().out)


def test_cli_add_list_remove(monkeypatch, capsys, tmp_path):
    added = _run_cli(
        monkeypatch,
        capsys,
        tmp_path,
        [
            "add",
            "--title",
            "Water the plants",
            "--when",
            "daily 09:00",
            "--note",
            "the fern",
        ],
    )["added"]
    assert added["id"].startswith("s-") and len(added["id"]) == 10
    assert added["enabled"] is True and added["kind"] == "reminder"

    listed = _run_cli(monkeypatch, capsys, tmp_path, ["list"])["entries"]
    assert len(listed) == 1
    assert listed[0]["id"] == added["id"]
    assert listed[0]["note"] == "the fern"
    assert datetime.fromisoformat(listed[0]["next"])  # a real ISO time

    _run_cli(monkeypatch, capsys, tmp_path, ["remove", added["id"]])
    assert _run_cli(monkeypatch, capsys, tmp_path, ["list"])["entries"] == []


def test_cli_add_refuses_a_when_that_does_not_parse(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CREW_SCHEDULE_HOME", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        sched_cli.main(["add", "--title", "Nope", "--when", "daily 25:00"])
    assert exc.value.code == 2
    assert "error" in json.loads(capsys.readouterr().out)
    assert schedule.load(tmp_path) == []


def test_cli_job_needs_a_spec_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CREW_SCHEDULE_HOME", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        sched_cli.main(
            ["add", "--title", "Nightly", "--when", "daily 02:00", "--kind", "job"]
        )
    assert exc.value.code == 2
    assert "error" in json.loads(capsys.readouterr().out)

    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({"task_type": "report"}), encoding="utf-8")
    added = _run_cli(
        monkeypatch,
        capsys,
        tmp_path,
        [
            "add",
            "--title",
            "Nightly",
            "--when",
            "daily 02:00",
            "--kind",
            "job",
            "--spec",
            str(spec_file),
        ],
    )["added"]
    assert added["spec"] == {"task_type": "report"}

    _run_cli(monkeypatch, capsys, tmp_path, ["disable", added["id"]])
    listed = _run_cli(monkeypatch, capsys, tmp_path, ["list"])["entries"]
    assert listed[0]["enabled"] is False
    _run_cli(monkeypatch, capsys, tmp_path, ["enable", added["id"]])
    listed = _run_cli(monkeypatch, capsys, tmp_path, ["list"])["entries"]
    assert listed[0]["enabled"] is True
