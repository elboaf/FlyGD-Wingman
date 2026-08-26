"""classify() against real googleapiclient.errors.HttpError objects.

test_uploader.py validates classify() against a local FakeHttpError double
that was hand-written to match the implementation's own attribute reads
(resp.status, status_code, content). That is a real gap: the double could
silently drift out of sync with what googleapiclient actually raises, and
the tests would keep passing. This file re-validates the same behavior
against the real exception type.

Guarded with importorskip so the suite still runs in environments without
the Google client libraries installed; uploader.py itself must keep
importing only stdlib at module level, so this import stays confined to
the test file.
"""

import pytest

pytest.importorskip("googleapiclient")

import httplib2
from googleapiclient.errors import HttpError

from wingman import uploader


def _http_error(status: int, body: bytes = b"") -> HttpError:
    return HttpError(httplib2.Response({"status": status}), body)


def test_classify_real_http_error_503_is_retry():
    assert uploader.classify(_http_error(503)) is uploader.Outcome.RETRY


def test_classify_real_http_error_403_quota_exceeded_body_is_quota():
    body = b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}'
    assert uploader.classify(_http_error(403, body)) is uploader.Outcome.QUOTA


def test_classify_real_http_error_403_other_reason_is_auth():
    body = b'{"error":{"errors":[{"reason":"accessNotConfigured"}]}}'
    assert uploader.classify(_http_error(403, body)) is uploader.Outcome.AUTH


def test_classify_real_http_error_401_is_auth():
    assert uploader.classify(_http_error(401)) is uploader.Outcome.AUTH


def test_classify_real_http_error_400_is_permanent():
    assert uploader.classify(_http_error(400)) is uploader.Outcome.PERMANENT


def test_classify_real_http_error_400_upload_limit_is_upload_limit():
    body = (
        b'{"error":{"errors":[{"message":"The user has exceeded the '
        b'number of videos they may upload.","domain":"youtube.video",'
        b'"reason":"uploadLimitExceeded"}],"code":400}}'
    )
    assert uploader.classify(_http_error(400, body)) is uploader.Outcome.UPLOAD_LIMIT
