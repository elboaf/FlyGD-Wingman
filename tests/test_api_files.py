"""Deleting, opening, and copying across the bridge.

These went through Tk messageboxes and the clipboard before the
replatform. The confirmations and the partial-failure handling are the
parts with real consequences on disk.

The combat-log tests used to live here, beside the button that ran them.
They moved to test_api_upload.py when that button merged into Upload:
posting logs is now the second half of an upload, not an action of its own.
"""

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
