"""Set Root and Clear Root are operations, not settings, so they cannot
travel through the config file. One slot, a monotonic sequence, and an
acknowledgement is the whole protocol -- but each of those three pieces has
a failure mode worth a test."""
import json
from obs_youtube_uploader import hotkeys
from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section


def started(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    return eng


def command(tmp_path):
    """Parse the INI the engine will read with IniRead."""
    out = {}
    for line in (tmp_path / "eve_command.ini").read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def ack(tmp_path, seq, now=1000.0):
    (tmp_path / "eve_status.json").write_text(json.dumps(
        {"seq": seq, "written": now, "failed_binds": []}))


def test_first_command_is_sequence_one(tmp_path):
    eng = started(tmp_path)
    assert eng.send_command("clear_root") is True
    got = command(tmp_path)
    assert got["Seq"] == "1"
    assert got["Name"] == "clear_root"
    assert got["Argument"] == ""


def test_file_has_the_section_header_iniread_needs(tmp_path):
    eng = started(tmp_path)
    eng.send_command("clear_root")
    assert (tmp_path / "eve_command.ini").read_text().startswith("[Command]")


def test_argument_is_carried(tmp_path):
    eng = started(tmp_path)
    eng.send_command("set_root", "J123456")
    assert command(tmp_path)["Argument"] == "J123456"


def test_argument_cannot_forge_an_ini_line(tmp_path):
    """The argument is free text typed by the user and lands in a file the
    engine parses; a newline must not be able to add a key."""
    eng = started(tmp_path)
    eng.send_command("set_root", "J1\r\nName=clear_root")
    assert command(tmp_path)["Name"] == "set_root"


def test_unacknowledged_command_is_never_overwritten(tmp_path):
    """One slot and a 2s poll: a second action taken quickly would destroy
    the first, and the user would see one of their two clicks vanish."""
    eng = started(tmp_path)
    eng.send_command("set_root", "J111")
    assert eng.send_command("clear_root") is False
    assert command(tmp_path)["Argument"] == "J111"


def test_a_new_command_is_allowed_once_acknowledged(tmp_path):
    eng = started(tmp_path)
    eng.send_command("set_root", "J111")
    ack(tmp_path, 1)
    assert eng.send_command("clear_root", now=1000.0) is True
    assert command(tmp_path)["Seq"] == "2"


def test_pending_command_reports_the_waiting_sequence(tmp_path):
    eng = started(tmp_path)
    eng.send_command("clear_root")
    assert eng.pending_command(now=1000.0) == 1
    ack(tmp_path, 1)
    assert eng.pending_command(now=1000.0) is None


def test_sequence_survives_a_wingman_restart(tmp_path):
    """If Wingman resumed from zero while a higher-numbered command sat on
    disk, the engine would ignore every command until it caught up."""
    eng = started(tmp_path)
    eng.send_command("clear_root", now=1000.0)
    ack(tmp_path, 1)
    eng.send_command("set_root", "J1", now=1000.0)
    ack(tmp_path, 2)

    fresh = started(tmp_path)
    fresh.sync_sequence()
    fresh.send_command("clear_root", now=1000.0)
    assert command(tmp_path)["Seq"] == "3"


def test_sync_ignores_a_corrupt_command_file(tmp_path):
    (tmp_path / "eve_command.ini").write_text("nonsense without a section")
    eng = started(tmp_path)
    eng.sync_sequence()
    eng.send_command("clear_root")
    assert command(tmp_path)["Seq"] == "1"


def test_command_is_refused_when_the_engine_is_not_running(tmp_path):
    """Writing a command nothing will read would leave the buttons stuck
    waiting for an acknowledgement that cannot arrive."""
    eng = engine(tmp_path, FakeSpawner())
    assert eng.send_command("clear_root") is False
    assert not (tmp_path / "eve_command.ini").exists()


def test_unknown_command_names_are_refused(tmp_path):
    eng = started(tmp_path)
    assert eng.send_command("rm_rf") is False
    assert not (tmp_path / "eve_command.ini").exists()


def test_a_failed_write_does_not_wedge_the_channel(tmp_path, monkeypatch):
    """Advancing the counter without a file on disk leaves
    pending_command() waiting on a command nothing can acknowledge, and
    every later command is refused for the rest of the session."""
    eng = started(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(hotkeys.atomicio, "write_atomic", boom)
    assert eng.send_command("clear_root", now=1000.0) is False
    monkeypatch.undo()

    assert eng.send_command("clear_root", now=1000.0) is True
    assert command(tmp_path)["Seq"] == "1"


def test_sync_ignores_a_seq_outside_the_command_section(tmp_path):
    (tmp_path / "eve_command.ini").write_text(
        "[Other]\r\nSeq=42\r\n[Command]\r\nSeq=7\r\n", newline="")
    eng = started(tmp_path)
    eng.sync_sequence()
    assert eng._seq == 7


def test_sync_clamps_a_negative_sequence(tmp_path):
    """A negative sequence makes `consumed >= self._seq` true for every
    command, defeating the unconsumed-command guard outright."""
    (tmp_path / "eve_command.ini").write_text(
        "[Command]\r\nSeq=-5\r\n", newline="")
    eng = started(tmp_path)
    eng.sync_sequence()
    assert eng._seq == 0


def test_sync_still_survives_a_byte_order_mark(tmp_path):
    """The section check reintroduces a dependency on the first line
    parsing correctly, which a BOM breaks."""
    # encoding is named, not inherited: write_text falls back to the
    # locale encoding, which is cp1252 on Windows and cannot encode a BOM
    # at all -- the test died in its own setup line rather than testing
    # anything. UTF-8 is what it was already getting on Linux.
    (tmp_path / "eve_command.ini").write_text(
        "﻿[Command]\r\nSeq=7\r\n", newline="", encoding="utf-8")
    eng = started(tmp_path)
    eng.sync_sequence()
    assert eng._seq == 7
