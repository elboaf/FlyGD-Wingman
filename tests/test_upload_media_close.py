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
not a drop-in replacement for the old free-standing widget double. Built
on tests/fakes.py's build_api/install_google rather than hand-rolled
doubles, since that MediaFileUpload stub is already vetted against the
real call site (chunksize=uploader.CHUNK_SIZE, resumable=True) and its
.stream().close() shape is exactly what _close_media calls.
"""

import types

import pytest

from tests import fakes
from wingman import uploader
from wingman.ui.api import RetryState, UploadJob


def _job(ids=("r1",), stitch=True):
    return UploadJob(
        items=[fakes.info(f"{rid}.mkv") for rid in ids],
        ids=list(ids),
        title="t",
        description="d",
        stitch=stitch,
        privacy="unlisted",
        category="20",
    )


def _upload_one(api, monkeypatch, upload_impl, **kwargs):
    """Drive Api._upload_one directly, with a real (vetted) MediaFileUpload."""
    MediaFileUpload = fakes.install_google(monkeypatch, fakes.FakeYouTube())
    monkeypatch.setattr(uploader, "upload", upload_impl)
    youtube = fakes.FakeYouTube()
    return api._upload_one(
        youtube, MediaFileUpload, "/tmp/stitch-abc.mkv", _job(), 0, 1, **kwargs
    )


def test_stitched_upload_closes_media_on_success(tmp_path, monkeypatch):
    api, _window = fakes.build_api(tmp_path)
    media_holder = {}

    def fake_upload(request, **kw):
        media_holder["media"] = request.media
        return "vid123"

    _upload_one(api, monkeypatch, fake_upload, close_media=True)
    assert media_holder["media"].closed


def test_stitched_upload_closes_media_on_failure(tmp_path, monkeypatch):
    api, _window = fakes.build_api(tmp_path)
    media_holder = {}

    def boom(request, **kw):
        media_holder["media"] = request.media
        raise uploader.UploadFailed(uploader.Outcome.UPLOAD_LIMIT, request=request)

    with pytest.raises(uploader.UploadFailed):
        _upload_one(api, monkeypatch, boom, close_media=True)
    assert media_holder["media"].closed


def test_plain_upload_leaves_media_open_for_resume(tmp_path, monkeypatch):
    api, _window = fakes.build_api(tmp_path)
    media_holder = {}

    def boom(request, **kw):
        media_holder["media"] = request.media
        raise uploader.UploadFailed(uploader.Outcome.RETRY, request=request)

    with pytest.raises(uploader.UploadFailed):
        _upload_one(api, monkeypatch, boom)
    assert not media_holder["media"].closed


def test_stitched_worker_asks_upload_one_to_close_the_media(tmp_path, monkeypatch):
    """The wiring, not the mechanism.

    The tests above drive _upload_one directly and pass close_media
    themselves, so every one of them still passes if the stitch call site
    drops the argument -- and the multi-gigabyte leak comes straight back.
    This is the test that fails when that happens.
    """
    import contextlib

    from wingman import paths, stitch

    recorded = {}

    def fake_upload_one(
        youtube, MediaFileUploadCls, path, job, index, total, close_media=False
    ):
        recorded["close_media"] = close_media
        return "vid123"

    @contextlib.contextmanager
    def fake_stitched(sources, ffmpeg_bin, tmp_dir, **kw):
        yield tmp_path / "merged.mkv"

    fakes.stub_auth(monkeypatch)
    monkeypatch.setattr(uploader, "refresh_credentials", lambda c: c)
    monkeypatch.setattr(paths, "token_file", lambda: tmp_path / "token.json")
    monkeypatch.setattr(paths, "tmp_dir", lambda: tmp_path)
    monkeypatch.setattr(stitch, "order_for_stitch", lambda items: items)
    monkeypatch.setattr(stitch, "stitched", fake_stitched)
    fakes.install_google(monkeypatch, fakes.FakeYouTube())

    api, _window = fakes.build_api(tmp_path)
    api._upload_one = fake_upload_one

    job = _job(ids=("r1",), stitch=True)
    api._upload_worker(job)

    assert recorded.get("close_media") is True, (
        "the stitched call site must ask _upload_one to close the media, or "
        "the merged temp file cannot be unlinked on Windows"
    )


@pytest.mark.parametrize(
    "outcome,retryable",
    [
        (uploader.Outcome.RETRY, True),
        (uploader.Outcome.UPLOAD_LIMIT, False),
        (uploader.Outcome.AUTH, False),
        (uploader.Outcome.PERMANENT, False),
    ],
)
def test_retry_availability_after_a_failed_retry_matches_the_outcome(
    tmp_path, monkeypatch, outcome, retryable
):
    """A retry that fails again must re-enable Retry only when retrying can
    still help. Re-enabling it for a channel limit invites the user into a
    loop of instant 'wait a day' dialogs.

    retry() disables the button before starting the worker; this drives
    _retry_worker directly, so the only "re-enable" signal possible is the
    onRetryAvailable push the worker itself makes on a RETRY outcome."""

    def boom(request, **kw):
        raise uploader.UploadFailed(outcome, request=request)

    monkeypatch.setattr(uploader, "upload", boom)
    rows = fakes.FakeRows({"r1": fakes.info(tmp_path / "a.mkv")})
    api, _window = fakes.build_api(tmp_path, rows=rows)
    sent = fakes.record_pushes(api)
    job = _job(ids=("r1",), stitch=False)
    state = RetryState(job=job, resume_index=0, request=object())

    api._retry_worker(state)

    available = [p for p in fakes.payloads(sent, "onRetryAvailable") if p["available"]]
    assert bool(available) is retryable


def _resumable_request(monkeypatch):
    """A request double shaped like googleapiclient's HttpRequest, whose
    `.resumable` is the MediaUpload that owns the open file handle."""
    MediaFileUpload = fakes.install_google(monkeypatch, fakes.FakeYouTube())
    media = MediaFileUpload("/tmp/a.mkv", chunksize=uploader.CHUNK_SIZE, resumable=True)
    return types.SimpleNamespace(resumable=media), media


def _run_retry(tmp_path, monkeypatch, outcome):
    request, media = _resumable_request(monkeypatch)

    def boom(req, **kw):
        raise uploader.UploadFailed(outcome, request=req)

    monkeypatch.setattr(uploader, "upload", boom)
    rows = fakes.FakeRows({"r1": fakes.info(tmp_path / "a.mkv")})
    api, _window = fakes.build_api(tmp_path, rows=rows)
    job = _job(ids=("r1",), stitch=False)
    state = RetryState(job=job, resume_index=0, request=request)
    api._retry_worker(state)
    return api, media


def test_terminal_retry_failure_releases_the_recording(tmp_path, monkeypatch):
    """A manual retry that fails for good must not keep the user's own
    recording open. The request is unreachable once Retry is disabled, so
    holding it only blocks renaming or deleting that file on Windows."""
    api, media = _run_retry(tmp_path, monkeypatch, uploader.Outcome.UPLOAD_LIMIT)
    assert media.closed
    assert api._retry_state.request is None


def test_retryable_retry_failure_keeps_the_stream_for_the_next_resume(
    tmp_path, monkeypatch
):
    api, media = _run_retry(tmp_path, monkeypatch, uploader.Outcome.RETRY)
    assert not media.closed
    assert api._retry_state.request is not None
