import os
import socket
import stat
import sys

import pytest
from obs_youtube_uploader import uploader


class FakeResp:
    def __init__(self, status): self.status = status
    def __getitem__(self, k): return self.status if k == "status" else None


class FakeHttpError(Exception):
    """Stands in for googleapiclient.errors.HttpError."""
    def __init__(self, status, content=b""):
        self.resp = FakeResp(status)
        self.status_code = status
        self.content = content
        super().__init__(f"HTTP {status}")


@pytest.mark.parametrize("status", [500, 502, 503, 504, 408, 429])
def test_transient_http_errors_retry(status):
    assert uploader.classify(FakeHttpError(status)) is uploader.Outcome.RETRY


@pytest.mark.parametrize("exc", [
    socket.timeout("slow"),
    ConnectionResetError("reset"),
    OSError("network down"),
])
def test_network_errors_retry(exc):
    assert uploader.classify(exc) is uploader.Outcome.RETRY


def test_quota_exceeded_is_its_own_outcome():
    err = FakeHttpError(403, b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
    assert uploader.classify(err) is uploader.Outcome.QUOTA


def test_access_denied_is_an_auth_outcome():
    err = FakeHttpError(403, b'{"error":{"errors":[{"reason":"accessNotConfigured"}]}}')
    assert uploader.classify(err) is uploader.Outcome.AUTH


def test_plain_403_without_reason_is_auth():
    assert uploader.classify(FakeHttpError(403)) is uploader.Outcome.AUTH


def test_401_is_auth():
    assert uploader.classify(FakeHttpError(401)) is uploader.Outcome.AUTH


@pytest.mark.parametrize("status", [400, 404, 413])
def test_other_client_errors_are_permanent(status):
    assert uploader.classify(FakeHttpError(status)) is uploader.Outcome.PERMANENT


def test_unknown_exception_is_permanent():
    assert uploader.classify(ValueError("???")) is uploader.Outcome.PERMANENT


def test_quota_message_is_plain_english():
    msg = uploader.message_for(uploader.Outcome.QUOTA)
    assert "limit" in msg.lower()
    assert "traceback" not in msg.lower()


def test_every_outcome_has_a_message():
    for outcome in uploader.Outcome:
        assert uploader.message_for(outcome)


class FakeRequest:
    """Stands in for a googleapiclient resumable insert request.

    `script` is a list of either ('progress', fraction), ('fail', exc), or
    ('done', response_dict) applied on successive next_chunk() calls.
    """
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        kind, value = self.script.pop(0)
        if kind == "fail":
            raise value
        if kind == "progress":
            return FakeStatus(value), None
        return None, value


class FakeStatus:
    def __init__(self, fraction): self._f = fraction
    def progress(self): return self._f


def test_upload_returns_video_id_on_clean_run():
    req = FakeRequest([("progress", 0.5), ("done", {"id": "abc123"})])
    assert uploader.upload(req, sleep=lambda s: None) == "abc123"


def test_upload_resumes_after_transient_failure():
    req = FakeRequest([
        ("progress", 0.3),
        ("fail", FakeHttpError(503)),
        ("progress", 0.7),
        ("done", {"id": "xyz789"}),
    ])
    assert uploader.upload(req, sleep=lambda s: None) == "xyz789"


def test_video_id_survives_mid_upload_failure():
    """Regression guard: the link column breaks if retry loses the ID."""
    req = FakeRequest([
        ("fail", ConnectionResetError("reset")),
        ("done", {"id": "survived"}),
    ])
    assert uploader.upload(req, sleep=lambda s: None) == "survived"


def test_upload_does_not_restart_from_zero():
    """next_chunk is called once more than the number of failures, never reset."""
    req = FakeRequest([
        ("progress", 0.5),
        ("fail", FakeHttpError(500)),
        ("done", {"id": "a"}),
    ])
    uploader.upload(req, sleep=lambda s: None)
    assert req.calls == 3


def test_upload_stops_after_max_attempts():
    req = FakeRequest([("fail", FakeHttpError(503))] * 10)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, max_attempts=3, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.RETRY
    assert req.calls == 3


def test_upload_does_not_retry_permanent_errors():
    req = FakeRequest([("fail", FakeHttpError(400))] * 5)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.PERMANENT
    assert req.calls == 1


def test_upload_does_not_retry_quota_errors():
    err = FakeHttpError(403, b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
    req = FakeRequest([("fail", err)] * 5)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.QUOTA
    assert req.calls == 1


def test_backoff_grows_between_attempts():
    slept = []
    req = FakeRequest([
        ("fail", FakeHttpError(503)),
        ("fail", FakeHttpError(503)),
        ("done", {"id": "a"}),
    ])
    uploader.upload(req, sleep=slept.append, jitter=lambda: 0.0)
    assert len(slept) == 2
    assert slept[1] > slept[0]


def test_progress_callback_receives_fractions():
    seen = []
    req = FakeRequest([("progress", 0.25), ("progress", 0.75), ("done", {"id": "a"})])
    uploader.upload(req, on_progress=seen.append, sleep=lambda s: None)
    assert seen == [0.25, 0.75]


def test_retry_callback_reports_each_attempt():
    """A stalled upload must look like it is retrying, not frozen."""
    attempts = []
    req = FakeRequest([
        ("fail", FakeHttpError(503)),
        ("fail", FakeHttpError(503)),
        ("done", {"id": "a"}),
    ])
    uploader.upload(req, on_retry=lambda n, d: attempts.append(n), sleep=lambda s: None)
    assert attempts == [1, 2]


def test_failed_upload_exposes_request_for_manual_retry():
    """The request holds the resumable session; discarding it would make a
    Retry button restart from zero."""
    req = FakeRequest([("fail", FakeHttpError(503))] * 4)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, max_attempts=2, sleep=lambda s: None)
    assert excinfo.value.request is req
    assert req.calls == 2


def test_missing_id_in_response_is_a_permanent_failure():
    req = FakeRequest([("done", {"no_id_here": True})])
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.PERMANENT


def test_upload_raises_auth_outcome_without_retrying():
    """AUTH is not in RETRYABLE_STATUS, so upload() must fail on the first
    attempt rather than burning through the retry budget."""
    req = FakeRequest([("fail", FakeHttpError(401))] * 3)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.AUTH
    assert req.calls == 1


def test_upload_with_max_attempts_one_fails_on_first_transient_error():
    req = FakeRequest([("fail", FakeHttpError(503)), ("done", {"id": "x"})])
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, max_attempts=1, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.RETRY
    assert req.calls == 1


def test_attempt_counter_resets_after_successful_chunk():
    """A transient failure every few chunks should not exhaust the retry
    budget as long as progress keeps being made. Punishing steady, recovering
    progress with a global failure counter would abort multi-gigabyte
    uploads that are, in practice, healthy."""
    script = []
    for _ in range(5):
        script.append(("fail", FakeHttpError(503)))
        script.append(("progress", 0.1))
    script.append(("done", {"id": "resilient"}))
    req = FakeRequest(script)
    assert uploader.upload(req, max_attempts=2, sleep=lambda s: None) == "resilient"


def test_build_body_omits_suffix_for_single_upload():
    body = uploader.build_body("Fight", "desc", "private", "20", index=0, total=1)
    assert body["snippet"]["title"] == "Fight"
    assert body["status"]["privacyStatus"] == "private"
    assert body["snippet"]["categoryId"] == "20"


def test_build_body_adds_suffix_for_multi_upload():
    body = uploader.build_body("Fight", "d", "private", "20", index=1, total=3)
    assert body["snippet"]["title"] == "Fight (2/3)"


def test_build_body_falls_back_to_untitled():
    body = uploader.build_body("", "d", "private", "20", index=0, total=1)
    assert body["snippet"]["title"] == "Untitled"


from obs_youtube_uploader import credentials


def test_is_placeholder_true_for_the_source_tree_value():
    assert credentials.is_placeholder() is True


def test_is_placeholder_false_once_the_release_workflow_has_substituted_it(monkeypatch):
    """Simulates what the release workflow's file-wide string replace does:
    swap the client_id for a realistic value while leaving is_placeholder's
    own sentinel construction untouched (it must be, since the replace
    can't match a value assembled from fragments — see credentials.py)."""
    monkeypatch.setitem(
        credentials.CLIENT_CONFIG["installed"], "client_id",
        "123456789-abcdefg.apps.googleusercontent.com",
    )
    assert credentials.is_placeholder() is False


def test_client_config_has_installed_app_shape():
    cfg = credentials.CLIENT_CONFIG
    assert "installed" in cfg
    for key in ("client_id", "client_secret", "auth_uri", "token_uri"):
        assert key in cfg["installed"]


def test_scopes_are_upload_only():
    assert uploader.SCOPES == ["https://www.googleapis.com/auth/youtube.upload"]


def test_load_credentials_returns_none_when_token_missing(tmp_path):
    assert uploader.load_credentials(tmp_path / "nope.json") is None


def test_load_credentials_returns_none_on_corrupt_token(tmp_path):
    p = tmp_path / "token.json"
    p.write_text("not json")
    assert uploader.load_credentials(p) is None


def test_needs_reauth_for_none():
    assert uploader.needs_reauth(None) is True


def test_needs_reauth_false_for_valid_creds():
    class Creds:
        valid = True
        expired = False
        refresh_token = "r"
    assert uploader.needs_reauth(Creds()) is False


def test_needs_reauth_true_when_expired_without_refresh_token():
    class Creds:
        valid = False
        expired = True
        refresh_token = None
    assert uploader.needs_reauth(Creds()) is True


def test_needs_reauth_false_when_expired_but_refresh_token_present():
    class Creds:
        valid = False
        expired = True
        refresh_token = "r"
    assert uploader.needs_reauth(Creds()) is False


def test_needs_reauth_true_when_invalid_and_not_expired():
    class Creds:
        valid = False
        expired = False
        refresh_token = "r"
    assert uploader.needs_reauth(Creds()) is True


def test_save_credentials_writes_and_restricts(tmp_path):
    class Creds:
        def to_json(self): return '{"token": "x"}'
    p = tmp_path / "token.json"
    uploader.save_credentials(Creds(), p)
    assert p.exists()
    assert "token" in p.read_text()


def test_save_credentials_restricts_permissions(tmp_path):
    class Creds:
        def to_json(self): return '{"token": "x"}'
    p = tmp_path / "token.json"
    uploader.save_credentials(Creds(), p)
    if sys.platform != "win32":
        mode = stat.S_IMODE(os.stat(p).st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
