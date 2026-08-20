import socket

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
