"""YouTube upload: error classification, retrying upload, OAuth.

Errors are classified before they reach the UI so users see plain language
instead of a traceback in a log file nobody reads.
"""
import enum
import json
import os
import random
import socket
import stat as _stat
import time
from pathlib import Path

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
CHUNK_SIZE = 4 * 1024 * 1024  # Consumed by app._upload_one when building MediaFileUpload.


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


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_credentials(token_path: Path):
    """Load stored credentials, or None if absent/unreadable."""
    token_path = Path(token_path)
    if not token_path.exists():
        return None
    from google.oauth2.credentials import Credentials
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception:
        return None


def save_credentials(creds, token_path: Path) -> None:
    """Persist credentials with owner-only permissions.

    The token grants upload access to the user's channel, so it must never
    be readable by other accounts on the machine, even momentarily. Writing
    with the default mode and chmod-ing afterward would leave a window where
    a new file sits at the umask's default (typically world-readable) before
    the restrictive bits are applied. Instead the file is created directly
    with owner-only bits via os.open, so there is no permissive state to
    observe. The chmod afterward is kept as a second pass so a *pre-existing*
    token file (written by an older build, or by another process) still ends
    up locked down even though O_CREAT | O_TRUNC would not have reset an
    existing file's mode bits on its own.
    """
    token_path = Path(token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    finally:
        try:
            os.chmod(token_path, _stat.S_IRUSR | _stat.S_IWUSR)
        except OSError:
            pass  # Best effort; Windows ACLs differ and failure is not fatal.


def needs_reauth(creds) -> bool:
    """True when a full interactive OAuth flow is required.

    While the app is unverified, refresh tokens expire after 7 days, so this
    returns True roughly weekly for every user. The caller must handle it
    smoothly rather than treating it as an error.
    """
    if creds is None:
        return True
    if getattr(creds, "valid", False):
        return False
    return not (getattr(creds, "expired", False) and getattr(creds, "refresh_token", None))


def run_oauth_flow():
    """Interactive consent via the loopback redirect. Returns Credentials."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from .credentials import CLIENT_CONFIG
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    return flow.run_local_server(port=0)


def refresh_credentials(creds):
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return creds
