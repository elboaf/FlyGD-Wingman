"""YouTube upload: error classification, retrying upload, OAuth.

Errors are classified before they reach the UI so users see plain language
instead of a traceback in a log file nobody reads.
"""
import enum
import json
import socket

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class Outcome(enum.Enum):
    RETRY = "retry"
    QUOTA = "quota"
    AUTH = "auth"
    PERMANENT = "permanent"


_MESSAGES = {
    Outcome.RETRY: "Network problem. Retrying…",
    Outcome.QUOTA: (
        "YouTube's daily upload limit for this app has been reached. "
        "Please try again tomorrow."
    ),
    Outcome.AUTH: (
        "Google refused the sign-in. If this build is a pre-release, your "
        "account may not be on the approved tester list yet."
    ),
    Outcome.PERMANENT: "The upload failed and retrying will not help.",
}


def _status_of(exc: Exception) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _reasons(exc: Exception) -> set[str]:
    content = getattr(exc, "content", None)
    if not content:
        return set()
    if isinstance(content, bytes):
        content = content.decode("utf-8", "replace")
    try:
        payload = json.loads(content)
    except ValueError:
        return set()
    errors = payload.get("error", {}).get("errors", [])
    return {e.get("reason", "") for e in errors if isinstance(e, dict)}


def classify(exc: Exception) -> Outcome:
    status = _status_of(exc)
    if status is None:
        if isinstance(exc, (socket.timeout, ConnectionError, OSError)):
            return Outcome.RETRY
        return Outcome.PERMANENT
    if status in RETRYABLE_STATUS:
        return Outcome.RETRY
    if status == 403 and "quotaExceeded" in _reasons(exc):
        return Outcome.QUOTA
    if status in (401, 403):
        return Outcome.AUTH
    return Outcome.PERMANENT


def message_for(outcome: Outcome) -> str:
    return _MESSAGES[outcome]


import random
import time

BASE_BACKOFF = 1.0
MAX_BACKOFF = 32.0


class UploadFailed(Exception):
    """An upload failed. `outcome` says whether retrying could ever help.

    `request` carries the resumable request object so a manual Retry can
    resume the existing session instead of restarting from zero.
    """

    def __init__(self, outcome: Outcome, original: Exception | None = None,
                 request=None):
        self.outcome = outcome
        self.original = original
        self.request = request
        super().__init__(message_for(outcome))


def build_body(title: str, description: str, privacy: str, category: str,
               index: int, total: int) -> dict:
    title = title or "Untitled"
    if total > 1:
        title = f"{title} ({index + 1}/{total})"
    return {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category,
        },
        "status": {"privacyStatus": privacy},
    }


def upload(request, *, on_progress=None, on_retry=None, max_attempts: int = 5,
           sleep=time.sleep, jitter=random.random) -> str:
    """Drive a resumable upload to completion, retrying transient failures.

    The *same* request object is reused across retries — that is what makes
    this resume rather than restart. Returns the YouTube video ID.

    on_retry(attempt_number, delay_seconds) fires before each backoff sleep
    so the UI can show "retrying" rather than appearing frozen.

    A successful chunk resets the failure count: an upload with one
    transient error every few chunks is still making steady progress, and a
    global attempt budget would otherwise eventually abort a healthy,
    multi-gigabyte upload for no reason connected to its actual health.
    """
    attempts = 0
    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
        except Exception as exc:
            outcome = classify(exc)
            attempts += 1
            if outcome is not Outcome.RETRY or attempts >= max_attempts:
                raise UploadFailed(outcome, exc, request=request) from exc
            delay = min(BASE_BACKOFF * (2 ** (attempts - 1)), MAX_BACKOFF) + jitter()
            if on_retry is not None:
                on_retry(attempts, delay)
            sleep(delay)
            continue
        attempts = 0
        if status is not None and on_progress is not None:
            on_progress(status.progress())

    video_id = response.get("id") if isinstance(response, dict) else None
    if not video_id:
        raise UploadFailed(Outcome.PERMANENT, request=request)
    return video_id
