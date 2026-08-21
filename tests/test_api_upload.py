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
    api.start_upload("t", "d", False, [])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to upload.")]
    assert api._upload_thread is None


def test_stitching_one_recording_is_refused_with_its_own_message(tmp_path):
    """Distinct from the no-selection warning: the user picked something,
    it just cannot be joined to itself."""
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", True, ["r1"])
    assert api._alert.raised == [
        ("warning", "Stitch", "Select at least two videos to stitch.")]


def test_a_second_upload_is_refused_while_one_is_running(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    gate = threading.Event()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.start_upload("t", "d", False, ["r1"])
        assert api._alert.raised == [
            ("warning", "Busy", "An upload is already in progress.")]
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)


def test_publishing_confirms_first_and_declining_uploads_nothing(monkeypatch, tmp_path):
    """The app's only irreversible action. 2.2.0 added this confirm
    deliberately; the port must not quietly drop it."""
    api, _window, _rows = api_with(tmp_path, settings={"channel_title": "Zoolanders",
                                                       "privacy": "public"})
    api._confirm = fakes.Answers(answer=False)
    called = []
    monkeypatch.setattr(uploader, "upload", lambda *a, **k: called.append(a))
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())

    api.start_upload("Fight", "d", False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    channel, = fakes.payloads(sent, "onChannel")
    assert channel["channel_id"] == "UC1"
    assert channel["channel_title"] == "Zoolanders"
    # The rendered line rides along, so the page never composes it.
    assert channel["destination"] == "Uploads go to Zoolanders"
    assert saved["channel_title"] == "Zoolanders"
    assert api._state.settings["channel_id"] == "UC1"

    # Learning the channel is the moment the Settings account line can stop
    # saying a bare "Connected", so it is refreshed here rather than at the
    # next launch -- otherwise the very session that learned the name shows
    # the least informative version of it.
    state, = fakes.payloads(sent, "onAuthState")
    assert state == {"state": "connected", "message": "Connected as Zoolanders"}


def test_a_completed_upload_clears_retry_and_says_so(monkeypatch, tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1"])
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

    api.start_upload("Fight", "d", True, ["r1", "r2"])
    join(api)

    modes = [p["mode"] for p in fakes.payloads(sent, "onProgress")]
    assert modes[0] == "indeterminate"
    assert "determinate" in modes[1:]
    # One stitched video, but every source row gets the link.
    assert sorted(l["id"] for l in fakes.payloads(sent, "onLink")) == ["r1", "r2"]


def failing_upload(outcome, request=object()):
    def _upload(req, **kw):
        raise uploader.UploadFailed(outcome, request=request)
    return _upload


def test_a_retryable_failure_offers_retry_and_keeps_the_session(monkeypatch, tmp_path):
    session = object()
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, session))

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    assert fakes.payloads(sent, "onRetryAvailable")[-1] == {"available": True}
    assert api._retry_state.request is session
    assert api._retry_state.resume_index == 0
    assert api._alert.raised[-1][0] == "error"


def test_a_permanent_failure_offers_no_retry_and_drops_the_session(monkeypatch, tmp_path):
    """A non-RETRY outcome cannot be resumed, and holding the request would
    keep an open handle on the user's own recording -- which blocks
    renaming or deleting it on Windows."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.QUOTA, object()))

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert fakes.payloads(sent, "onRetryAvailable") == []
    assert api._retry_state.request is None


def test_a_stitched_failure_cannot_resume_even_when_retryable(monkeypatch, tmp_path):
    """The context manager has already deleted the merged file the resumable
    session points at. Retry re-stitches from scratch instead."""
    import contextlib

    api, _window, _rows = api_with(tmp_path)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, object()))

    @contextlib.contextmanager
    def fake_stitched(sources, ffmpeg_bin, tmp):
        yield tmp_path / "merged.mkv"

    monkeypatch.setattr("obs_youtube_uploader.ui.api.stitch.stitched", fake_stitched)

    api.start_upload("Fight", "d", True, ["r1", "r2"])
    join(api)

    assert api._retry_state.request is None
    assert api._retry_state.job.stitch is True


def test_retry_resumes_the_session_then_finishes_the_rest(monkeypatch, tmp_path):
    session = object()
    resumed = []
    api, _window, _rows = api_with(tmp_path)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, session))
    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    def resume(req, *, on_progress=None, on_retry=None, on_response=None, **kw):
        resumed.append(req)
        if on_progress is not None:
            on_progress(1.0)
        return "vidA" if req is session else "vidB"

    monkeypatch.setattr(uploader, "upload", resume)
    sent = fakes.record_pushes(api)
    api.retry()
    join(api)

    # The FIRST call reuses the stored session -- that is what makes this
    # resume rather than restart -- and the second file follows on.
    assert resumed[0] is session
    assert [l["video_id"] for l in fakes.payloads(sent, "onLink")] == ["vidA", "vidB"]
    assert fakes.payloads(sent, "onRetryAvailable")[0] == {"available": False}
    assert api._retry_state is None


def test_retry_with_nothing_to_retry_does_nothing(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    api.retry()
    assert sent == []
    assert api._upload_thread is None


def test_the_stored_privacy_and_category_decide_the_upload(monkeypatch, tmp_path):
    """The page cannot choose the privacy of a video, because it does not
    hold one to choose.

    The bridge's first version took privacy and category as arguments and
    the page held its own defaults, so every upload before Settings was
    saved in that session went out `unlisted`/`20` -- a user set to
    `private` silently published a link anyone could open. The Tk build
    read self.state.settings at dispatch time; so does this.
    """
    api, _window, _rows = api_with(
        tmp_path, settings={"privacy": "private", "category": "27"})
    jobs = []
    monkeypatch.setattr(api, "_confirm_then_upload", lambda job: jobs.append(job))
    api.start_upload("Fight", "d", False, ["r1"])
    join(api)
    assert (jobs[0].privacy, jobs[0].category) == ("private", "27")


def test_the_confirm_dialog_names_the_privacy_that_will_be_used(tmp_path):
    """The one place the user sees the value before it becomes permanent.
    It read as the app stating a fact while it was in truth overriding the
    setting, so it must be the same value the job carries."""
    api, _window, _rows = api_with(tmp_path, settings={"privacy": "private"})
    api._confirm = fakes.Answers(answer=False)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    (_title, body), = api._confirm.asked
    assert "private" in body
    assert "unlisted" not in body
