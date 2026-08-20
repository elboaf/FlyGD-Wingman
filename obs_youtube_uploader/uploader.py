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
