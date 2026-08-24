"""Read-only ESI client: path hardening, bounded retries, ETags.

Transport and sleep are injected with production defaults, the seam
discord.py:196-197,224 establishes, which is what lets the whole retry and
backoff ladder be tested headless with no real sleeps.

Nothing here writes to ESI. The two scopes this application requests are
read-only, and the only POST is the unauthenticated universe/ids lookup.
"""
import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import application

MAX_ATTEMPTS = 3
MAX_ERROR_BODY_BYTES = 8192
MAX_SUCCESS_BODY_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = frozenset({408, 420, 429, 500, 502, 503, 504})
TIMEOUT_S = 20.0

# Server-suggested waits are honoured but capped: a misconfigured or hostile
# Retry-After of 86400 would otherwise hold a refresh worker for a day, and
# the user cannot tell that apart from a crash.
MAX_BACKOFF_S = 30.0
BASE_BACKOFF_S = 0.650
NETWORK_BACKOFF_S = 0.500

# Segments are restricted to this set, which is what makes a query string, a
# fragment, an encoded slash, and a traversal all structurally impossible
# rather than merely filtered. Adding a paging parameter to any ESI call in
# this package therefore requires a deliberate change here first.
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_VERSION_SEGMENT = re.compile(r"^v\d+$")


def validate_path(path: str) -> str:
    """Return *path* unchanged, or raise ValueError.

    Every authenticated request carries an Authorization header, so a path
    that can be steered to another host hands a live access token to that
    host. The checks are ported whole from TriffView and are load-bearing.
    """
    if not isinstance(path, str):
        raise ValueError("ESI path must be a string.")
    if not path.startswith("/"):
        raise ValueError("ESI path must start with '/'.")
    # "//host/x" is a protocol-relative URL: joined to a base it resolves to
    # a different authority while still looking like a path.
    if path.startswith("//"):
        raise ValueError("ESI path must not start with '//'.")
    if "://" in path:
        raise ValueError("ESI path must not be an absolute URL.")
    for forbidden, label in (("\\", "backslash"), ("?", "query"),
                             ("#", "fragment"), ("\x00", "NUL")):
        if forbidden in path:
            raise ValueError(f"ESI path must not contain a {label}.")

    body = path[1:]
    # Exactly one optional trailing slash: ESI's own routes carry it
    # ("/v3/universe/ids/"), but a second one is an empty segment.
    if body.endswith("/"):
        body = body[:-1]
    if not body:
        raise ValueError("ESI path must name at least one segment.")
    for segment in body.split("/"):
        if not segment:
            raise ValueError("ESI path segments must not be empty.")
        if segment in (".", ".."):
            raise ValueError("ESI path must not contain '.' or '..'.")
        if not _SEGMENT.match(segment):
            raise ValueError(
                f"ESI path segment {segment!r} has characters outside "
                "[A-Za-z0-9_-].")
    return path


def _default_transport(request, timeout=None):
    return urllib.request.urlopen(request, timeout=timeout)


@dataclass(frozen=True)
class EsiResponse:
    status: int
    data: object
    error: str
    etag: str
    method: str
    path: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def not_modified(self) -> bool:
        return self.status == 304


def _redact(text: str, token) -> str:
    """Strip an access token out of anything that could reach a log.

    Guarded on length because a very short token would be a common
    substring and redacting it would mangle unrelated text. Real EVE access
    tokens run to hundreds of characters, so the guard never fires in
    production -- it exists so a test fixture using "tok" cannot make this
    function destructive.

    EsiClient.cs's own Redact() has no such floor -- TriffView never hands
    it a short secret, so the case never arose there. This is a deliberate,
    documented divergence rather than a silent gap: the floor only ever
    matters against a short *test* token, and this file's own fixtures use
    exactly that ("tok"), so removing it would make this function corrupt
    strings in this project's test output the day someone adds a fixture
    using a short bearer value.
    """
    if token and len(token) >= 8:
        return text.replace(token, "[redacted]")
    return text


def _header_seconds(headers, name: str):
    """A header's value as seconds, or None.

    Retry-After may legally be an HTTP-date. That form is deliberately not
    parsed: the fallback ladder is a fine answer, and a date parser here
    would be more code than the case is worth. Returning None routes it
    there.

    Strictly positive, not merely non-negative: a server sending
    Retry-After: 0 or X-Esi-Error-Limit-Reset: 0 is not asking for a
    zero-delay retry, it is a value this code must not trust literally --
    treating 0 as "wait zero seconds" would turn the backoff ladder into a
    hot loop against an API that just told the client to slow down. 0 is
    therefore absent, exactly like a missing or unparsable header, and
    falls through to the fixed ladder below.
    """
    if headers is None:
        return None
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _is_ids_route(path: str) -> bool:
    """Whether *path* is the universe/ids batch lookup.

    The only POST this package retries. A retried non-idempotent request is
    the classic way to duplicate a write, so the allowance is a route check
    rather than a method check -- this package makes no writes today and the
    guard keeps that true if one is ever added. A leading version segment is
    tolerated so a bump from /v3/ to /v4/ does not silently lose the retry,
    which would surface as an intermittently failing first refresh that
    nobody connects back to this line.
    """
    segments = [s for s in path.split("/") if s]
    if segments and _VERSION_SEGMENT.match(segments[0]):
        segments = segments[1:]
    return tuple(segments) == ("universe", "ids")


class EsiClient:
    def __init__(self, *, user_agent: str, transport=_default_transport,
                 sleep=time.sleep) -> None:
        self._user_agent = user_agent
        self._transport = transport
        self._sleep = sleep

    def get(self, path: str, *, token=None, etag=None) -> EsiResponse:
        return self._request("GET", path, token=token, etag=etag)

    def post(self, path: str, body, *, token=None) -> EsiResponse:
        return self._request("POST", path, body=body, token=token)

    def _request(self, method: str, path: str, *, body=None, token=None,
                 etag=None) -> EsiResponse:
        # Raises, deliberately: a bad path is a bug in the caller, not a
        # runtime condition, and it must never reach the network.
        validate_path(path)
        url = application.ESI_BASE + path
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "X-Compatibility-Date": application.ESI_COMPATIBILITY_DATE,
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if etag:
            headers["If-None-Match"] = etag

        retryable_method = method == "GET" or _is_ids_route(path)
        last_error = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = urllib.request.Request(url, data=payload,
                                             headers=headers, method=method)
            try:
                with self._transport(request, timeout=TIMEOUT_S) as response:
                    return self._read(response, method, path, etag)
            except urllib.error.HTTPError as exc:
                # HTTPError subclasses URLError subclasses OSError, so this
                # clause MUST come first. Below the network clause, a 404
                # would be treated as a connection failure and retried three
                # times against the error-limit budget.
                if exc.code == 304:
                    # urlopen RAISES for every non-2xx status -- 304
                    # included. HTTPRedirectHandler only implements
                    # http_error_301/302/303/307/308; there is no
                    # http_error_304, so a real 304 falls through to
                    # http_error_default and comes out here, not through
                    # the normal return above. Handled as a non-error
                    # response, not folded into the generic error branch
                    # below: 304 means "what you have is current," so data
                    # stays None (an empty dict here would read as a
                    # character with no skills, which is data loss) and the
                    # ETag the CALLER sent is preserved -- a 304 body
                    # carries no new validator to replace it with, so
                    # losing it here would cost every subsequent refresh
                    # its conditional request and silently double ESI load.
                    exc_headers = getattr(exc, "headers", None)
                    response_etag = (exc_headers.get("ETag", "")
                                     if exc_headers else "") or ""
                    return EsiResponse(304, None, "", etag or response_etag,
                                       method, path)
                text = self._error_text(exc, token)
                if exc.code in RETRY_STATUSES and retryable_method:
                    last_error = text
                    if attempt < MAX_ATTEMPTS:
                        self._sleep(self._backoff(exc.headers, attempt))
                    continue
                return EsiResponse(exc.code, None, text, "", method, path)
            except (urllib.error.URLError, socket.timeout, OSError) as exc:
                # No response, so no headers to read a suggested wait from.
                # The ladder is fixed and short: a refresh is sequential, so
                # every second spent here delays every character behind it.
                last_error = _redact(f"Network error: {exc}", token)
                if attempt < MAX_ATTEMPTS:
                    self._sleep(NETWORK_BACKOFF_S * attempt)
                continue

        # Exhausted. Return rather than raise: a refresh iterates characters
        # sequentially and one exhausted character must record an error and
        # let the loop continue to the next.
        #
        # The 503 is SYNTHETIC -- it did not necessarily come from ESI. The
        # upstream failure may have been any status in RETRY_STATUSES, or no
        # response at all, and a caller reading it as an upstream outage
        # will be wrong about the cause.
        return EsiResponse(
            503, None,
            last_error or f"No response after {MAX_ATTEMPTS} attempts.",
            "", method, path)

    @staticmethod
    def _read(response, method: str, path: str, sent_etag) -> EsiResponse:
        # 304 no longer reaches here: urlopen raises HTTPError for it, and
        # that is handled in _request. This path only ever sees a genuine
        # 2xx-or-similar response the transport returned rather than raised.
        status = getattr(response, "status", 200)
        response_etag = response.headers.get("ETag", "") or ""
        # Read one byte past the cap so oversize is detectable without
        # buffering the whole thing first.
        raw = response.read(MAX_SUCCESS_BODY_BYTES + 1)
        if len(raw) > MAX_SUCCESS_BODY_BYTES:
            raise ValueError(
                f"ESI response for {path} exceeded "
                f"{MAX_SUCCESS_BODY_BYTES} bytes.")
        data = json.loads(raw.decode("utf-8")) if raw.strip() else None
        return EsiResponse(status, data, "", response_etag, method, path)

    @staticmethod
    def _backoff(headers, attempt: int) -> float:
        """Retry-After, then X-Esi-Error-Limit-Reset, then the ladder.

        The order is not arbitrary. Retry-After is a specific instruction
        about this request; the reset is the window before the shared error
        budget refills. Preferring the budget window when a specific wait
        was given would sit on the worker thread longer than asked.
        """
        for name in ("Retry-After", "X-Esi-Error-Limit-Reset"):
            seconds = _header_seconds(headers, name)
            if seconds is not None:
                return min(seconds, MAX_BACKOFF_S)
        return BASE_BACKOFF_S * attempt

    @staticmethod
    def _error_text(exc, token) -> str:
        try:
            raw = exc.read(MAX_ERROR_BODY_BYTES + 1)
        except Exception:
            # HTTPError is not guaranteed to carry a readable body, and a
            # failure to read the explanation must not replace the status we
            # already have with a traceback.
            raw = b""
        text = raw.decode("utf-8", "replace")
        if len(raw) > MAX_ERROR_BODY_BYTES:
            # Truncated rather than dropped: the first 8 KiB of an error
            # page is where the reason is, and the rest is usually markup.
            text = text[:MAX_ERROR_BODY_BYTES] + "... [truncated]"
        return _redact(f"HTTP {exc.code}: {text}".strip(), token)
