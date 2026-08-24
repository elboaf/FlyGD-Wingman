"""Path hardening, retries, backoff order, redaction, and the synthetic 503.

Transport and sleep are injected, matching discord.py:196-197,224. HTTP is
stdlib urllib.request: this app has no requests dependency and discord.py is
the house pattern for doing without one.

The 304 fixtures raise urllib.error.HTTPError rather than returning a
_Response(304): urlopen's HTTPErrorProcessor routes every non-2xx status,
304 included, to the error path. HTTPRedirectHandler only implements
http_error_301/302/303/307/308 -- there is no http_error_304 -- so a real
304 falls through to http_error_default and raises. A test double that
instead RETURNED a 304 response would exercise a code path production never
takes.
"""
import io
import json
import socket
import urllib.error
from email.message import Message

import pytest

from obs_youtube_uploader.eveskills import esi


def test_a_normal_path_is_returned_unchanged():
    assert esi.validate_path("/v3/universe/types/3300/") == \
        "/v3/universe/types/3300/"


def test_a_path_without_a_trailing_slash_is_accepted():
    assert esi.validate_path("/v3/universe/types/3300") == \
        "/v3/universe/types/3300"


@pytest.mark.parametrize("path", [
    "characters/1/skills/",          # no leading slash
    "//evil.example/skills/",        # protocol-relative: another authority
    "https://evil.example/skills/",  # absolute URL
    "/v3\\universe/",                # backslash
    "/v3/universe/?page=2",          # query
    "/v3/universe/#frag",            # fragment
    "/v3/universe/\x00/",            # NUL
    "/v3//universe/",                # empty interior segment
    "/v3/../admin/",                 # dot-dot traversal
    "/v3/./universe/",               # single dot
    "/v3/universe types/",           # space
    "/v3/universe%2Ftypes/",         # percent-encoding
    "/v3/universe/types//",          # empty trailing segment
    "/",                             # no segments
    "",
])
def test_hostile_paths_are_rejected(path):
    """These are all the ways a caller-built path could be steered off the
    intended endpoint. The Authorization header rides on every request, so a
    path that reaches another host hands a live access token to it."""
    with pytest.raises(ValueError):
        esi.validate_path(path)


def test_a_non_string_path_is_rejected():
    with pytest.raises(ValueError):
        esi.validate_path(None)


def test_query_strings_are_structurally_impossible():
    """Recorded as a test rather than only a comment: adding a paging
    parameter to any ESI call requires a deliberate change HERE first, and a
    future author will find this failing before they find the comment."""
    with pytest.raises(ValueError):
        esi.validate_path("/v3/universe/ids/?page=2")


def _headers(**pairs) -> Message:
    """An email.message.Message is exactly what urllib hands back as
    `response.headers`, including its case-insensitive lookup."""
    message = Message()
    for key, value in pairs.items():
        message[key.replace("_", "-")] = str(value)
    return message


class _Response:
    """The minimal shape urllib returns: a context manager with status,
    headers, and read()."""

    def __init__(self, status, payload=b"", headers=None):
        self.status = status
        self.headers = headers if headers is not None else Message()
        self._stream = io.BytesIO(payload)

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError(
        "https://esi.evetech.net/x", code, "err",
        headers if headers is not None else Message(), io.BytesIO(body))


class FakeTransport:
    """Records requests and replays a scripted list of outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeSleep:
    """Records the delays asked for without spending any wall time."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def _client(outcomes, sleep=None):
    return esi.EsiClient(user_agent="TestAgent/1.0",
                         transport=FakeTransport(outcomes),
                         sleep=sleep or FakeSleep())


def test_a_successful_get_returns_parsed_json():
    client = _client([_Response(200, b'{"skills": []}')])
    response = client.get("/v6/characters/1/skills/")
    assert response.ok is True
    assert response.data == {"skills": []}
    assert response.error == ""


def test_every_request_carries_the_required_headers():
    """User-Agent identifies the app to CCP, X-Compatibility-Date pins the
    schema, and Accept stops a proxy negotiating something else."""
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="TestAgent/1.0", transport=transport,
                           sleep=FakeSleep())
    client.get("/v6/characters/1/skills/")
    headers = transport.requests[0].headers
    assert headers["User-agent"] == "TestAgent/1.0"
    assert headers["Accept"] == "application/json"
    assert headers["X-compatibility-date"] == \
        esi.application.ESI_COMPATIBILITY_DATE
    assert "Authorization" not in headers


def test_a_token_becomes_a_bearer_header():
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    client.get("/v6/characters/1/skills/", token="tok")
    assert transport.requests[0].headers["Authorization"] == "Bearer tok"


def test_an_etag_becomes_an_if_none_match_header():
    """The one place this port knowingly improves on TriffView, which sends
    no conditional requests at all: forty characters is eighty full
    refetches per click, charged against the error-limit budget to
    re-download data that mostly has not changed."""
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    client.get("/v6/characters/1/skills/", etag='W/"abc"')
    assert transport.requests[0].headers["If-none-match"] == 'W/"abc"'


def test_a_304_carries_no_data_and_keeps_the_sent_etag():
    """304 means "what you have is current". data must be None so a caller
    cannot mistake it for an empty skill list, and the etag must survive so
    the next refresh still sends it -- a 304 body carries no new validator
    to replace it with.

    Modelled as an HTTPError, not a _Response(status=304): urlopen raises
    for every non-2xx status and there is no http_error_304 handler to
    redirect it back onto the normal-return path."""
    client = _client([_http_error(304)])
    response = client.get("/v6/characters/1/skills/", etag='W/"abc"')
    assert response.not_modified is True
    assert response.ok is False
    assert response.data is None
    assert response.etag == 'W/"abc"'


def test_a_304_with_no_sent_etag_falls_back_to_the_response_etag():
    """Rare in practice (a 304 with no If-None-Match sent at all would be
    unusual), but if the server includes its own ETag on the 304, that is
    still better than the empty string a caller who sent nothing has."""
    client = _client([_http_error(304, headers=_headers(ETag='W/"srv"'))])
    response = client.get("/v6/characters/1/skills/")
    assert response.etag == 'W/"srv"'


def test_a_response_etag_is_captured():
    client = _client([_Response(200, b"{}", _headers(ETag='W/"new"'))])
    assert client.get("/v6/characters/1/skills/").etag == 'W/"new"'


def test_the_method_and_path_come_back_on_the_response():
    """The controller commits both halves of a snapshot together, so it has
    to be able to tell which half a response belongs to."""
    client = _client([_Response(200, b"{}")])
    response = client.get("/v6/characters/1/skills/")
    assert (response.method, response.path) == \
        ("GET", "/v6/characters/1/skills/")


def test_post_sends_a_json_body():
    transport = FakeTransport([_Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    client.post("/v3/universe/ids/", ["Navigation"])
    request = transport.requests[0]
    assert request.get_method() == "POST"
    assert json.loads(request.data.decode("utf-8")) == ["Navigation"]
    assert request.headers["Content-type"] == "application/json"


def test_an_invalid_path_raises_before_any_request_is_made():
    """Path validation guards a programming error, not a runtime condition,
    so it raises rather than returning a response -- and it must fire before
    the transport sees anything."""
    transport = FakeTransport([])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    with pytest.raises(ValueError):
        client.get("/v3/universe/?page=2")
    assert transport.requests == []


def test_a_retryable_status_is_retried_and_then_succeeds():
    sleep = FakeSleep()
    client = _client([_http_error(503), _Response(200, b'{"ok": 1}')], sleep)
    response = client.get("/v6/characters/1/skills/")
    assert response.data == {"ok": 1}
    assert sleep.delays == [pytest.approx(0.650)]


def test_a_non_retryable_status_returns_immediately():
    """401 and 403 are definitive -- they mean re-authenticate, and burning
    two more requests against the error-limit budget to confirm it costs the
    other characters queued behind this one in the refresh."""
    transport = FakeTransport([_http_error(403, b'{"error":"forbidden"}')])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    response = client.get("/v6/characters/1/skills/")
    assert response.status == 403
    assert len(transport.requests) == 1


def test_backoff_grows_with_the_attempt():
    sleep = FakeSleep()
    _client([_http_error(500), _http_error(500), _http_error(500)],
            sleep).get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(0.650), pytest.approx(1.300)]


def test_retry_after_wins_over_the_default_backoff():
    sleep = FakeSleep()
    client = _client([_http_error(429, headers=_headers(Retry_After=7)),
                      _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(7.0)]


def test_the_error_limit_reset_is_used_when_retry_after_is_absent():
    """420 is ESI's error-limited status and carries the reset rather than
    Retry-After. Ignoring it is how a client gets its budget zeroed."""
    sleep = FakeSleep()
    client = _client(
        [_http_error(420, headers=_headers(X_Esi_Error_Limit_Reset=12)),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(12.0)]


def test_retry_after_wins_over_the_error_limit_reset():
    """The order is asserted rather than assumed: Retry-After is a specific
    instruction about this request, the reset is the window before the error
    budget refills."""
    sleep = FakeSleep()
    client = _client(
        [_http_error(429, headers=_headers(Retry_After=3,
                                           X_Esi_Error_Limit_Reset=25)),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(3.0)]


def test_a_server_suggested_wait_is_capped():
    """A hostile or misconfigured Retry-After would otherwise hold a refresh
    worker for a day, which the user cannot tell from a crash."""
    sleep = FakeSleep()
    client = _client([_http_error(429, headers=_headers(Retry_After=86400)),
                      _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(esi.MAX_BACKOFF_S)]


def test_a_non_numeric_retry_after_falls_through_to_the_default():
    """Retry-After may legally be an HTTP-date. That form is not parsed
    here, and the fallback must be the ladder rather than a crash."""
    sleep = FakeSleep()
    client = _client(
        [_http_error(503,
                     headers=_headers(Retry_After="Wed, 21 Oct 2026 07:28:00 GMT")),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(0.650)]


def test_a_zero_retry_after_is_treated_as_absent():
    """A Retry-After (or X-Esi-Error-Limit-Reset) of 0 is not a real
    instruction to retry immediately -- treating it literally would turn the
    backoff ladder into a hot loop against an API that just asked for a
    slowdown. It must fall through to the fixed ladder exactly like a
    missing or unparsable header."""
    sleep = FakeSleep()
    client = _client([_http_error(429, headers=_headers(Retry_After=0)),
                      _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(0.650)]


def test_a_zero_error_limit_reset_is_treated_as_absent():
    sleep = FakeSleep()
    client = _client(
        [_http_error(420, headers=_headers(X_Esi_Error_Limit_Reset=0)),
         _Response(200, b"{}")], sleep)
    client.get("/v6/characters/1/skills/")
    assert sleep.delays == [pytest.approx(0.650)]


def test_exhausting_the_retries_returns_a_synthetic_503():
    """Returns, never raises: a refresh iterates characters sequentially,
    and one exhausted character must record an error and let the loop go on
    to the next.

    The caller must NOT read this 503 as "ESI said 503" -- it is synthesised
    here, and the upstream failure may have been any status in the retry set
    or no response at all."""
    transport = FakeTransport([_http_error(500)] * esi.MAX_ATTEMPTS)
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    response = client.get("/v6/characters/1/skills/")
    assert response.status == 503
    assert response.ok is False
    assert response.error
    assert len(transport.requests) == esi.MAX_ATTEMPTS


def test_network_errors_retry_on_their_own_ladder():
    """A connection that never opened produced no headers to read a
    server-suggested wait from, so the ladder is fixed and short."""
    sleep = FakeSleep()
    client = _client([urllib.error.URLError("no route"),
                      socket.timeout("timed out"),
                      _Response(200, b"{}")], sleep)
    assert client.get("/v6/characters/1/skills/").ok is True
    assert sleep.delays == [pytest.approx(0.5), pytest.approx(1.0)]


def test_an_oserror_from_the_transport_is_retried_not_raised():
    sleep = FakeSleep()
    client = _client([OSError("connection reset"), _Response(200, b"{}")],
                     sleep)
    assert client.get("/v6/characters/1/skills/").ok is True


def test_the_access_token_is_redacted_from_error_text():
    """The error string reaches a log and a per-character UI row. A bearer
    token echoed back by an ESI error page or a proxy would be written to
    both, in plain text, where it stays until log rotation."""
    token = "eyJhbGciOiJSUzI1NiJ9.super-secret-access-token.sig"
    body = json.dumps({"error": f"invalid token {token}"}).encode("utf-8")
    client = _client([_http_error(400, body)])
    response = client.get("/v6/characters/1/skills/", token=token)
    assert token not in response.error
    assert "[redacted]" in response.error


def test_an_oversized_error_body_is_truncated():
    """An error page can be a full HTML document. 8 KiB is enough to see
    what happened and small enough not to fill the log."""
    body = b"x" * (esi.MAX_ERROR_BODY_BYTES * 2)
    response = _client([_http_error(400, body)]).get("/v6/characters/1/skills/")
    assert response.error.endswith("... [truncated]")
    assert len(response.error) < esi.MAX_ERROR_BODY_BYTES + 200


def test_an_oversized_success_body_raises():
    """Unlike an error body this is not truncated: half a JSON document is
    not parseable, and silently returning None would look to the caller like
    an empty skill list."""
    payload = b'{"pad": "' + b"y" * (esi.MAX_SUCCESS_BODY_BYTES + 10) + b'"}'
    with pytest.raises(ValueError):
        _client([_Response(200, payload)]).get("/v6/characters/1/skills/")


def test_a_post_to_the_ids_route_is_retried():
    """The batch name lookup is idempotent and is the only POST this package
    makes. A first refresh over a large plan set depends on it."""
    transport = FakeTransport([_http_error(503), _Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    assert client.post("/v3/universe/ids/", ["Navigation"]).ok is True
    assert len(transport.requests) == 2


def test_a_version_bump_keeps_the_ids_route_retryable():
    """Matching the literal "/v3/universe/ids/" would silently lose the
    retry the day CCP ships v4, and the symptom would be an intermittent
    first refresh nobody connects back to the route check."""
    transport = FakeTransport([_http_error(503), _Response(200, b"{}")])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    assert client.post("/v4/universe/ids/", ["Navigation"]).ok is True
    assert len(transport.requests) == 2


def test_a_post_to_any_other_route_is_not_retried():
    """A retried non-idempotent POST is the classic way to duplicate a
    write. This package makes no writes today, and the guard is a route
    check rather than a method check so that stays true if one is added."""
    transport = FakeTransport([_http_error(503)])
    client = esi.EsiClient(user_agent="A", transport=transport,
                           sleep=FakeSleep())
    response = client.post("/v1/ui/openwindow/", {})
    assert response.status == 503
    assert len(transport.requests) == 1
