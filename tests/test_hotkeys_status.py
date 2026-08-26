"""A stale readout is worse than none: a plausible-looking dead root system
would be acted on. Liveness is the authority; the file only supplies values
once liveness is established."""

import json

import pytest

from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section
from wingman import hotkeys

VALUES = {
    "sig": "-ABC",
    "root": "J1234",
    "next_num": "J12345",
    "next_alpha": "J1234A",
    "failed_binds": [],
    "seq": 0,
    "written": 1000.0,
}


def write_status(tmp_path, **over):
    (tmp_path / "eve_status.json").write_text(json.dumps({**VALUES, **over}))


def test_off_when_not_enabled(tmp_path):
    write_status(tmp_path)
    got = engine(tmp_path, FakeSpawner()).status(enabled=False, now=1000.0)
    assert got.state == "off"
    assert got.root is None


def test_stopped_clears_values_rather_than_freezing_them(tmp_path):
    """The engine died but its last status file is still on disk. Showing
    J1234 as the current root would be a lie the user acts on."""
    write_status(tmp_path)
    got = engine(tmp_path, FakeSpawner()).status(enabled=True, now=1000.0)
    assert got.state == "stopped"
    assert got.root is None
    assert got.sig is None


def test_running_reports_the_values(tmp_path):
    write_status(tmp_path)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    got = eng.status(enabled=True, now=1002.0)
    assert got.state == "running"
    assert got.root == "J1234"
    assert got.next_alpha == "J1234A"


def test_stale_when_the_file_stops_updating(tmp_path):
    """The engine writes every 2s; several missed ticks means it is alive
    but not working."""
    write_status(tmp_path, written=1000.0)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    got = eng.status(enabled=True, now=1000.0 + hotkeys.STALE_AFTER_S + 1)
    assert got.state == "stale"
    assert got.root is None


def test_failed_binds_are_surfaced(tmp_path):
    """Registration errors are swallowed by UseErrorLevel in the script
    (111unified.ahk:767-823); a process can look healthy with dead keys."""
    write_status(tmp_path, failed_binds=["FinH", "FinL"])
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1001.0).failed_binds == ["FinH", "FinL"]


def test_missing_status_file_while_running_is_stale_not_a_crash(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1000.0).state == "stale"


def test_corrupt_status_file_is_stale_not_a_crash(tmp_path):
    """A torn read is exactly what atomic publication is meant to prevent,
    but a truncated file from an older build must not take the UI down."""
    (tmp_path / "eve_status.json").write_text('{"sig": "-AB')
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1000.0).state == "stale"


@pytest.mark.parametrize("bad", ["nope", 7, {"a": 1}, None])
def test_a_malformed_failed_binds_is_stale_not_empty(tmp_path, bad):
    """[] means "every hotkey registered fine" -- the one thing an
    unreadable field does not tell us. A wrong-typed field also means the
    document is untrustworthy, so `root` must not be shown either."""
    write_status(tmp_path, failed_binds=bad)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    got = eng.status(enabled=True, now=1001.0)
    assert got.state == "stale"
    assert got.root is None


@pytest.mark.parametrize(
    "bad,expected",
    [
        ({"a": 1}, None),
        ([1], None),
        (True, None),
        (42, "42"),
        ("  ", None),
    ],
)
def test_display_values_are_coerced_for_a_label(tmp_path, bad, expected):
    """These render into a status bar; a dict would appear as its repr, and
    a bool as "True", which is not a system name."""
    write_status(tmp_path, root=bad)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1001.0).root == expected


def test_a_status_written_in_the_future_is_not_stale(tmp_path):
    """A backwards clock step makes the difference negative. Reporting stale
    there would blank a live engine's readout for no reason."""
    write_status(tmp_path, written=2000.0)
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    assert eng.status(enabled=True, now=1000.0).state == "running"


def test_a_failed_start_reason_reaches_the_status(tmp_path):
    """The reason a start failed is the one actionable thing the user can be
    told -- without it the toggle reads "on" while nothing runs. Both
    API-level tests use a fake whose status() reimplements this logic, so
    nothing else in the suite would catch this line being dropped."""
    eng = hotkeys.HotkeyEngine(None, None, tmp_path, spawner=FakeSpawner())
    assert eng.start() is False
    got = eng.status(enabled=True)
    assert got.state == "stopped"
    assert got.last_error
    assert "reinstall" in got.last_error.lower()


def test_a_clean_stop_reports_no_reason(tmp_path):
    """Stopped-because-you-turned-it-off must not look like
    stopped-because-it-failed; a spurious error string is worse than none."""
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    assert eng.start() is True
    eng.stop()
    got = eng.status(enabled=True)
    assert got.state == "stopped"
    assert got.last_error is None
