"""_upload_one must release the stitched temp file's handle.

A stitched upload writes a multi-gigabyte temporary that
stitch.stitched() deletes as soon as the upload returns. MediaFileUpload
closes its descriptor only in __del__, so on Windows the unlink hit
WinError 32 ("used by another process") and the temporary survived until
the next startup sweep. Observed in the field on two consecutive failed
uploads.

The non-stitched path must NOT close: UploadFailed carries the resumable
request so a manual Retry can resume the session, and resuming reads from
this same stream.
"""
import contextlib
import types

import pytest

from obs_youtube_uploader import app as app_mod, uploader


class FakeStream:
    def __init__(self): self.closed = False
    def close(self): self.closed = True


class FakeMediaFileUpload:
    last = None

    def __init__(self, path, chunksize=None, resumable=False):
        self.path = path
        self._stream = FakeStream()
        FakeMediaFileUpload.last = self

    def stream(self): return self._stream


def _fake_window():
    """Enough of UploaderWindow for _upload_one, without a display."""
    widget = types.SimpleNamespace(config=lambda *a, **k: None,
                                   start=lambda *a: None,
                                   stop=lambda *a: None,
                                   state=lambda *a: None)
    return types.SimpleNamespace(
        _ui=lambda fn, *args: None,
        progress=widget,
        status=widget,
        _status_kind="FG",
    )


def _fake_youtube():
    def insert(**_kwargs):
        return object()

    return types.SimpleNamespace(videos=lambda: types.SimpleNamespace(insert=insert))


def _job():
    return app_mod.UploadJob(items=[], title="t", description="d",
                             stitch=True, privacy="unlisted", category="20")


def _call(monkeypatch, upload_impl, **kwargs):
    FakeMediaFileUpload.last = None  # Never assert against a prior test's object.
    monkeypatch.setattr(uploader, "upload", upload_impl)
    return app_mod.UploaderWindow._upload_one(
        _fake_window(), _fake_youtube(), FakeMediaFileUpload,
        "/tmp/stitch-abc.mkv", _job(), 0, 1, **kwargs)


def test_stitched_upload_closes_media_on_success(monkeypatch):
    _call(monkeypatch, lambda request, **kw: "vid123", close_media=True)
    assert FakeMediaFileUpload.last.stream().closed


def test_stitched_upload_closes_media_on_failure(monkeypatch):
    def boom(request, **kw):
        raise uploader.UploadFailed(uploader.Outcome.UPLOAD_LIMIT, request=request)

    with pytest.raises(uploader.UploadFailed):
        _call(monkeypatch, boom, close_media=True)
    assert FakeMediaFileUpload.last.stream().closed


def test_plain_upload_leaves_media_open_for_resume(monkeypatch):
    def boom(request, **kw):
        raise uploader.UploadFailed(uploader.Outcome.RETRY, request=request)

    with pytest.raises(uploader.UploadFailed):
        _call(monkeypatch, boom)
    assert not FakeMediaFileUpload.last.stream().closed


def test_stitched_worker_asks_upload_one_to_close_the_media(monkeypatch, tmp_path):
    """The wiring, not the mechanism.

    The tests above drive _upload_one directly and pass close_media
    themselves, so every one of them still passes if the stitch call site
    drops the argument -- and the multi-gigabyte leak comes straight back.
    This is the test that fails when that happens.
    """
    from obs_youtube_uploader import paths, stitch

    recorded = {}

    def fake_upload_one(youtube, MediaFileUploadCls, path, job, index, total,
                        close_media=False):
        recorded["close_media"] = close_media
        return "vid123"

    @contextlib.contextmanager
    def fake_stitched(sources, ffmpeg_bin, tmp_dir, **kw):
        yield tmp_path / "merged.mkv"

    monkeypatch.setattr(uploader, "load_credentials",
                        lambda p: types.SimpleNamespace(valid=True))
    monkeypatch.setattr(uploader, "needs_reauth", lambda c: False)
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)
    monkeypatch.setattr(uploader, "refresh_credentials", lambda c: c)
    monkeypatch.setattr(paths, "token_file", lambda: tmp_path / "token.json")
    monkeypatch.setattr(paths, "tmp_dir", lambda: tmp_path)
    monkeypatch.setattr(stitch, "order_for_stitch", lambda items: items)
    monkeypatch.setattr(stitch, "stitched", fake_stitched)

    import googleapiclient.discovery
    import googleapiclient.http
    monkeypatch.setattr(googleapiclient.discovery, "build",
                        lambda *a, **k: _fake_youtube())
    monkeypatch.setattr(googleapiclient.http, "MediaFileUpload", FakeMediaFileUpload)

    window = _fake_window()
    window._upload_one = fake_upload_one
    window._set_link = lambda *a: None
    window.retry_btn = types.SimpleNamespace(state=lambda *a: None)
    window.retry_state = None
    window.state = types.SimpleNamespace(ffmpeg_bin="/usr/bin/ffmpeg")

    job = app_mod.UploadJob(items=[], title="t", description="d", stitch=True,
                            privacy="unlisted", category="20")
    app_mod.UploaderWindow._upload_worker(window, job)

    assert recorded.get("close_media") is True, (
        "the stitched call site must ask _upload_one to close the media, or "
        "the merged temp file cannot be unlinked on Windows")


def _retry_window():
    window = _fake_window()
    # _ui must actually invoke here: this test observes what the worker
    # asks the widget to do, and the no-op stub above would make every
    # assertion pass without the code running at all.
    window._ui = lambda fn, *args: fn(*args)
    window._set_link = lambda *a: None
    window.retry_btn = types.SimpleNamespace(
        state=lambda spec: window.button_states.append(list(spec)))
    window.button_states = []
    window.retry_state = None
    return window


@pytest.mark.parametrize("outcome,enabled", [
    (uploader.Outcome.RETRY, True),
    (uploader.Outcome.UPLOAD_LIMIT, False),
    (uploader.Outcome.AUTH, False),
    (uploader.Outcome.PERMANENT, False),
])
def test_retry_button_after_a_failed_retry_matches_the_outcome(
        monkeypatch, tmp_path, outcome, enabled):
    """A retry that fails again must re-enable Retry only when retrying can
    still help. Re-enabling it for a channel limit invites the user into a
    loop of instant 'wait a day' dialogs."""
    def boom(request, **kw):
        raise uploader.UploadFailed(outcome, request=request)

    monkeypatch.setattr(uploader, "upload", boom)
    window = _retry_window()
    info = types.SimpleNamespace(path=tmp_path / "a.mkv")
    job = app_mod.UploadJob(items=[info], title="t", description="d",
                            stitch=False, privacy="unlisted", category="20")
    state = app_mod.RetryState(job=job, resume_index=0, request=object())

    app_mod.UploaderWindow._retry_worker(window, state)

    assert (["!disabled"] in window.button_states) is enabled


def _resumable_request():
    """A request double shaped like googleapiclient's HttpRequest, whose
    `.resumable` is the MediaUpload that owns the open file handle."""
    media = FakeMediaFileUpload("/tmp/a.mkv")
    return types.SimpleNamespace(resumable=media), media


def _run_retry(monkeypatch, tmp_path, outcome):
    request, media = _resumable_request()

    def boom(req, **kw):
        raise uploader.UploadFailed(outcome, request=req)

    monkeypatch.setattr(uploader, "upload", boom)
    window = _retry_window()
    info = types.SimpleNamespace(path=tmp_path / "a.mkv")
    job = app_mod.UploadJob(items=[info], title="t", description="d",
                            stitch=False, privacy="unlisted", category="20")
    state = app_mod.RetryState(job=job, resume_index=0, request=request)
    app_mod.UploaderWindow._retry_worker(window, state)
    return window, media


def test_terminal_retry_failure_releases_the_recording(monkeypatch, tmp_path):
    """A manual retry that fails for good must not keep the user's own
    recording open. The request is unreachable once Retry is disabled, so
    holding it only blocks renaming or deleting that file on Windows."""
    window, media = _run_retry(monkeypatch, tmp_path, uploader.Outcome.UPLOAD_LIMIT)
    assert media.stream().closed
    assert window.retry_state.request is None


def test_retryable_retry_failure_keeps_the_stream_for_the_next_resume(
        monkeypatch, tmp_path):
    window, media = _run_retry(monkeypatch, tmp_path, uploader.Outcome.RETRY)
    assert not media.stream().closed
    assert window.retry_state.request is not None
