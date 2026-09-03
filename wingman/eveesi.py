"""Shared secure ESI transport: path hardening, bounded retries, ETags,
and an exactly-one-attempt mutation path.

Transport and sleep are injected with production defaults, the seam
discord.py:196-197,224 establishes, which is what lets the whole retry and
backoff ladder be tested headless with no real sleeps.

This module is the shared authority for talking to ESI: Skills' read-only
GET/ids-lookup traffic and Fittings' mutation POSTs both go through the
one `EsiClient` defined here. `wingman/eveskills/esi.py` re-exports these
symbols rather than duplicating them, which is what keeps the retry
ladder, redaction, and no-redirect opener defined and tested in exactly
one place as a second capability starts using them.
"""

import http.client
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass

# eveesi.py sits above eveskills/ in the package but still depends on its
# application identity constants (ESI_BASE, ESI_COMPATIBILITY_DATE):
# those have not moved yet -- eveauth's extraction of shared application
# identity is a later task -- and eveskills.application is preserved as a
# compatibility import indefinitely, so this dependency does not need to
# change when that extraction lands.
from .eveskills import application

MAX_ATTEMPTS = 3
MAX_ERROR_BODY_BYTES = 8192
MAX_SUCCESS_BODY_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = frozenset({408, 420, 429, 500, 502, 503, 504})
TIMEOUT_S = 20.0

# EsiClient.cs's Sanitize() caps the extracted error TEXT (not the raw body
# read from the wire) at this length before it can reach a log or the UI.
_SANITIZE_MAX_CHARS = 2048

# Server-suggested waits are honoured but capped: a misconfigured or hostile
# Retry-After of 86400 would otherwise hold a refresh worker for a day, and
# the user cannot tell that apart from a crash.
MAX_BACKOFF_S = 30.0
BASE_BACKOFF_S = 0.650
NETWORK_BACKOFF_S = 0.500

# A single mutation attempt never sleeps or retries, so it has no backoff
# ladder of its own -- only this bound on how many response headers get
# copied into a MutationResponse. A hostile or misbehaving proxy in front
# of ESI could otherwise hand back thousands of headers; nothing in this
# app needs more than a handful (rate-limit headers, ETag, Location).
MAX_MUTATION_HEADERS = 32

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
    for forbidden, label in (
        ("\\", "backslash"),
        ("?", "query"),
        ("#", "fragment"),
        ("\x00", "NUL"),
    ):
        if forbidden in path:
            raise ValueError(f"ESI path must not contain a {label}.")

    body = path[1:]
    # Exactly one optional trailing slash: ESI's own routes carry it
    # ("/v3/universe/ids/"), but a second one is an empty segment.
    body = body.removesuffix("/")
    if not body:
        raise ValueError("ESI path must name at least one segment.")
    for segment in body.split("/"):
        if not segment:
            raise ValueError("ESI path segments must not be empty.")
        if segment in (".", ".."):
            raise ValueError("ESI path must not contain '.' or '..'.")
        if not _SEGMENT.match(segment):
            raise ValueError(
                f"ESI path segment {segment!r} has characters outside [A-Za-z0-9_-]."
            )
    return path


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects on any ESI request.

    Ported from discord.py:175-197, which exists for the identical reason:
    urllib's default HTTPRedirectHandler.redirect_request() carries every
    request header across a redirect except Content-Length and
    Content-Type -- Authorization is NOT stripped, and there is no
    same-origin check on the Location header. .NET's HttpClientHandler
    strips Authorization on a cross-host redirect; urllib does not, and
    EsiClient.cs never had to think about this because of it.

    Every authenticated call here carries a live EVE Bearer token in that
    header. Without this handler, a 3xx response -- from ESI, from a
    compromised or misconfigured proxy in front of it, or from anything
    on the path -- would silently resend that token to wherever Location
    points, with no host check at all. Returning None here tells urllib
    "don't redirect"; the 3xx then surfaces as an ordinary HTTPError, like
    any other non-2xx status, and nothing is ever sent past the URL this
    module itself built.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


# Module-level so every call shares one opener, matching discord.py's
# _opener -- and so a test can assert on _opener.handlers directly rather
# than only on _NoRedirectHandler in isolation (see
# test_the_default_opener_refuses_redirects in test_discord.py, which this
# module's own equivalent test is modelled on).
_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


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


@dataclass(frozen=True)
class MutationResponse:
    """The outcome of exactly one mutation attempt.

    `response_received` is the one distinction the whole type exists to
    make: True means ESI (or whatever sits in front of it) actually sent
    something back -- `status` is real, whatever it is -- while False
    means the attempt raised before any response arrived, and `status` is
    None because there is no real status to report. A caller must never
    collapse these into a single "failed" outcome: the design's copy
    executor treats a definite rejection (response received, deterministic
    4xx) as Failed but a no-response outcome as Unknown, and those two
    error strings alone do not carry that distinction back -- only this
    field does.

    `post_once` never raises for a response it received, however
    malformed: a non-JSON or over-size 2xx body still comes back as
    `response_received=True` with `data=None` and `error` describing the
    anomaly, so the caller can classify it deliberately rather than have
    an exception replace the outcome it needs to record.
    """

    response_received: bool
    status: int | None
    data: object
    error: str
    headers: dict[str, str]


# Below this length a token is a common substring, and blindly replacing
# every occurrence of it anywhere in a log line would corrupt unrelated
# text instead of redacting a secret -- the same reasoning discord.py:25-31
# gives for _MIN_REDACTABLE_TOKEN_LEN there. Real EVE access tokens run to
# hundreds of characters, so the guard never fires in production; it exists
# so a short token (this file's own fixtures use "tok") cannot make this
# function destructive. EsiClient.cs's Redact() has no such floor -- it is
# never handed anything but a real, long secret, so the case never arose
# there. Named, not a bare literal, to match discord.py's own constant.
_MIN_REDACTABLE_TOKEN_LEN = 8


def _redact(text: str, token) -> str:
    """Strip an access token out of anything that could reach a log."""
    if token and len(token) >= _MIN_REDACTABLE_TOKEN_LEN:
        return text.replace(token, "[redacted]")
    return text


def _sanitize(text) -> str:
    """Strip control characters, fold newlines to spaces, and cap length.

    Ports EsiClient.cs's Sanitize() (:258-268) whole. \\r, \\n and \\t are
    kept through the filtering step and folded (\\r, \\n only) to a space
    AFTER the length cap is applied, not before: dropping them first would
    let a message that is mostly newlines pad itself out with characters
    about to become nothing anyway, silently admitting more real content
    than the cap is meant to allow. Every other Unicode control character
    (category Cc) is dropped outright -- an error string reaches a log file
    and a UI row, neither of which should ever render raw control bytes.

    Never returns an empty string: a body that sanitizes down to nothing
    (all control characters, or blank) is exactly as uninformative as one
    that failed to parse at all, so both get the same fixed message.
    """
    text = text if isinstance(text, str) else ""
    filtered = "".join(
        ch for ch in text if ch in "\r\n\t" or unicodedata.category(ch) != "Cc"
    )[:_SANITIZE_MAX_CHARS]
    cleaned = filtered.replace("\r", " ").replace("\n", " ").strip()
    return cleaned or "Remote service returned an unreadable error."


def _extract_remote_error(text: str, token) -> str:
    """Pull the "error" field out of an ESI error body, sanitized and
    redacted. Ports EsiClient.cs's ReadError() (:164-179) whole.

    Only ever the "error" field, never the raw body -- see _error_text's
    own docstring for why. Any parse failure (not JSON, not an object, no
    "error" field, or a non-string/blank one) collapses to the same fixed
    message ESI-Client.cs uses, rather than leaking whatever the body
    actually contained.
    """
    if not text or not text.strip():
        return "No response body."
    try:
        parsed = json.loads(text)
        remote = parsed.get("error") if isinstance(parsed, dict) else None
    except ValueError:
        return "Remote service returned an unreadable error."
    if not isinstance(remote, str) or not remote.strip():
        return "Remote service returned an unreadable error."
    return _redact(_sanitize(remote), token)


def _append_rate_limit(error: str, headers, token=None) -> str:
    """Append the error-limit and Retry-After headers to *error*.

    Ports EsiClient.cs's AppendRateLimit() (:212-222) whole. This is the
    one signal that makes ESI's shared error-limit budget visible at all;
    without it, a character silently backing off from 420s looks identical
    to one failing for any other reason. Re-sanitizes the combined string
    (matching the source exactly) rather than trusting the values are
    already clean -- a header value is attacker- or proxy- controlled
    input exactly as much as the body is.

    Also redacts the fully assembled string, not just the sanitized
    *error* it started from: these header VALUES are exactly as
    attacker/proxy-controlled as the body, and a hostile or misconfigured
    proxy echoing the Authorization header back in Retry-After or an
    error-limit header would otherwise leak the live bearer token into a
    string this module hands back to a caller to log or display.

    Redacted BEFORE the final sanitize/truncate, not after: _sanitize
    caps this combined string at 2048 characters, and a token whose bytes
    straddle that cutoff would have its closing half truncated away while
    its opening half survived untouched -- a partial, unredacted token
    prefix sitting in the output, silently missed by _redact's exact
    substring match, which can no longer recognize a fragment of the
    token as the token once the other half is gone. Redacting the
    complete, untruncated assembly first guarantees the whole token is
    still there to match against, and only the (now token-free) result is
    ever truncated.
    """
    if headers is None:
        return error
    parts = []
    for name in ("X-Esi-Error-Limit-Remain", "X-Esi-Error-Limit-Reset", "Retry-After"):
        value = headers.get(name)
        if value is not None:
            parts.append(f"{name}={_sanitize(str(value))}")
    if not parts:
        return error
    combined = f"{error} ({'; '.join(parts)})"
    return _sanitize(_redact(combined, token))


def _bounded_headers(headers, token=None) -> dict[str, str]:
    """A plain, bounded, redacted dict view of a urllib headers object.

    Exists only for MutationResponse.headers -- GET's EsiResponse never
    carried raw headers and this does not change that. Bounded on two
    axes independently: MAX_MUTATION_HEADERS caps how many header LINES
    are copied at all, and _sanitize's own cap bounds each value's length,
    so neither a header flood nor one absurdly long header value can turn
    a single mutation's result into an unbounded object a caller might log
    or persist whole.
    """
    if headers is None:
        return {}
    bounded: dict[str, str] = {}
    for name, value in headers.items():
        if len(bounded) >= MAX_MUTATION_HEADERS:
            break
        bounded[name] = _redact(_sanitize(str(value)), token)
    return bounded


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
    def __init__(
        self, *, user_agent: str, transport=_default_transport, sleep=time.sleep
    ) -> None:
        self._user_agent = user_agent
        self._transport = transport
        self._sleep = sleep

    def get(self, path: str, *, token=None, etag=None) -> EsiResponse:
        return self._request("GET", path, token=token, etag=etag)

    def post(self, path: str, body, *, token=None) -> EsiResponse:
        return self._request("POST", path, body=body, token=token)

    def post_once(self, path: str, body, *, token: str) -> MutationResponse:
        """Make exactly one request; never synthesize or retry an outcome.

        Unlike `get`/`post`, this never sleeps and never loops: a mutation
        is not idempotent, so a request this package cannot prove never
        reached ESI must never be resent automatically. The one attempt's
        real result -- including "no response at all" -- is reported back
        verbatim so the caller can decide what "no response" means for a
        write (see the design doc: "Timeout, no response, 408, or 5xx is
        Unknown unless ESI documents that the response guarantees
        non-creation").
        """
        validate_path(path)
        url = application.ESI_BASE + path
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Compatibility-Date": application.ESI_COMPATIBILITY_DATE,
            "Authorization": f"Bearer {token}",
        }
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, headers=headers, method="POST"
        )
        try:
            with self._transport(request, timeout=TIMEOUT_S) as response:
                # Status and headers are already real the moment the
                # transport returns a response object -- the connection
                # succeeded and the status line/headers arrived. Only the
                # BODY read below can still fail (a dropped connection
                # mid-stream, a read timeout, an interrupted chunked
                # transfer), and that failure must not erase the response
                # that already happened: see the try/except around
                # response.read() below.
                status = getattr(response, "status", 200)
                response_headers = _bounded_headers(response.headers, token)
                try:
                    # Read one byte past the cap so oversize is detectable
                    # without buffering the whole thing first, exactly as
                    # EsiClient._read does for GET.
                    raw = response.read(MAX_SUCCESS_BODY_BYTES + 1)
                except (TimeoutError, OSError, http.client.IncompleteRead) as exc:
                    # A response WAS received -- status and headers are
                    # real -- but the body read itself failed partway
                    # through. Without this clause, TimeoutError/OSError
                    # would escape this inner try and be caught by the
                    # outer no-response handler below, which reports
                    # response_received=False and discards the real status
                    # this attempt already has; http.client.IncompleteRead
                    # (raised by http.client's own chunked/length-based
                    # reader, and not an OSError subclass) would escape
                    # post_once entirely with no handler at all. Both are a
                    # definite response with a lost body, not "no response".
                    return MutationResponse(
                        True,
                        status,
                        None,
                        _sanitize(_redact(f"Response body read failed: {exc}", token)),
                        response_headers,
                    )
                if len(raw) > MAX_SUCCESS_BODY_BYTES:
                    return MutationResponse(
                        True,
                        status,
                        None,
                        f"Response exceeded {MAX_SUCCESS_BODY_BYTES} bytes.",
                        response_headers,
                    )
                if not raw.strip():
                    return MutationResponse(True, status, None, "", response_headers)
                try:
                    data = json.loads(raw.decode("utf-8"))
                except ValueError:
                    # A response WAS received -- status is real -- but its
                    # body did not parse. This must not raise: the caller
                    # still needs to know a status code came back, which an
                    # exception here would discard along with everything
                    # else in the response.
                    return MutationResponse(
                        True,
                        status,
                        None,
                        "Malformed response body.",
                        response_headers,
                    )
                return MutationResponse(True, status, data, "", response_headers)
        except urllib.error.HTTPError as exc:
            # A definite HTTP response, whatever its status -- including a
            # 3xx, which _NoRedirectHandler ensures is never silently
            # followed and instead surfaces here like any other non-2xx.
            text = self._error_text(exc, token)
            exc_headers = _bounded_headers(exc.headers, token) if exc.headers else {}
            return MutationResponse(True, exc.code, None, text, exc_headers)
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            # No response at all -- the transport raised before a status
            # line ever arrived (the inner try/except above is what
            # reclassifies a body-read failure AFTER a real response, so
            # this clause only ever sees a connection that never produced
            # one). There is nothing to report a status, data, or headers
            # for, and nothing here retries: retrying a write whose
            # delivery is unknown is exactly the duplicate-write hazard
            # this method exists to avoid.
            #
            # Redacted before sanitized, not after: nothing has bounded
            # this text's length yet (unlike an HTTP error body, which is
            # already byte-truncated before it ever reaches redaction), so
            # redacting the full, untruncated message first is what
            # guarantees the length cap below can never split a token in
            # half and leave a partial, unredacted fragment in the output.
            return MutationResponse(
                False,
                None,
                None,
                _sanitize(_redact(f"Network error: {exc}", token)),
                {},
            )

    def _request(
        self, method: str, path: str, *, body=None, token=None, etag=None
    ) -> EsiResponse:
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
        # Tracks the MOST RECENT attempt's outcome, overwritten every
        # iteration -- never accumulated -- so that at exhaustion it
        # reflects only what the final attempt actually produced.
        # An EsiResponse when the last attempt got a real HTTP response
        # (even a failing one); None when it did not get a response at all
        # (a network-level exception). EsiClient.cs's ShouldRetry makes the
        # identical distinction (:183, `if (attempt >= MaxAttempts) return
        # false`): on the final attempt a retryable status is never
        # retried, and SendAsync falls through to the real last response --
        # synthesis happens ONLY when the final attempt raised with no
        # response to report at all.
        last_result = None
        last_network_error = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = urllib.request.Request(
                url, data=payload, headers=headers, method=method
            )
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
                    response_etag = (
                        exc_headers.get("ETag", "") if exc_headers else ""
                    ) or ""
                    return EsiResponse(
                        304, None, "", etag or response_etag, method, path
                    )
                text = self._error_text(exc, token)
                if exc.code in RETRY_STATUSES and retryable_method:
                    # The real response, headers and all -- not just its
                    # message -- so that if this turns out to be the LAST
                    # attempt, exhaustion can return it unchanged instead of
                    # replacing it with a synthetic status that discards
                    # the very rate-limit headers _error_text just appended.
                    last_result = EsiResponse(exc.code, None, text, "", method, path)
                    if attempt < MAX_ATTEMPTS:
                        self._sleep(self._backoff(exc.headers, attempt))
                    continue
                return EsiResponse(exc.code, None, text, "", method, path)
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                # No response, so no headers to read a suggested wait from.
                # The ladder is fixed and short: a refresh is sequential, so
                # every second spent here delays every character behind it.
                #
                # Resets last_result to None: this attempt got no response
                # at all, so if it turns out to be the last one, exhaustion
                # must fall back to the synthetic 503 below rather than
                # returning a stale HTTP response from an earlier attempt.
                last_result = None
                last_network_error = _redact(f"Network error: {exc}", token)
                if attempt < MAX_ATTEMPTS:
                    self._sleep(NETWORK_BACKOFF_S * attempt)
                continue

        # Exhausted. Return rather than raise: a refresh iterates characters
        # sequentially and one exhausted character must record an error and
        # let the loop continue to the next.
        if last_result is not None:
            # The final attempt got a real HTTP response. Return it exactly
            # as ESI (or whatever sits in front of it) sent it -- real
            # status, real sanitized error text, real rate-limit headers
            # already folded in by _error_text. A caller depends on seeing
            # the actual 429 (and its Retry-After/error-limit values) when
            # that is what finally happened, not a 503 that never came from
            # anywhere.
            return last_result

        # The final attempt raised with no response to report at all, so
        # there is nothing real left to return. The 503 here is SYNTHETIC
        # -- it did not necessarily come from ESI. The upstream failure may
        # have been any status in RETRY_STATUSES on an earlier attempt, or
        # no response at all, and a caller reading it as an upstream outage
        # will be wrong about the cause.
        return EsiResponse(
            503,
            None,
            last_network_error or f"No response after {MAX_ATTEMPTS} attempts.",
            "",
            method,
            path,
        )

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
                f"ESI response for {path} exceeded {MAX_SUCCESS_BODY_BYTES} bytes."
            )
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
        """The full non-success handling ESI-Client.cs splits across
        ReadError() (:164-179) and AppendRateLimit() (:212-222): read the
        body, extract only the "error" field, sanitize it, redact the
        token, then append the rate-limit headers.

        Deliberately narrow at the extraction step: only the JSON "error"
        field is ever surfaced, never the raw body. A raw pass-through
        would put whatever the server -- or a misconfigured or hostile
        proxy in front of it -- chose to send (arbitrary markup, escape
        sequences, unbounded length) directly into a field that reaches
        the UI, which is exactly the shape of injection this port must
        not reopen.
        """
        try:
            raw = exc.read(MAX_ERROR_BODY_BYTES + 1)
        except Exception:  # noqa: BLE001 - a body we cannot read is not a verdict
            # HTTPError is not guaranteed to carry a readable body, and a
            # failure to read the explanation must not replace the status we
            # already have with a traceback.
            raw = b""
        text = raw.decode("utf-8", "replace")
        if len(raw) > MAX_ERROR_BODY_BYTES:
            # Truncated rather than dropped: the first 8 KiB of an error
            # page is where the reason is, and the rest is usually markup.
            # If this cut a JSON document mid-string, _extract_remote_error
            # below will simply fail to parse it and fall back to its own
            # generic message -- matching ReadLimitedBodyAsync's identical
            # truncate-then-hand-to-ReadError order in the source.
            text = text[:MAX_ERROR_BODY_BYTES] + "... [truncated]"
        error = _extract_remote_error(text, token)
        # Rate-limit headers are appended AFTER extraction/sanitization,
        # not folded into the raw body beforehand: appending first would
        # feed AppendRateLimit's own output back through Sanitize a second
        # time against a base that was never validated as JSON, and could
        # let a long, un-sanitized base swallow the values this step exists
        # to surface. Matches EsiClient.cs's own ordering: AppendRateLimit
        # runs on ReadError's already-sanitized result, not on the raw text.
        return _append_rate_limit(error, exc.headers, token)
