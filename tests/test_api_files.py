"""Deleting, opening, copying, and combat-log upload across the bridge.

These went through Tk messageboxes and the clipboard before the
replatform. The confirmations and the partial-failure handling are the
parts with real consequences on disk.
"""
import datetime

import pytest

from obs_youtube_uploader import combatlog, discord, library
from obs_youtube_uploader.ui import api as api_mod
from tests import fakes


def api_with(tmp_path, names=("a.mkv", "b.mkv"), watcher=None, **kw):
    rows = {}
    for index, name in enumerate(names):
        path = tmp_path / name
        path.write_bytes(b"\0" * 1024)
        rows[f"r{index}"] = fakes.info(path, size=1024, mtime=1_700_000_000.0)
    api, window = fakes.build_api(tmp_path, rows=fakes.FakeRows(rows),
                                  watcher=watcher, **kw)
    api._alert = fakes.Alerts()
    api._confirm = fakes.Answers()
    api.list_rows = lambda preselect=None: None  # Task 6's refresh; not under test here.
    return api, window, rows


def join_delete(api):
    api._delete_thread.join(timeout=5)


def test_deleting_nothing_says_so(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api.delete_selected([])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to delete.")]


def test_delete_confirms_by_naming_every_file_and_saying_it_is_final(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api._confirm = fakes.Answers(answer=False)
    api.delete_selected(["r0", "r1"])
    join_delete(api)

    (title, body), = api._confirm.asked
    assert title == "Confirm Delete"
    assert "a.mkv" in body and "b.mkv" in body
    assert "cannot be undone" in body
    assert (tmp_path / "a.mkv").exists()


def test_declining_the_delete_leaves_the_files_alone(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api._confirm = fakes.Answers(answer=False)
    api.delete_selected(["r0"])
    join_delete(api)
    assert (tmp_path / "a.mkv").exists()


def test_only_files_that_actually_went_are_forgotten_by_the_watcher(monkeypatch, tmp_path):
    """A file that failed to delete still exists, and dropping its
    seen-entry would make the watcher announce it again as if it were new."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, rows = api_with(tmp_path, watcher=watcher)
    sent = fakes.record_pushes(api)
    kept = rows["r1"].path

    def half_fails(items):
        items[0].unlink()
        return 1, [(kept, "Permission denied")]

    monkeypatch.setattr(api_mod.library, "delete", half_fails)

    api.delete_selected(["r0", "r1"])
    join_delete(api)

    assert watcher.forgotten == [rows["r0"].path]
    assert fakes.payloads(sent, "onStatus")[-1] == {
        "text": "Deleted 1 file(s). 1 failed.", "kind": "FG"}


def test_copy_returns_the_link_and_reports_it(tmp_path):
    """The name is historical: what a row offers to copy or open is the
    YouTube link it earned, which is why both are inert before an upload."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    api._links["r0"] = "https://www.youtube.com/watch?v=abc"

    assert api.copy_path("r0") == "https://www.youtube.com/watch?v=abc"
    assert fakes.payloads(sent, "onStatus") == [
        {"text": "Link copied to clipboard", "kind": "SUCCESS"}]


def test_copy_on_a_row_with_no_link_returns_nothing_and_says_nothing(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    assert api.copy_path("r0") == ""
    assert sent == []


def test_open_launches_the_browser_for_a_linked_row(monkeypatch, tmp_path):
    opened = []
    api, _window, _rows = api_with(tmp_path)
    api._links["r0"] = "https://www.youtube.com/watch?v=abc"
    monkeypatch.setattr(api_mod.webbrowser, "open", opened.append)
    api.open_path("r0")
    assert opened == ["https://www.youtube.com/watch?v=abc"]


def test_open_on_an_unknown_row_does_nothing(monkeypatch, tmp_path):
    """A stale page after a refresh must fail cleanly rather than act on an
    id the backend no longer knows."""
    opened = []
    api, _window, _rows = api_with(tmp_path)
    monkeypatch.setattr(api_mod.webbrowser, "open", opened.append)
    api.open_path("gone")
    assert opened == []


HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def test_combat_logs_with_nothing_selected_says_which_selection_is_missing(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api.upload_combat_logs([])
    assert api._alert.raised == [
        ("warning", "No Selection",
         "Select at least one recording to upload logs for.")]


def test_combat_logs_share_the_upload_busy_guard(tmp_path):
    """One upload of either kind at a time; this inherits the same warning
    and the same refresh deferral."""
    import threading as _threading
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    gate = _threading.Event()
    api._upload_thread = _threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.upload_combat_logs(["r0"])
        assert api._alert.titles() == ["Busy"]
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)


def test_combat_logs_without_a_webhook_name_the_parse_error(tmp_path):
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": ""})
    api.upload_combat_logs(["r0"])
    kind, title, body = api._alert.raised[0]
    assert (kind, title) == ("warning", "Discord not configured")
    assert "Add a webhook URL in Settings first." in body


def test_combat_logs_without_a_gamelogs_folder_say_so(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)
    api.upload_combat_logs(["r0"])
    assert api._alert.titles() == ["Gamelogs not found"]


def test_a_recording_with_no_readable_duration_blocks_the_window(monkeypatch, tmp_path):
    """No duration means no start time, so there is no window to build --
    refuse rather than invent one that pulls logs from another fight."""
    logs = tmp_path / "logs"
    logs.mkdir()
    api, _window, rows = api_with(tmp_path,
                                  settings={"discord_webhook": HOOK,
                                            "gamelogs_dir": str(logs)})
    rows["r0"].duration = None
    rows["r0"].probed = True
    api.upload_combat_logs(["r0"])
    kind, title, body = api._alert.raised[0]
    assert title == "Cannot determine the time window"
    assert "a.mkv" in body


def test_an_unprobed_recording_is_probed_rather_than_blamed(monkeypatch, tmp_path):
    """The background probe walks the whole folder; a user who beats it to
    this button must not be told ffprobe is broken."""
    logs = tmp_path / "logs"
    logs.mkdir()
    api, _window, rows = api_with(tmp_path,
                                  settings={"discord_webhook": HOOK,
                                            "gamelogs_dir": str(logs)})
    rows["r0"].duration = None
    rows["r0"].probed = False
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.library, "probe", lambda path, binary: (30.0, True))
    monkeypatch.setattr(api_mod.combatlog, "select_logs",
                        lambda d, s, e: combatlog.Selection(logs=[], dropped=0))

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    # KEY IS `id`, matching every other duration message.
    assert fakes.payloads(sent, "onDuration") == [
        {"id": "r0", "duration": 30.0, "definitive": True}]
    assert api._alert.titles() == ["No logs found"]


def ready_api(tmp_path, monkeypatch, logs):
    api, _window, rows = api_with(tmp_path,
                                  settings={"discord_webhook": HOOK,
                                            "gamelogs_dir": str(logs)})
    for info in rows.values():
        info.duration = 60.0
        info.probed = True
    # Field names are the real ones: SelectedLog is (path, listener,
    # span_start, span_end) -- there is no start=/end=.
    stamp = datetime.datetime(2026, 8, 21, 19, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(api_mod.combatlog, "select_logs",
                        lambda d, s, e: combatlog.Selection(
                            logs=[combatlog.SelectedLog(
                                path=logs / "x.txt", listener="Pilot",
                                span_start=stamp,
                                span_end=stamp + datetime.timedelta(minutes=5))],
                            dropped=2))
    return api, rows


def test_a_posted_archive_is_deleted_and_the_drop_note_is_appended(monkeypatch, tmp_path):
    """The status line must not report a truncated export as a complete one."""
    logs = tmp_path / "logs"
    logs.mkdir()
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    api, _rows = ready_api(tmp_path, monkeypatch, logs)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=2))
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda h, p, c: discord.PostResult(
                            ok=True, message="Posted combatlogs.zip (0.0 MB)."))

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["kind"] == "SUCCESS"
    assert "Posted combatlogs.zip" in final["text"]
    assert "2 older logs omitted" in final["text"]
    assert not archive_path.exists()


def test_a_rejected_archive_is_kept_and_its_location_named(monkeypatch, tmp_path):
    """There is no UI for selecting fewer logs, so a user told "too large"
    has no move available unless the file survives."""
    logs = tmp_path / "logs"
    logs.mkdir()
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    api, _rows = ready_api(tmp_path, monkeypatch, logs)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=0))
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda h, p, c: discord.PostResult(
                            ok=False, message="The archive is too large."))

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    assert archive_path.exists()
    kind, title, body = api._alert.raised[-1]
    assert (kind, title) == ("error", "Combat log upload failed")
    assert str(archive_path) in body
    assert fakes.payloads(sent, "onStatus")[-1]["kind"] == "ERROR"


def test_a_failure_after_the_archive_exists_still_names_it(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    api, _rows = ready_api(tmp_path, monkeypatch, logs)
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=0))

    def boom(archive, s, e):
        raise RuntimeError("manifest failed")

    monkeypatch.setattr(api_mod.combatlog, "summarize_archive", boom)

    api.upload_combat_logs(["r0"])
    api._upload_thread.join(timeout=5)

    body = api._alert.raised[-1][2]
    assert "manifest failed" in body
    assert str(archive_path) in body
