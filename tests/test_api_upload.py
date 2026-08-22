"""The upload flow across the bridge.

Every one of these ran through Tk's messagebox and widget calls before the
replatform; they are the behaviours that had no test at all because the
only thing asserting them was a widget.
"""
import datetime
import threading

import pytest

from obs_youtube_uploader import combatlog, discord, uploader
from obs_youtube_uploader.ui import api as api_mod
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
    api.start_upload("t", "d", False, False, [])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to upload.")]
    assert api._upload_thread is None


def test_stitching_one_recording_is_refused_with_its_own_message(tmp_path):
    """Distinct from the no-selection warning: the user picked something,
    it just cannot be joined to itself."""
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", True, False, ["r1"])
    assert api._alert.raised == [
        ("warning", "Stitch", "Select at least two videos to stitch.")]


def test_a_second_upload_is_refused_while_one_is_running(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    gate = threading.Event()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.start_upload("t", "d", False, False, ["r1"])
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

    api.start_upload("Fight", "d", False, False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, False, ["r1"])
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

    api.start_upload("Fight", "d", False, False, ["r1"])
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

    api.start_upload("Fight", "d", True, False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, False, ["r1", "r2"])
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

    api.start_upload("Fight", "d", False, False, ["r1"])
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

    api.start_upload("Fight", "d", True, False, ["r1", "r2"])
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
    api.start_upload("Fight", "d", False, False, ["r1", "r2"])
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
    api.start_upload("Fight", "d", False, False, ["r1"])
    join(api)
    assert (jobs[0].privacy, jobs[0].category) == ("private", "27")


def test_the_confirm_dialog_names_the_privacy_that_will_be_used(tmp_path):
    """The one place the user sees the value before it becomes permanent.
    It read as the app stating a fact while it was in truth overriding the
    setting, so it must be the same value the job carries."""
    api, _window, _rows = api_with(tmp_path, settings={"privacy": "private"})
    api._confirm = fakes.Answers(answer=False)

    api.start_upload("Fight", "d", False, False, ["r1"])
    join(api)

    (_title, body), = api._confirm.asked
    assert "private" in body
    assert "unlisted" not in body


# --- the combined upload: video, then combat logs ---------------------------

HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def test_the_confirm_names_the_discord_half_when_logs_are_requested(tmp_path):
    """One button now publishes to two places, and the confirm is the only
    screen between pressing it and the upload starting."""
    api, _window, _rows = api_with(tmp_path)
    api._confirm = fakes.Answers(answer=False)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    (_title, body), = api._confirm.asked
    assert "combat logs" in body.lower()


def test_declining_the_confirm_posts_no_logs_either(monkeypatch, tmp_path):
    """Declining must stop BOTH halves: posting to Discord is a public
    action too, and this confirm is now the only thing guarding it."""
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    api._confirm = fakes.Answers(answer=False)
    posted = []
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: posted.append(path))

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    assert posted == []


def combined_api(tmp_path, monkeypatch, settings=None, dropped=0):
    """An api whose video half and log half are both ready to succeed."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(exist_ok=True)
    cfg = {"discord_webhook": HOOK, "gamelogs_dir": str(logs_dir)}
    cfg.update(settings or {})
    api, window, rows = api_with(tmp_path, settings=cfg)
    for info in rows.infos.values():
        info.duration = 60.0
        info.probed = True

    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    stamp = datetime.datetime(2026, 8, 21, 19, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(api_mod.combatlog, "select_logs",
                        lambda d, s, e: combatlog.Selection(
                            logs=[combatlog.SelectedLog(
                                path=logs_dir / "x.txt", listener="Pilot",
                                span_start=stamp,
                                span_end=stamp + datetime.timedelta(minutes=5))],
                            dropped=dropped))
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(api_mod.combatlog, "build_archive",
                        lambda sel, out, s, e: combatlog.ArchiveResult(
                            path=archive_path, file_count=1,
                            characters=["Pilot"], raw_bytes=10, zip_bytes=3,
                            dropped=dropped))
    return api, window, rows


def test_one_upload_publishes_the_video_and_then_posts_the_logs(monkeypatch, tmp_path):
    """The whole point of the merged button: one press, both destinations,
    on one thread so the existing busy guard still covers both."""
    order = []
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    monkeypatch.setattr(uploader, "upload", lambda *a, **k: (
        order.append("video"), "vid123")[1])
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: (
                            order.append("logs"),
                            discord.PostResult(ok=True,
                                               message="Posted combatlogs.zip."))[1])

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    assert order == ["video", "logs"]
    assert api._alert.raised == []


def test_the_video_finishing_is_not_the_end_of_the_status_line(monkeypatch, tmp_path):
    """"Upload complete!" must not be the last thing said while the log half
    is still running, or a user reads the app as finished and closes it."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: discord.PostResult(
                            ok=True, message="Posted combatlogs.zip."))

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    texts = [p["text"] for p in fakes.payloads(sent, "onStatus")]
    assert "Posted combatlogs.zip." in texts[-1]
    assert texts.index("Upload complete!") < len(texts) - 1


def test_leaving_the_box_unchecked_uploads_the_video_alone(monkeypatch, tmp_path):
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    posted = []
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: posted.append(path))

    api.start_upload("Fight", "d", False, False, ["r1"])
    join(api)

    assert posted == []
    assert api._alert.raised == []


# --- a log half that cannot run must not unwin the video --------------------
#
# Each of these was a blocking warning DIALOG when combat logs had their own
# button, and every one of them refused before anything was uploaded. Merged
# into one button they cannot stay blocking: the video is on YouTube by the
# time they are reached, so the app has to report a half-done job rather
# than pretend it did nothing.

def test_an_unconfigured_webhook_skips_the_logs_and_keeps_the_video(monkeypatch, tmp_path):
    api, _window, _rows = combined_api(tmp_path, monkeypatch,
                                       settings={"discord_webhook": ""})
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    assert fakes.payloads(sent, "onLink")[0]["video_id"] == "vid123"
    final = fakes.payloads(sent, "onStatus")[-1]
    assert "combat logs skipped" in final["text"]
    assert "Settings" in final["text"]
    # Not an ERROR: the upload the user asked for did happen.
    assert final["kind"] == "WARNING"
    # And not a dialog either -- a modal apologising for the half that did
    # not run reads as though the whole thing failed.
    assert api._alert.raised == []


def test_a_missing_gamelogs_folder_skips_the_logs_and_keeps_the_video(monkeypatch, tmp_path):
    api, _window, _rows = combined_api(tmp_path, monkeypatch,
                                       settings={"gamelogs_dir": ""})
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert "combat logs skipped" in final["text"]
    assert "Gamelogs" in final["text"]
    assert api._alert.raised == []


def test_an_unreadable_duration_skips_the_logs_and_names_the_file(monkeypatch, tmp_path):
    """No duration means no start time, so there is no window to build --
    still a refusal, but one that names the file it could not measure."""
    api, _window, rows = combined_api(tmp_path, monkeypatch)
    rows.infos["r1"].duration = None
    rows.infos["r1"].probed = True
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert "combat logs skipped" in final["text"]
    assert "r1.mkv" in final["text"]
    assert api._alert.raised == []


def test_an_unprobed_recording_is_probed_rather_than_blamed(monkeypatch, tmp_path):
    """The background probe walks the whole folder; a user whose upload beats
    it to these files must not be told ffprobe is broken."""
    api, _window, rows = combined_api(tmp_path, monkeypatch)
    rows.infos["r1"].duration = None
    rows.infos["r1"].probed = False
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(api_mod.library, "probe", lambda path, binary: (30.0, True))
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: discord.PostResult(
                            ok=True, message="Posted combatlogs.zip."))

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    # KEY IS `id`, matching every other duration message.
    assert fakes.payloads(sent, "onDuration") == [
        {"id": "r1", "duration": 30.0, "definitive": True}]
    assert "Posted combatlogs.zip." in fakes.payloads(sent, "onStatus")[-1]["text"]


def test_a_failed_video_posts_no_logs_and_leaves_them_to_retry(monkeypatch, tmp_path):
    """The one direction that is all-or-nothing. Logs posted for a video
    that never published announce a fight nobody can watch, and the error
    the user must act on would be buried under a Discord success line."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    posted = []
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, object()))
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: posted.append(path))
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    assert posted == []
    assert fakes.payloads(sent, "onStatus")[-1]["kind"] == "ERROR"
    # The flag survives on the retained job, so Retry runs both halves.
    assert api._retry_state.job.logs is True


def test_a_retried_upload_still_posts_the_logs_it_promised(monkeypatch, tmp_path):
    """Retry re-runs the job the user confirmed, and that job included the
    Discord half."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    monkeypatch.setattr(uploader, "upload",
                        failing_upload(uploader.Outcome.RETRY, object()))
    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    posted = []
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: (
                            posted.append(path),
                            discord.PostResult(ok=True, message="Posted."))[1])

    api.retry()
    join(api)

    assert len(posted) == 1


# --- what the Discord post itself does --------------------------------------
#
# Moved from test_api_files.py with the button. These are about the archive
# and the post, not about the merge, and none of them changed: a genuine
# post FAILURE still alerts, because it leaves a file on disk the user has
# to be told about.

def test_a_posted_archive_is_deleted_and_the_drop_note_is_appended(monkeypatch, tmp_path):
    """The status line must not report a truncated export as a complete one."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch, dropped=2)
    sent = fakes.record_pushes(api)
    archive_path = tmp_path / "combatlogs.zip"
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: discord.PostResult(
                            ok=True, message="Posted combatlogs.zip (0.0 MB)."))

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["kind"] == "SUCCESS"
    assert "Posted combatlogs.zip" in final["text"]
    assert "2 older logs omitted" in final["text"]
    assert not archive_path.exists()


def test_a_rejected_archive_is_kept_and_its_location_named(monkeypatch, tmp_path):
    """There is no UI for selecting fewer logs, so a user told "too large"
    has no move available unless the file survives."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)
    archive_path = tmp_path / "combatlogs.zip"
    monkeypatch.setattr(api_mod.discord, "post_archive",
                        lambda hook, path, content: discord.PostResult(
                            ok=False, message="The archive is too large."))

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    assert archive_path.exists()
    kind, title, body = api._alert.raised[-1]
    assert (kind, title) == ("error", "Combat log upload failed")
    assert str(archive_path) in body
    assert fakes.payloads(sent, "onStatus")[-1]["kind"] == "ERROR"


def test_a_failure_after_the_archive_exists_still_names_it(monkeypatch, tmp_path):
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    archive_path = tmp_path / "combatlogs.zip"

    def boom(archive, start, end):
        raise RuntimeError("manifest failed")

    monkeypatch.setattr(api_mod.combatlog, "summarize_archive", boom)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    body = api._alert.raised[-1][2]
    assert "manifest failed" in body
    assert str(archive_path) in body


def test_a_crash_in_the_log_half_does_not_report_the_video_as_failed(monkeypatch, tmp_path):
    """The log half runs inside the upload worker's try block, so anything
    it raises outside _combat_log_worker's own handler -- a probe blowing
    up, a bad mtime -- would otherwise be caught by the handler for a FAILED
    UPLOAD and reported as one. The video is already on YouTube and linked
    at that point; telling the user it failed sends them to re-upload a
    video that is already public."""
    api, _window, rows = combined_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)
    rows.infos["r1"].probed = False

    def boom(path, binary):
        raise OSError("ffprobe exploded")

    monkeypatch.setattr(api_mod.library, "probe", boom)

    api.start_upload("Fight", "d", False, True, ["r1"])
    join(api)

    # The video really did publish.
    assert fakes.payloads(sent, "onLink")[0]["video_id"] == "vid123"
    assert [t for _, t, _ in api._alert.raised] != ["Upload Failed"]
    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["kind"] != "ERROR"
    assert "ffprobe exploded" in final["text"]
    # And Retry must not be offered for a video that needs no retrying.
    retries = fakes.payloads(sent, "onRetryAvailable")
    assert retries[-1] == {"available": False}


def test_the_busy_guard_still_holds_while_the_logs_are_posting(monkeypatch, tmp_path):
    """The claim the whole merge rests on: one worker thread, so the guard
    that always covered the video now covers the Discord half too. Asserted
    against _busy() directly rather than inferred from message ordering,
    because it is also what defers the watcher's list rebuild -- and a
    rebuild mid-upload would mint new row ids underneath the job."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    posting = threading.Event()
    release = threading.Event()

    def blocking_post(hook, path, content):
        posting.set()
        release.wait(timeout=5)
        return discord.PostResult(ok=True, message="Posted.")

    monkeypatch.setattr(api_mod.discord, "post_archive", blocking_post)

    api.start_upload("Fight", "d", False, True, ["r1"])
    try:
        assert posting.wait(timeout=5)
        # The video is already published and linked at this point.
        assert api._busy()
        api.start_upload("Fight again", "d", False, True, ["r2"])
        assert api._alert.raised[-1] == (
            "warning", "Busy", "An upload is already in progress.")
    finally:
        release.set()
    join(api)

