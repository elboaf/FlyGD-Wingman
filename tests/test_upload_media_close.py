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
    widget = types.SimpleNamespace(config=lambda *a, **k: None)
    return types.SimpleNamespace(
        _ui=lambda fn, *args: None,
        progress=widget,
        status=widget,
        _status_kind="FG",
    )


def _fake_youtube():
    insert = lambda **kwargs: object()
    return types.SimpleNamespace(videos=lambda: types.SimpleNamespace(insert=insert))


def _job():
    return app_mod.UploadJob(items=[], title="t", description="d",
                             stitch=True, privacy="unlisted", category="20")


def _call(monkeypatch, upload_impl, **kwargs):
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
