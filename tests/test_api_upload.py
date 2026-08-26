"""The upload flow across the bridge.

Every one of these ran through Tk's messagebox and widget calls before the
replatform; they are the behaviours that had no test at all because the
only thing asserting them was a widget.
"""

import datetime
import threading

from obs_youtube_uploader import combatlog, discord, library, uploader
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
    api.start_upload("t", "d", False, [])
    assert api._alert.raised == [
        ("warning", "No Selection", "Select at least one video to upload.")
    ]
    assert api._upload_thread is None


def test_stitching_one_recording_is_refused_with_its_own_message(tmp_path):
    """Distinct from the no-selection warning: the user picked something,
    it just cannot be joined to itself."""
    api, _window, _rows = api_with(tmp_path)
    api.start_upload("t", "d", True, ["r1"])
    assert api._alert.raised == [
        ("warning", "Stitch", "Select at least two videos to stitch.")
    ]


def test_a_second_upload_is_refused_while_one_is_running(tmp_path):
    api, _window, _rows = api_with(tmp_path)
    gate = threading.Event()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        api.start_upload("t", "d", False, ["r1"])
        assert api._alert.raised == [
            ("warning", "Busy", "An upload is already in progress.")
        ]
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)


def test_publishing_confirms_first_and_declining_uploads_nothing(monkeypatch, tmp_path):
    """The app's only irreversible action. 2.2.0 added this confirm
    deliberately; the port must not quietly drop it."""
    api, _window, _rows = api_with(
        tmp_path, settings={"channel_title": "Zoolanders", "privacy": "public"}
    )
    api._confirm = fakes.Answers(answer=False)
    called = []
    monkeypatch.setattr(uploader, "upload", lambda *a, **k: called.append(a))
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    assert called == []
    ((title, body),) = api._confirm.asked
    assert title == "Confirm Upload"
    # Built through format_upload_confirm, so the numbering shown is the
    # numbering build_body will send.
    assert "Zoolanders" in body
    assert "public" in body
    assert '"Fight (1/2)"' in body and '"Fight (2/2)"' in body
    assert "cannot be undone" in body


def fake_upload_ok(
    video_id="vid123", channel=("UC1", "Zoolanders"), fractions=(0.5, 1.0)
):
    """uploader.upload's contract: drive on_progress, then on_response."""

    def _upload(request, *, on_progress=None, on_retry=None, on_response=None, **kw):
        for fraction in fractions:
            if on_progress is not None:
                on_progress(fraction)
        if on_response is not None:
            on_response(
                {
                    "id": video_id,
                    "snippet": {"channelId": channel[0], "channelTitle": channel[1]},
                }
            )
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
    assert [link["id"] for link in links] == ["r1", "r2"]
    assert rows.links == {"r1": "vid123", "r2": "vid123"}
    # The messages really went through evaluate_js, not just through the spy.
    assert window.calls


def test_progress_text_names_the_file_and_the_bar_tracks_the_batch(
    monkeypatch, tmp_path
):
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok(fractions=(0.5,)))

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    bars = [p for p in fakes.payloads(sent, "onProgress") if p["text"]]
    assert bars[0] == {
        "mode": "determinate",
        "pct": 25.0,
        "text": "Uploading file 1 of 2… 50%",
        "kind": "FG",
        # An upload in flight. The page never clears a busy strip: it is
        # the only feedback there is while this runs (round 3, finding 12).
        "busy": True,
    }


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
    # _remember_channel now writes through settings_mod.update(), which
    # calls _save_locked internally rather than save() directly.
    monkeypatch.setattr(
        "obs_youtube_uploader.ui.api.settings_mod._save_locked",
        lambda data, path=None: saved.update(data),
    )

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    (channel,) = fakes.payloads(sent, "onChannel")
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
    (state,) = fakes.payloads(sent, "onAuthState")
    assert state == {"state": "connected", "message": "Connected as Zoolanders"}


def test_a_completed_upload_clears_retry_and_says_so(monkeypatch, tmp_path):
    """Round 3, finding 13: the terminal line names the action, the title
    and the destination. It used to say "Upload complete!", which the
    combat-log tail then overwrote outright -- so the last word on the
    app's one irreversible action was about the side-effect.

    The title comes through uploader.build_body, the same route
    format_upload_confirm takes, so the strip names the video the way
    YouTube does rather than echoing the raw field.
    """
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert {
        "text": 'Uploaded "Fight" to YouTube.',
        "kind": "SUCCESS",
        # Terminal, so the page may clear it when the route changes.
        "busy": False,
    } in fakes.payloads(sent, "onStatus")
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
    assert sorted(link["id"] for link in fakes.payloads(sent, "onLink")) == ["r1", "r2"]


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
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.RETRY, session)
    )

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    assert fakes.payloads(sent, "onRetryAvailable")[-1] == {"available": True}
    assert api._retry_state.request is session
    assert api._retry_state.resume_index == 0
    assert api._alert.raised[-1][0] == "error"


def test_a_permanent_failure_offers_no_retry_and_drops_the_session(
    monkeypatch, tmp_path
):
    """A non-RETRY outcome cannot be resumed, and holding the request would
    keep an open handle on the user's own recording -- which blocks
    renaming or deleting it on Windows."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.QUOTA, object())
    )

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
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.RETRY, object())
    )

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
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.RETRY, session)
    )
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
    assert [link["video_id"] for link in fakes.payloads(sent, "onLink")] == [
        "vidA",
        "vidB",
    ]
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
        tmp_path, settings={"privacy": "private", "category": "27"}
    )
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

    ((_title, body),) = api._confirm.asked
    assert "private" in body
    assert "unlisted" not in body


# --- the combined upload: video, then combat logs ---------------------------

HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def test_the_confirm_names_the_discord_half_when_logs_are_requested(tmp_path):
    """One button now publishes to two places, and the confirm is the only
    screen between pressing it and the upload starting.

    A webhook is configured here on purpose: the promise is only made when
    it will be kept, which the test below is the other half of."""
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    api._confirm = fakes.Answers(answer=False)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    ((_title, body),) = api._confirm.asked
    assert "combat logs" in body.lower()


def test_the_confirm_withdraws_the_discord_promise_on_a_fresh_install(tmp_path):
    """No webhook is configured -- the state every fresh install starts in.

    Api reads the webhook out of live settings and hands it to the confirm,
    which parses it with the same discord.parse_webhook _post_combat_logs
    gates on. This is the wiring test for that: the formatter's own
    branches are covered in tests/test_app_upload_copy.py, but nothing
    there proves Api passes the real value rather than a default.
    """
    api, _window, _rows = api_with(tmp_path)
    api._confirm = fakes.Answers(answer=False)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    ((_title, body),) = api._confirm.asked
    assert "posted to Discord" not in body
    assert "not posted" in body


def test_declining_the_confirm_posts_no_logs_either(monkeypatch, tmp_path):
    """Declining must stop BOTH halves: posting to Discord is a public
    action too, and this confirm is now the only thing guarding it."""
    api, _window, _rows = api_with(tmp_path, settings={"discord_webhook": HOOK})
    api._confirm = fakes.Answers(answer=False)
    posted = []
    monkeypatch.setattr(
        api_mod.discord, "post_archive", lambda hook, path, content: posted.append(path)
    )

    api.start_upload("Fight", "d", False, ["r1"])
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

    stamp = datetime.datetime(2026, 8, 21, 19, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(
        api_mod.combatlog,
        "select_logs",
        lambda d, s, e: combatlog.Selection(
            logs=[
                combatlog.SelectedLog(
                    path=logs_dir / "x.txt",
                    listener="Pilot",
                    span_start=stamp,
                    span_end=stamp + datetime.timedelta(minutes=5),
                )
            ],
            dropped=dropped,
        ),
    )
    archive_path = tmp_path / "combatlogs.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(
        api_mod.combatlog,
        "build_archive",
        lambda sel, out, s, e: combatlog.ArchiveResult(
            path=archive_path,
            file_count=1,
            characters=["Pilot"],
            raw_bytes=10,
            zip_bytes=3,
            dropped=dropped,
        ),
    )
    return api, window, rows


def test_one_upload_publishes_the_video_and_then_posts_the_logs(monkeypatch, tmp_path):
    """The whole point of the merged button: one press, both destinations,
    on one thread so the existing busy guard still covers both."""
    order = []
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    monkeypatch.setattr(
        uploader, "upload", lambda *a, **k: (order.append("video"), "vid123")[1]
    )
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: (
            order.append("logs"),
            discord.PostResult(ok=True, message="Posted combatlogs.zip."),
        )[1],
    )

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert order == ["video", "logs"]
    assert api._alert.raised == []


def test_the_video_finishing_is_not_the_end_of_the_status_line(monkeypatch, tmp_path):
    """The upload summary must not be the last thing said while the log half
    is still running, or a user reads the app as finished and closes it.

    And the line that DOES land last still leads with the upload: round 3's
    finding 13 caught the version where "Posted combatlogs-....zip (15 KB)."
    replaced it outright and the words uploaded / YouTube / the title
    appeared nowhere on a successful upload.
    """
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: discord.PostResult(
            ok=True, message="Posted combatlogs.zip."
        ),
    )

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    texts = [p["text"] for p in fakes.payloads(sent, "onStatus")]
    assert texts[-1] == 'Uploaded "Fight" to YouTube. Posted combatlogs.zip.'
    assert texts.index('Uploaded "Fight" to YouTube.') < len(texts) - 1
    # Every line left behind is settled; nothing is still running.
    assert fakes.payloads(sent, "onStatus")[-1]["busy"] is False


def test_logs_are_posted_without_being_asked_for(monkeypatch, tmp_path):
    """Uploader 8: the checkbox had no true second state, so logs are
    unconditional and a configured webhook is what decides the post.

    start_upload takes four arguments now, not five. S3 left `logs`
    accepted-and-ignored so the page could keep calling with the old shape
    until R1 removed the control; the control is gone, so the parameter
    went with it in the same commit. This asserts the whole of what
    replaced it: nothing on the call names logs, and the logs are posted
    anyway.
    """
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    posted = []
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: (
            posted.append(path),
            discord.PostResult(ok=True, message="Posted combatlogs.zip."),
        )[1],
    )

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert len(posted) == 1
    assert api._alert.raised == []


# --- a log half that cannot run must not unwin the video --------------------
#
# Each of these was a blocking warning DIALOG when combat logs had their own
# button, and every one of them refused before anything was uploaded. Merged
# into one button they cannot stay blocking: the video is on YouTube by the
# time they are reached, so the app has to report a half-done job rather
# than pretend it did nothing.


def test_an_unconfigured_webhook_says_nothing_at_all(monkeypatch, tmp_path):
    """No webhook is a fact about the install, not a skipped request.

    This used to end on a WARNING strip, and that was right while a ticked
    checkbox meant the user had asked for logs on this run. Uploader 8
    removed the checkbox, so nobody asked -- and reporting a skip anyway
    would put a warning on every upload a webhook-less install ever
    performs. That is the exact failure format_upload_confirm's docstring
    records: a strip "reading like a recurring failure rather than an
    unconfigured option".

    The fact belongs on the panel, where it is true all the time. R1
    renders it there.
    """
    api, _window, _rows = combined_api(
        tmp_path, monkeypatch, settings={"discord_webhook": ""}
    )
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert fakes.payloads(sent, "onLink")[0]["video_id"] == "vid123"
    final = fakes.payloads(sent, "onStatus")[-1]
    assert "skipped" not in final["text"].lower()
    assert final["kind"] != "WARNING"
    assert api._alert.raised == []


def test_a_webhook_that_does_not_parse_still_warns(monkeypatch, tmp_path):
    """The counterpart to the above, and the reason it checks emptiness
    rather than just `hook is None`.

    A user who PUT something in the field and got it wrong has a real
    problem, and nothing else in the app will tell them: the field's own
    validation ran when they typed it, not on this upload. Configured and
    unusable keeps the strip; never configured does not.
    """
    api, _window, _rows = combined_api(
        tmp_path, monkeypatch, settings={"discord_webhook": "https://example.com/nope"}
    )
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert fakes.payloads(sent, "onLink")[0]["video_id"] == "vid123"
    final = fakes.payloads(sent, "onStatus")[-1]
    # Finding 13's invariant on the skip path too: whatever went wrong with
    # the logs, the sentence still opens with the upload that worked.
    assert final["text"].startswith('Uploaded "Fight" to YouTube. ')
    assert "Combat logs skipped" in final["text"]
    assert "Settings" in final["text"]
    # Not an ERROR: the upload the user asked for did happen.
    assert final["kind"] == "WARNING"
    # And not a dialog either -- a modal apologising for the half that did
    # not run reads as though the whole thing failed.
    assert api._alert.raised == []


def test_a_missing_gamelogs_folder_skips_the_logs_and_keeps_the_video(
    monkeypatch, tmp_path
):
    api, _window, _rows = combined_api(
        tmp_path, monkeypatch, settings={"gamelogs_dir": ""}
    )
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert "Combat logs skipped" in final["text"]
    assert "Gamelogs" in final["text"]
    assert api._alert.raised == []


def test_an_unreadable_duration_skips_the_logs_and_names_the_file(
    monkeypatch, tmp_path
):
    """No duration means no start time, so there is no window to build --
    still a refusal, but one that names the file it could not measure."""
    api, _window, rows = combined_api(tmp_path, monkeypatch)
    rows.infos["r1"].duration = None
    rows.infos["r1"].probed = True
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert "Combat logs skipped" in final["text"]
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
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: discord.PostResult(
            ok=True, message="Posted combatlogs.zip."
        ),
    )

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    # KEY IS `id`, matching every other duration message.
    assert fakes.payloads(sent, "onDuration") == [
        {"id": "r1", "duration": library.format_duration(30.0), "definitive": True}
    ]
    assert "Posted combatlogs.zip." in fakes.payloads(sent, "onStatus")[-1]["text"]


def test_a_failed_video_posts_no_logs_and_leaves_them_to_retry(monkeypatch, tmp_path):
    """The one direction that is all-or-nothing. Logs posted for a video
    that never published announce a fight nobody can watch, and the error
    the user must act on would be buried under a Discord success line."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    posted = []
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.RETRY, object())
    )
    monkeypatch.setattr(
        api_mod.discord, "post_archive", lambda hook, path, content: posted.append(path)
    )
    sent = fakes.record_pushes(api)

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert posted == []
    assert fakes.payloads(sent, "onStatus")[-1]["kind"] == "ERROR"
    # The flag survives on the retained job, so Retry runs both halves.
    assert api._retry_state.job.logs is True


def test_a_retried_upload_still_posts_the_logs_it_promised(monkeypatch, tmp_path):
    """Retry re-runs the job the user confirmed, and that job included the
    Discord half."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch)
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.RETRY, object())
    )
    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    posted = []
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: (
            posted.append(path),
            discord.PostResult(ok=True, message="Posted."),
        )[1],
    )

    api.retry()
    join(api)

    assert len(posted) == 1


# --- what the Discord post itself does --------------------------------------
#
# Moved from test_api_files.py with the button. These are about the archive
# and the post, not about the merge, and none of them changed: a genuine
# post FAILURE still alerts, because it leaves a file on disk the user has
# to be told about.


def test_a_posted_archive_is_deleted_and_the_drop_note_is_appended(
    monkeypatch, tmp_path
):
    """The status line must not report a truncated export as a complete one."""
    api, _window, _rows = combined_api(tmp_path, monkeypatch, dropped=2)
    sent = fakes.record_pushes(api)
    archive_path = tmp_path / "combatlogs.zip"
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: discord.PostResult(
            ok=True, message="Posted combatlogs.zip (0.0 MB)."
        ),
    )

    api.start_upload("Fight", "d", False, ["r1"])
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
    monkeypatch.setattr(
        api_mod.discord,
        "post_archive",
        lambda hook, path, content: discord.PostResult(
            ok=False, message="The archive is too large."
        ),
    )

    api.start_upload("Fight", "d", False, ["r1"])
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

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    body = api._alert.raised[-1][2]
    assert "manifest failed" in body
    assert str(archive_path) in body


def test_a_crash_in_the_log_half_does_not_report_the_video_as_failed(
    monkeypatch, tmp_path
):
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

    api.start_upload("Fight", "d", False, ["r1"])
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

    api.start_upload("Fight", "d", False, ["r1"])
    try:
        assert posting.wait(timeout=5)
        # The video is already published and linked at this point.
        assert api._busy()
        api.start_upload("Fight again", "d", False, ["r2"])
        assert api._alert.raised[-1] == (
            "warning",
            "Busy",
            "An upload is already in progress.",
        )
    finally:
        release.set()
    join(api)


# ----- the status strip's `busy` flag, and what it is for --------------------
# Round 3, lane L7. The strip is global chrome and app.js deliberately never
# tells Python which route is showing, so `busy` on the payload is the only
# thing that lets the page tell a RESULT (clearable when the route changes --
# finding 14) from something STILL RUNNING (never clearable -- finding 12).


def test_every_strip_push_goes_through_the_two_helpers():
    """A raw _push("onStatus") anywhere else ships a payload with no `busy`
    key, which the page reads as falsy -- i.e. as a finished job -- and the
    strip then clears itself out from under a live operation. Nothing
    executes the page, so this is the only thing that catches a new push
    site forgetting the flag.

    Walks the AST rather than counting substrings. A count is satisfied by
    the wrong two lines: the comment above the helpers quotes both literals,
    so reword the comment and the build goes red for no reason, while
    deleting the comment AND adding a raw push leaves the count untouched
    and ships the bug. The tree cannot be fooled either way.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(api_mod))
    helpers = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in ("_status", "_progress")
    }
    assert set(helpers) == {"_status", "_progress"}

    def strip_pushes(node):
        return {
            call.lineno
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "_push"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value in ("onStatus", "onProgress")
        }

    everywhere = strip_pushes(tree)
    inside = strip_pushes(helpers["_status"]) | strip_pushes(helpers["_progress"])
    assert everywhere == inside, (
        f"strip pushes outside _status/_progress at lines {sorted(everywhere - inside)}"
    )
    assert len(inside) == 2


def test_an_upload_in_flight_is_marked_busy_and_its_result_is_not(
    monkeypatch, tmp_path
):
    """The whole of finding 14 in one assertion: everything the strip is
    left holding after the job is settled, and nothing during it is."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok(fractions=(0.5,)))

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    strip = fakes.payloads(sent, "onStatus") + fakes.payloads(sent, "onProgress")
    assert strip, "the upload said nothing at all"
    assert all("busy" in p for p in strip)
    # Mid-flight progress is busy...
    live = [p for p in fakes.payloads(sent, "onProgress") if p["text"]]
    assert live and all(p["busy"] is True for p in live)
    # ...and the last word on the job is not.
    assert fakes.payloads(sent, "onStatus")[-1]["busy"] is False
    assert fakes.payloads(sent, "onProgress")[-1]["busy"] is False


def test_a_stitch_is_busy_so_a_route_change_cannot_blank_it(monkeypatch, tmp_path):
    """The case that rules out "just clear the strip on every route change":
    ffmpeg reports no progress this code can read, so a multi-gigabyte join
    can go minutes between pushes. Cleared, the app would look idle while it
    was working, with nothing due to repaint it.
    """
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

    (indeterminate,) = [
        p for p in fakes.payloads(sent, "onProgress") if p["mode"] == "indeterminate"
    ]
    assert indeterminate["busy"] is True


def test_a_failed_upload_leaves_a_settled_strip(monkeypatch, tmp_path):
    """An error is a result too. Left busy, the page would preserve a red
    line about a job that ended across every route for the rest of the
    session -- which is finding 14 again, in the other colour."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(
        uploader, "upload", failing_upload(uploader.Outcome.RETRY, object())
    )

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    final = fakes.payloads(sent, "onStatus")[-1]
    assert final["kind"] == "ERROR"
    assert final["busy"] is False


def test_a_batch_names_the_count_rather_than_one_title(monkeypatch, tmp_path):
    """build_body numbers a batch, so there is no single name to give and
    claiming one would be false. The noun matches the confirm the user just
    read ("3 recordings"), per the derived-not-retyped rule."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    assert (
        fakes.payloads(sent, "onStatus")[-1]["text"]
        == "Uploaded 2 recordings to YouTube."
    )


def test_a_stitched_batch_is_one_video_and_takes_the_title_form(monkeypatch, tmp_path):
    """Stitching collapses a batch into ONE video, so the summary branches
    the same way format_upload_confirm does."""
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

    assert (
        fakes.payloads(sent, "onStatus")[-1]["text"] == 'Uploaded "Fight" to YouTube.'
    )


def test_an_unrelated_worker_cannot_settle_the_strip_mid_upload(monkeypatch, tmp_path):
    """The strip is one shared surface with more than one writer.

    Delete, Copy link, Open folder and the Profiles half are all reachable
    while an upload runs, and each ends on a line of its own. Written as a
    plain busy=False those lines settle the strip on behalf of a job that is
    still going, and the next route change blanks it -- finding 14 in
    reverse, reached through a door the upload path does not control. So
    `busy` defaults to _busy() rather than to False.

    The case that makes it matter is a stitch: it reports no progress this
    code can read, so nothing is due to repaint the strip for minutes.
    """
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    gate = threading.Event()
    api._upload_thread = threading.Thread(target=gate.wait, daemon=True)
    api._upload_thread.start()
    try:
        assert api._busy()
        api._links["r1"] = "https://www.youtube.com/watch?v=abc"
        api.copy_path("r1")
        assert fakes.payloads(sent, "onStatus")[-1]["busy"] is True
    finally:
        gate.set()
        api._upload_thread.join(timeout=5)

    # And with nothing running it settles, as it always did.
    api.copy_path("r1")
    assert fakes.payloads(sent, "onStatus")[-1]["busy"] is False


# ---- stopping an upload (D5) --------------------------------------------
# The rule these exist to hold: a stop is not a failure, and it never
# reports that nothing happened. The plain path links each video as it
# lands, so a batch stopped part-way leaves finished, public videos on the
# channel -- and the message is the only thing on screen that says so.


def cancelling_upload(api, cancel_before_index):
    """uploader.upload's contract, plus the cancel poll the real one runs.

    Mirrors the real loop's ORDER deliberately: the predicate is checked
    before the chunk is sent, so a stop requested during item N leaves
    items 0..N-1 uploaded and N not.
    """
    seen = {"index": 0}

    def _upload(request, *, on_progress=None, should_cancel=None, **kw):
        index = seen["index"]
        seen["index"] += 1
        if index == cancel_before_index:
            api.cancel_upload()
        if should_cancel is not None and should_cancel():
            raise uploader.UploadCancelled()
        if on_progress is not None:
            on_progress(1.0)
        return f"vid{index}"

    return _upload


def test_stopping_a_batch_reports_what_actually_reached_the_channel(
    monkeypatch, tmp_path
):
    """The card's worked example: two of four, and the two are still up."""
    api, _window, rows = api_with(tmp_path, ids=("r1", "r2", "r3", "r4"))
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", cancelling_upload(api, 2))

    api.start_upload("Fight", "d", False, ["r1", "r2", "r3", "r4"])
    join(api)

    # Two finished and were linked; the stop did not un-upload them.
    assert [link["id"] for link in fakes.payloads(sent, "onLink")] == ["r1", "r2"]
    assert set(rows.links) == {"r1", "r2"}
    statuses = fakes.payloads(sent, "onStatus")
    assert statuses[-1]["text"] == "Stopped. 2 of 4 uploaded."
    # Not an error -- the user asked for it.
    assert statuses[-1]["kind"] == "WARNING"
    assert statuses[-1]["busy"] is False


def test_stopping_before_anything_lands_says_nothing_was_uploaded(
    monkeypatch, tmp_path
):
    api, _window, rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", cancelling_upload(api, 0))

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    assert rows.links == {}
    assert fakes.payloads(sent, "onStatus")[-1]["text"] == (
        "Stopped. Nothing was uploaded."
    )


def test_a_stop_never_offers_retry(monkeypatch, tmp_path):
    """D5, and the reason is the shared slot: Retry recovers from a
    failure, and a stop is not one. Offering it would also re-arm the slot
    the Cancel button was occupying a moment earlier."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", cancelling_upload(api, 0))

    api.start_upload("Fight", "d", False, ["r1", "r2"])
    join(api)

    assert api._retry_state is None
    assert {"available": True} not in fakes.payloads(sent, "onRetryAvailable")


def test_the_cancel_control_is_disarmed_however_the_job_ends(monkeypatch, tmp_path):
    """Armed for the upload phase, and off again on every exit -- success
    included, because the slot is shared with Retry."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    armed = fakes.payloads(sent, "onCancelAvailable")
    assert armed[0] == {"available": True}
    assert armed[-1] == {"available": False}


def test_the_cancel_control_goes_before_the_combat_log_half_runs(monkeypatch, tmp_path):
    """The video is up and nothing polls the flag any more, but the log
    post still runs on this thread and can take seconds. A Cancel left
    armed across it is a live button that does nothing."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    names = [name for name, _ in sent]
    done_at = names.index("onUploadDone")
    disarms = [
        i
        for i, (name, payload) in enumerate(sent)
        if name == "onCancelAvailable" and payload == {"available": False}
    ]
    # A disarm lands BEFORE the completion event, not only in the worker's
    # finally afterwards. The trailing one is the backstop for the paths
    # that never reach _upload_done, and it is allowed to be there too.
    assert any(i < done_at for i in disarms), (
        "the cancel control is still armed while the combat-log half runs"
    )


def test_a_stop_left_over_from_one_job_cannot_abort_the_next(monkeypatch, tmp_path):
    """The flag is cleared per dispatch. A click that raced the end of a
    job would otherwise make the NEXT upload report a stop before its first
    chunk."""
    api, _window, rows = api_with(tmp_path)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    api.cancel_upload()
    assert api._cancel.is_set()
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert rows.links == {"r1": "vid123"}


def test_a_finished_upload_tells_the_page_the_job_is_over(monkeypatch, tmp_path):
    """Round 3's finding 5. A semantic event, not an instruction: the page
    is what decides that this means dropping the selection."""
    api, _window, _rows = api_with(tmp_path)
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", fake_upload_ok())

    api.start_upload("Fight", "d", False, ["r1"])
    join(api)

    assert fakes.payloads(sent, "onUploadDone") == [{}]


def test_a_stopped_job_never_claims_completion(monkeypatch, tmp_path):
    """The other half of finding 5, and the reason the panel clears its
    selection on onUploadDone alone: a stopped batch leaves some files up
    and some not, and dropping the selection there would hide which is
    which at exactly the moment the distinction matters."""
    api, _window, _rows = api_with(tmp_path, ids=("r1", "r2", "r3"))
    sent = fakes.record_pushes(api)
    fakes.stub_auth(monkeypatch)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", cancelling_upload(api, 1))

    api.start_upload("Fight", "d", False, ["r1", "r2", "r3"])
    join(api)

    assert fakes.payloads(sent, "onUploadDone") == []
    assert fakes.payloads(sent, "onStatus")[-1]["text"] == "Stopped. 1 of 3 uploaded."
