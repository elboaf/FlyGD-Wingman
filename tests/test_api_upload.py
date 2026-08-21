"""The upload flow across the bridge.

Every one of these ran through Tk's messagebox and widget calls before the
replatform; they are the behaviours that had no test at all because the
only thing asserting them was a widget.
"""
import threading

import pytest

from obs_youtube_uploader import uploader
from tests import fakes


def api_with(tmp_path, ids=("r1", "r2"), **kw):
    rows = fakes.FakeRows({rid: fakes.info(tmp_path / f"{rid}.mkv") for rid in ids})
    api, window = fakes.build_api(tmp_path, rows=rows, **kw)
    api._alert = fakes.Alerts()
    api._confirm = fakes.Answers()
    return api, window, rows


def join(api):
    thread = api._upload_thread
    if thread is not None:
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_uploading_nothing_says_so_rather_than_starting_an_empty_job(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", "unlisted", "20", False, [])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to upload.")]
    assert api._upload_thread is None


def test_stitching_one_recording_is_refused_with_its_own_message(tmp_path):
    """Distinct from the no-selection warning: the user picked something,
    it just cannot be joined to itself."""
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", "unlisted", "20", True, ["r1"])
    assert api._alert.raised == [
        ("warning", "Stitch", "Select at least two videos to stitch.")]


def test_a_second_upload_is_refused_while_one_is_running(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    gate = threading.Event()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.start_upload("t", "d", "unlisted", "20", False, ["r1"])
        assert api._alert.raised == [
            ("warning", "Busy", "An upload is already in progress.")]
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)


def test_publishing_confirms_first_and_declining_uploads_nothing(monkeypatch, tmp_path):
    """The app's only irreversible action. 2.2.0 added this confirm
    deliberately; the port must not quietly drop it."""
    api, _window, _rows = api_with(tmp_path, settings={"channel_title": "Zoolanders"})
    api._confirm = fakes.Answers(answer=False)
    called = []
    monkeypatch.setattr(uploader, "upload", lambda *a, **k: called.append(a))
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())

    api.start_upload("Fight", "d", "public", "20", False, ["r1", "r2"])
    join(api)

    assert called == []
    (title, body), = api._confirm.asked
    assert title == "Confirm Upload"
    # Built through format_upload_confirm, so the numbering shown is the
    # numbering build_body will send.
    assert "Zoolanders" in body
    assert "public" in body
    assert '"Fight (1/2)"' in body and '"Fight (2/2)"' in body
    assert "cannot be undone" in body


def fake_upload_ok(video_id="vid123", channel=("UC1", "Zoolanders"), fractions=(0.5, 1.0)):
    """uploader.upload's contract: drive on_progress, then on_response."""
    def _upload(request, *, on_progress=None, on_retry=None, on_response=None,
                **kw):
        for fraction in fractions:
            if on_progress is not None:
                on_progress(fraction)
        if on_response is not None:
            on_response({"id": video_id,
                         "snippet": {"channelId": channel[0],
                                     "channelTitle": channel[1]}})
        return video_id
    return _upload


def test_a_finished_upload_links_every_row_it_covered(monkeypatch, tmp_path):
    api, window, rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1", "r2"])
    join(api)

    links = fakes.payloads(sent, "onLink")
    # KEY IS `id`: the page's onLink handler looks up the row by that field.
    assert [l["id"] for l in links] == ["r1", "r2"]
    assert rows.links == {"r1": "vid123", "r2": "vid123"}
    # The messages really went through evaluate_js, not just through the spy.
    assert window.calls


def test_progress_text_names_the_file_and_the_bar_tracks_the_batch(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok(fractions=(0.5,)))

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1", "r2"])
    join(api)

    bars = [p for p in fakes.payloads(sent, "onProgress") if p["text"]]
    assert bars[0] == {"mode": "determinate", "pct": 25.0,
                       "text": "Uploading file 1 of 2… 50.0%", "kind": "FG"}


def test_the_destination_channel_is_learned_and_persisted(monkeypatch, tmp_path):
    """Replaces test_app_last_upload, which drove a real window: the channel
    is the only thing the app ever learns about where uploads land, because
    it holds the youtube.upload scope alone."""
    saved = {}
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())
    monkeypatch.setattr("obs_youtube_uploader.ui.api.settings_mod.save",
                        lambda cfg, path=None: saved.update(cfg))

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1"])
    join(api)

    channel, = fakes.payloads(sent, "onChannel")
    assert channel["channel_id"] == "UC1"
    assert channel["channel_title"] == "Zoolanders"
    # The rendered line rides along, so the page never composes it.
    assert channel["destination"] == "Uploads go to Zoolanders · unlisted"
    assert saved["channel_title"] == "Zoolanders"
    assert api._state.settings["channel_id"] == "UC1"


def test_a_completed_upload_clears_retry_and_says_so(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", "unlisted", "20", False, ["r1"])
    join(api)

    assert {"text": "Upload complete!", "kind": "SUCCESS"} in fakes.payloads(sent, "onStatus")
    assert fakes.payloads(sent, "onRetryAvailable")[-1] == {"available": False}
    assert api._retry_state is None


def test_stitching_switches_the_bar_to_indeterminate_and_back(monkeypatch, tmp_path):
    """ffmpeg reports no progress this code can read, and a multi-gigabyte
    join is seconds of no other signal to the user."""
    import contextlib

    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    @contextlib.contextmanager
    def fake_stitched(sources, ffmpeg_bin, tmp):
        yield tmp_path / "merged.mkv"

    monkeypatch.setattr("obs_youtube_uploader.ui.api.stitch.stitched", fake_stitched)

    api.start_upload("Fight", "d", "unlisted", "20", True, ["r1", "r2"])
    join(api)

    modes = [p["mode"] for p in fakes.payloads(sent, "onProgress")]
    assert modes[0] == "indeterminate"
    assert "determinate" in modes[1:]
    # One stitched video, but every source row gets the link.
    assert sorted(l["id"] for l in fakes.payloads(sent, "onLink")) == ["r1", "r2"]
