"""Media-handle lifecycle around an upload, and the retry state it leaves behind.

A stitched upload writes a multi-gigabyte temporary that stitch.stitched()
deletes as soon as the upload returns. MediaFileUpload closes its
descriptor only in __del__, so on Windows the unlink hit WinError 32 ("used
by another process") and the temporary survived until the next startup
sweep. Observed in the field on two consecutive failed uploads.

The non-stitched path must NOT close: UploadFailed carries the resumable
request so a manual Retry can resume the session, and resuming reads from
this same stream.

These tests exercise ui.api.Api directly (the webview bridge that carries
this logic now), not the Tk UploaderWindow -- Api._upload_one,
_upload_worker and _retry_worker are bound methods with their own
collaborators (self._push, self._state, self._retry_state, self._links),
not a drop-in replacement for the old free-standing widget double.
"""
import contextlib
import types
from pathlib import Path

import pytest

from obs_youtube_uploader import uploader
from obs_youtube_uploader.ui.api import Api, AppState, RetryState, UploadJob


class FakeWindow:
    """Enough of ui.window's webview.Window for the bridge's pushes to land
    somewhere instead of raising -- Api._push swallows exceptions, but a
    silent no-op window would let a broken push go unnoticed."""

    def __init__(self):
        self.evaluated: list[str] = []

    def evaluate_js(self, script: str):
        self.evaluated.append(script)


def make_api(**settings_overrides) -> Api:
    settings = {"privacy": "unlisted", "category": "20", "notify_mode": "toast"}
    settings.update(settings_overrides)
    state = AppState(recording_dir=None, settings=settings,
                     ffmpeg_bin="/usr/bin/ffmpeg", ffprobe_bin=None)
    api = Api(state)
    api._window = FakeWindow()
    return api


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


def _fake_youtube():
    def insert(**_kwargs):
        return object()

    return types.SimpleNamespace(videos=lambda: types.SimpleNamespace(insert=insert))


def _job(items=(), ids=(), stitch=True):
    return UploadJob(items=list(items), ids=list(ids), title="t", description="d",
                     stitch=stitch, privacy="unlisted", category="20")


def _call(monkeypatch, api, upload_impl, **kwargs):
    FakeMediaFileUpload.last = None  # Never assert against a prior test's object.
    monkeypatch.setattr(uploader, "upload", upload_impl)
    return api._upload_one(_fake_youtube(), FakeMediaFileUpload,
                           "/tmp/stitch-abc.mkv", _job(), 0, 1, **kwargs)


def test_stitched_upload_closes_media_on_success(monkeypatch):
    api = make_api()
    _call(monkeypatch, api, lambda request, **kw: "vid123", close_media=True)
    assert FakeMediaFileUpload.last.stream().closed


def test_stitched_upload_closes_media_on_failure(monkeypatch):
    api = make_api()

    def boom(request, **kw):
        raise uploader.UploadFailed(uploader.Outcome.UPLOAD_LIMIT, request=request)

    with pytest.raises(uploader.UploadFailed):
        _call(monkeypatch, api, boom, close_media=True)
    assert FakeMediaFileUpload.last.stream().closed


def test_plain_upload_leaves_media_open_for_resume(monkeypatch):
    api = make_api()

    def boom(request, **kw):
        raise uploader.UploadFailed(uploader.Outcome.RETRY, request=request)

    with pytest.raises(uploader.UploadFailed):
        _call(monkeypatch, api, boom)
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

    api = make_api()
    api._upload_one = fake_upload_one

    job = _job(items=[], ids=[], stitch=True)
    api._upload_worker(job)

    assert recorded.get("close_media") is True, (
        "the stitched call site must ask _upload_one to close the media, or "
        "the merged temp file cannot be unlinked on Windows")


def _pushed(api: Api, handler: str) -> list:
    """Payloads pushed under *handler*, decoded back out of evaluate_js calls."""
    import json
    out = []
    for script in api._window.evaluated:
        name = script.split("window.", 1)[1].split(" ", 1)[0]
        if name != handler:
            continue
        payload = json.loads(script[script.index("(", script.rindex(name)) + 1:
                                    script.rindex(")")])
        out.append(payload)
    return out


@pytest.mark.parametrize("outcome,retryable", [
    (uploader.Outcome.RETRY, True),
    (uploader.Outcome.UPLOAD_LIMIT, False),
    (uploader.Outcome.AUTH, False),
    (uploader.Outcome.PERMANENT, False),
])
def test_retry_availability_after_a_failed_retry_matches_the_outcome(
        monkeypatch, tmp_path, outcome, retryable):
    """A retry that fails again must re-enable Retry only when retrying can
    still help. Re-enabling it for a channel limit invites the user into a
    loop of instant 'wait a day' dialogs.

    retry() disables the button before starting the worker; this drives
    _retry_worker directly, so the only "re-enable" signal possible is the
    onRetryAvailable push the worker itself makes on a RETRY outcome."""
    def boom(request, **kw):
        raise uploader.UploadFailed(outcome, request=request)

    monkeypatch.setattr(uploader, "upload", boom)
    api = make_api()
    info = types.SimpleNamespace(path=tmp_path / "a.mkv")
    job = _job(items=[info], ids=["r1"], stitch=False)
    state = RetryState(job=job, resume_index=0, request=object())

    api._retry_worker(state)

    available_pushes = [p for p in _pushed(api, "onRetryAvailable") if p["available"]]
    assert bool(available_pushes) is retryable


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
    api = make_api()
    info = types.SimpleNamespace(path=tmp_path / "a.mkv")
    job = _job(items=[info], ids=["r1"], stitch=False)
    state = RetryState(job=job, resume_index=0, request=request)
    api._retry_worker(state)
    return api, media


def test_terminal_retry_failure_releases_the_recording(monkeypatch, tmp_path):
    """A manual retry that fails for good must not keep the user's own
    recording open. The request is unreachable once Retry is disabled, so
    holding it only blocks renaming or deleting that file on Windows."""
    api, media = _run_retry(monkeypatch, tmp_path, uploader.Outcome.UPLOAD_LIMIT)
    assert media.stream().closed
    assert api._retry_state.request is None


def test_retryable_retry_failure_keeps_the_stream_for_the_next_resume(
        monkeypatch, tmp_path):
    api, media = _run_retry(monkeypatch, tmp_path, uploader.Outcome.RETRY)
    assert not media.stream().closed
    assert api._retry_state.request is not None
