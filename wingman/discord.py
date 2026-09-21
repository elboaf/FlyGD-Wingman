"""Discord webhook posting.

A webhook URL is a bearer credential: anyone holding it can post to that
channel indefinitely. Unlike the OAuth token it does not expire, cannot be
scoped, and has no revocation UI short of deleting the webhook server-side.
Nothing here may ever surface one in full.
"""

import contextlib
import json
import logging
import mimetypes
import re
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from . import __version__ as _version

# The only hosts Discord serves webhooks from. Deliberately not a suffix
# match: "discord.com.evil.example" must not pass.
_ALLOWED_HOSTS = frozenset(
    {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
)

# Real Discord webhook tokens are long, high-entropy strings (well over 60
# characters). A malformed-but-parseable URL could in principle carry a
# short or common token (e.g. a single letter); blindly replacing every
# occurrence of that substring anywhere in a log line would corrupt unrelated
# text instead of redacting a secret. Below this length we skip the bare
# token pass entirely; the full URL is still always redacted verbatim.
_MIN_REDACTABLE_TOKEN_LEN = 8

# Placeholder used while redacting so that a token which happens to be a
# substring of the webhook id can never corrupt the id text that describe()
# inserts. The URL is replaced with this sentinel first, the bare token is
# then redacted from what remains of the original text, and only afterwards
# is the sentinel swapped for the human-readable describe() string.
_SENTINEL = "\x00__discord_webhook__\x00"


@dataclass(frozen=True)
class Webhook:
    url: str
    webhook_id: str
    token: str
    host: str = "discord.com"


def parse_webhook(raw: str | None) -> tuple[Webhook | None, str]:
    """Validate a webhook URL. Returns (webhook, error); error is "" on success."""
    if raw is None or not raw.strip():
        return None, "Enter a Discord webhook URL."
    candidate = raw.strip()
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None, "That is not a valid URL."
    if parsed.scheme != "https":
        return None, "Webhook URL must use https."
    if parsed.hostname is None or parsed.hostname.lower() not in _ALLOWED_HOSTS:
        return None, "That is not a Discord webhook host."
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 4 or parts[0] != "api" or parts[1] != "webhooks":
        return None, (
            "That does not look like a Discord webhook URL "
            "(expected .../api/webhooks/{id}/{token})."
        )
    host = parsed.hostname.lower()
    return Webhook(url=candidate, webhook_id=parts[2], token=parts[3], host=host), ""


def describe(webhook: Webhook | None) -> str:
    """A name for a webhook that omits its token, safe to display anywhere."""
    if webhook is None:
        return "(not configured)"
    return f"{webhook.host}/api/webhooks/{webhook.webhook_id}…"


def redact(text: str, webhook: Webhook | None) -> str:
    """Replace a webhook URL and its bare token with a safe description.

    Order matters: the full URL is redacted first (as a sentinel, not the
    final describe() text, so a token that is a substring of the webhook id
    cannot later corrupt the id once it's been inserted). The bare token is
    then stripped from whatever text remains, and only at the end is the
    sentinel swapped in for the human-readable description.
    """
    if webhook is None or not isinstance(text, str) or not text:
        return text
    out = text.replace(webhook.url, _SENTINEL)
    if webhook.token and len(webhook.token) >= _MIN_REDACTABLE_TOKEN_LEN:
        out = out.replace(webhook.token, "…")
    return out.replace(_SENTINEL, describe(webhook))


class RedactingFilter(logging.Filter):
    """Redacts the configured webhook from every record, whatever emitted it.

    Installed on the root handler rather than applied at call sites: the app
    attaches its handler to the root logger, so every library logger inherits
    it, and an HTTP transport logging its request URL at DEBUG would write the
    token to disk without passing through any of our code. Call-site
    redaction cannot make that guarantee; this can.

    Covers the rendered message (record.msg/args), plus record.exc_text and
    record.stack_info -- a Formatter appends both of those independently of
    getMessage(), so logger.exception(...) or stack_info=True can otherwise
    write an unredacted token even when the message itself is clean.

    Takes a callable rather than a Webhook so it picks up a webhook the user
    configures after logging is already running.
    """

    def __init__(self, get_webhook):
        super().__init__()
        self._get_webhook = get_webhook

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            webhook = self._get_webhook()
        except Exception:  # noqa: BLE001 - a filter must never raise, or every log call breaks
            return True
        if webhook is None:
            return True
        # Render once, then redact: the token may arrive via args rather than
        # in the format string.
        try:
            rendered = record.getMessage()
        except Exception:  # noqa: BLE001 - a filter must never raise, or every log call breaks
            return True
        cleaned = redact(rendered, webhook)
        if cleaned != rendered:
            record.msg = cleaned
            record.args = ()
        # logger.exception(...)/exc_info=True embeds the traceback text
        # separately from getMessage() -- a Formatter appends record.exc_text
        # (deriving it from record.exc_info the first time it's needed) after
        # the rendered message. Rewriting record.msg alone leaves that text,
        # which can carry the webhook URL (e.g. "bad response from <url>"),
        # completely unredacted on disk. Pre-compute and redact it here so
        # the Formatter finds it already set and never re-derives it.
        if record.exc_info:
            try:
                if not record.exc_text:
                    record.exc_text = "".join(
                        traceback.format_exception(*record.exc_info)
                    )
                record.exc_text = redact(record.exc_text, webhook)
            except Exception:  # noqa: BLE001,S110 - a filter must never raise, or every log call breaks
                pass
        # stack_info=True appends record.stack_info the same way; it's
        # already a formatted string by the time a record carries it (built
        # eagerly by Logger._log), so it just needs redacting in place.
        if record.stack_info:
            with contextlib.suppress(Exception):
                record.stack_info = redact(record.stack_info, webhook)
        return True


# Discord's webhook attachment limit on a non-boosted server.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Discord's edge refuses urllib's default "Python-urllib/3.x" user agent with
# a Cloudflare 403 ("error code: 1010") before the request ever reaches the
# webhook. Here that status is indistinguishable from a genuinely deleted
# webhook, so without this header _describe_status reports a perfectly valid
# webhook as "invalid or has been deleted". Discord's API docs ask for a
# descriptive user agent; sending one gets the real webhook response back.
_USER_AGENT = f"FlyGD-Wingman/{_version} (+https://github.com/elboaf/FlyGD-Wingman)"

_TIMEOUT_SECONDS = 60

# Metadata is optional, but Settings Save/Identify/Remove share a serialized
# webhook field queue. This is a whole caller deadline rather than urllib's
# socket timeout: DNS and a slow-but-progressing body can outlive that timeout.
WEBHOOK_IDENTIFY_DEADLINE_S = 5.0


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects on the webhook POST.

    A redirect target is not covered by the host allowlist in
    parse_webhook() -- that check only ever runs once, against the URL the
    user typed in. If Discord's edge (or anything sitting in front of it)
    ever answered with a 3xx, the default urllib behavior would silently
    resend the archive, including whatever private log content it holds, to
    wherever the Location header points. Returning None here tells urllib
    "don't redirect"; the 3xx is then surfaced like any other non-2xx status
    by the ordinary HTTPError path below, and nothing is ever sent past the
    URL the caller supplied.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def safe_webhook_name(webhook: Webhook | None, name: object) -> str:
    """Untrusted metadata must not turn a masked credential into an identity."""
    if webhook is None or not isinstance(name, str) or not 1 <= len(name) <= 80:
        return ""
    if not name.isprintable() or not name.strip():
        return ""
    # Unlike log redaction, even a short token must not become UI copy. Reject
    # echoes rather than displaying a partly redacted credential as a name.
    if webhook.token in name or "://" in name or "api/webhooks/" in name:
        return ""
    return name.strip()


def identify_webhook(webhook: Webhook, *, transport=None) -> str:
    """One no-redirect GET; return only a safe webhook name or "".

    `WebhookLookupLane` owns the end-to-end caller deadline in production.
    This leaf stays synchronous so its complete security boundary — canonical
    URL, no redirects, bounded body, JSON and safe-name validation — runs in
    one retained daemon rather than being split across callback stages.

    The POST parser deliberately accepts legacy URL shapes. Metadata must not
    inherit userinfo, ports, query strings or extra path segments, nor let an
    encoded separator/dot segment redirect a token to a different API path.
    """
    parsed, _ = parse_webhook(webhook.url)
    if (
        parsed is None
        or not re.fullmatch(r"[0-9]{1,20}", parsed.webhook_id)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", parsed.token)
        or urlparse(webhook.url).params
    ):
        return ""
    url = f"https://{parsed.host}/api/webhooks/{parsed.webhook_id}/{parsed.token}"
    request = urllib.request.Request(
        url, headers={"User-agent": _USER_AGENT}, method="GET"
    )
    try:
        with (transport or _default_transport)(request, timeout=5) as response:
            if response.status != 200:
                return ""
            body = response.read(16 * 1024 + 1)
        if len(body) > 16 * 1024:
            return ""
        document = json.loads(body.decode("utf-8"))
        if not isinstance(document, dict) or document.get("id") != parsed.webhook_id:
            return ""
        return safe_webhook_name(parsed, document.get("name"))
    except urllib.error.HTTPError as error:
        # HTTPError owns a response too; never read its potentially echoed body.
        error.close()
        return ""
    except Exception:  # noqa: BLE001 - external metadata failures are optional; never echo transport errors or bodies
        return ""


class WebhookLookupLane:
    """One retained optional-metadata owner, never a growing timeout pool.

    DNS cannot be force-cancelled safely. A caller therefore waits only until
    `deadline_s`, while the one daemon that entered the transport remains the
    lane owner until it exits. Busy and closed callers fail locally; no worker
    completion publishes or persists anything, so an overdue result has no
    authority outside its original synchronous caller.
    """

    def __init__(
        self,
        lookup=identify_webhook,
        *,
        deadline_s: float = WEBHOOK_IDENTIFY_DEADLINE_S,
        clock=time.monotonic,
        thread_factory=threading.Thread,
    ):
        self._lookup = lookup
        self._deadline_s = max(0.0, deadline_s)
        self._clock = clock
        self._thread_factory = thread_factory
        self._lock = threading.Lock()
        self._closed = False
        self._owner = None
        self._done = None

    def identify(self, webhook: Webhook) -> str:
        """Return a safe name by the deadline, or "" without replacing owner."""
        deadline = self._clock() + self._deadline_s
        with self._lock:
            if self._closed or self._owner is not None:
                return ""
            done = threading.Event()
            self._done = done
            result = [""]

            def run():
                try:
                    value = self._lookup(webhook)
                except Exception:  # noqa: BLE001 - optional metadata never reports transport failures
                    value = ""
                try:
                    if isinstance(value, str):
                        result[0] = value
                finally:
                    with self._lock:
                        self._owner = None
                        done.set()

            try:
                owner = self._thread_factory(
                    target=run, name="discord-webhook-lookup", daemon=True
                )
                self._owner = owner
                owner.start()
            except Exception:  # noqa: BLE001 - no owner means the optional lookup is unavailable
                self._owner = None
                done.set()
                return ""
        if not done.wait(max(0.0, deadline - self._clock())):
            return ""
        with self._lock:
            return "" if self._closed else result[0]

    def close(self) -> bool:
        """Close admission without joining an uninterruptible DNS owner."""
        with self._lock:
            self._closed = True
            return self._owner is None

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Testable bounded observation; production shutdown intentionally skips it."""
        with self._lock:
            done = self._done
        return done is None or done.wait(timeout)


@dataclass(frozen=True)
class PostResult:
    ok: bool
    message: str


def _build_multipart(archive_path: Path, content: str) -> tuple[bytes, str]:
    boundary = _uuid.uuid4().hex
    payload = archive_path.read_bytes()
    ctype = mimetypes.guess_type(archive_path.name)[0] or "application/zip"
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="content"\r\n\r\n',
        content.encode("utf-8"),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="files[0]"; filename="{archive_path.name}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        payload,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def post_archive(
    webhook: Webhook, archive_path, content: str, *, transport=_default_transport
) -> PostResult:
    """POST an archive to a Discord webhook.

    Refuses locally when the archive exceeds Discord's limit rather than
    uploading megabytes to be rejected -- the oversized file itself is left
    untouched either way; this function only ever reads it, never deletes or
    moves it. Never raises: every failure comes back as a PostResult with a
    redacted message, and neither the request URL nor a non-2xx response
    body (which could itself echo the token back, e.g. in a proxy's error
    page) is ever read into that message -- only the numeric status is used.
    """
    archive_path = Path(archive_path)
    try:
        size = archive_path.stat().st_size
    except OSError as exc:
        return PostResult(False, f"Could not read the archive: {exc}")

    if size > MAX_ATTACHMENT_BYTES:
        return PostResult(
            False,
            (
                f"The archive is {size / 1024 / 1024:.1f} MB, which is too large for "
                f"Discord ({MAX_ATTACHMENT_BYTES // 1024 // 1024} MB limit)."
            ),
        )

    try:
        # archive_path.read_bytes() inside _build_multipart can raise OSError
        # even after the stat() above succeeded (e.g. permissions revoked, or
        # any other unreadable-but-stat-able state) -- that must land here,
        # not escape past the try, or the caller's "never raises" contract
        # breaks and the recovery message below never gets shown.
        body, content_type = _build_multipart(archive_path, content)
        request = urllib.request.Request(
            webhook.url,
            data=body,
            headers={"Content-type": content_type, "User-agent": _USER_AGENT},
            method="POST",
        )
        with transport(request, timeout=_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        return PostResult(False, redact(_describe_status(exc.code), webhook))
    except OSError as exc:
        return PostResult(False, f"Could not read the archive: {exc}")
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return PostResult(False, redact(f"Could not reach Discord: {exc}", webhook))

    if 200 <= status < 300:
        return PostResult(True, f"Posted {archive_path.name} ({size / 1024:.0f} KB).")
    return PostResult(False, redact(_describe_status(status), webhook))


def _describe_status(status: int) -> str:
    if status in (401, 403, 404):
        return "That webhook is invalid or has been deleted. Check it in Settings."
    if status == 413:
        return "Discord rejected the archive as too large."
    if status == 429:
        return "Discord is rate-limiting uploads. Try again shortly."
    return f"Discord returned an unexpected status ({status})."
