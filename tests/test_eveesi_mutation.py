"""`post_once`: exactly one network attempt, never a retry, never a
synthesized outcome.

The one distinction this whole test file exists to nail down is
`response_received`: True means ESI (or whatever sits in front of it)
actually answered -- `status` is real, whatever it is, even a 500 or a
429 -- while False means the attempt raised before anything came back,
and there is no real status to report. A caller must be able to tell
those apart without inspecting `error` text, because the design's copy
executor treats a definite HTTP response very differently from no
response at all (Failed vs. Unknown).

Modelled directly on test_eveskills_esi.py's fixtures (`_headers`,
`_Response`, `_http_error`, `FakeTransport`) rather than reinventing
them, since post_once shares the exact same transport contract GET does.
"""

import http.client
import io
import json
import urllib.error
from email.message import Message

from wingman import eveesi

PATH = "/characters/42/fittings"
BODY = {"name": "Fit", "ship_type_id": 1, "items": []}
TOKEN = "a-token-long-enough-to-redact"


def _headers(**pairs) -> Message:
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


class _ResponseThatFailsOnRead:
    """A response whose status line and headers arrived normally, but
    whose body read raises. Models a connection that answered and then
    dropped mid-body (a read timeout, a reset, an interrupted chunked
    transfer) -- a definite response with a lost body, not "no response
    at all"."""

    def __init__(self, status, exc, headers=None):
        self.status = status
        self.headers = headers if headers is not None else Message()
        self._exc = exc

    def read(self, size=-1):
        raise self._exc

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError(
        "https://esi.evetech.net/x",
        code,
        "err",
        headers if headers is not None else Message(),
        io.BytesIO(body),
    )


class FakeTransport:
    """Records requests and replays a single scripted outcome. post_once
    is not a retry loop, so unlike test_eveskills_esi.py's FakeTransport
    there is never more than one outcome to pop -- a second call would
    mean post_once retried, and popping from an empty list makes that an
    IndexError rather than a silently-passing test."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []
        self._called = False

    def __call__(self, request, timeout=None):
        assert not self._called, "post_once must make exactly one request"
        self._called = True
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _client(outcome):
    return eveesi.EsiClient(
        user_agent="TestAgent/1.0", transport=FakeTransport(outcome)
    )


def client_for_http_error(code, body=b"", headers=None):
    return _client(_http_error(code, body, headers))


def test_post_once_never_retries_a_timeout():
    calls = []

    def transport(request, timeout=None):
        calls.append(request)
        raise TimeoutError("after send")

    result = eveesi.EsiClient(user_agent="test", transport=transport).post_once(
        "/characters/42/fittings", {"name": "Fit"}, token="long-secret-token"
    )

    assert len(calls) == 1
    assert result.response_received is False
    assert result.status is None
    assert "long-secret-token" not in result.error


def test_post_once_preserves_a_real_500_as_received():
    result = client_for_http_error(500).post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 500


def test_post_once_makes_exactly_one_request():
    transport = FakeTransport(_Response(201, b'{"fitting_id": 1}'))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    client.post_once(PATH, BODY, token=TOKEN)
    assert len(transport.requests) == 1


def test_a_successful_201_returns_the_parsed_fitting_id():
    transport = FakeTransport(_Response(201, b'{"fitting_id": 12345}'))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 201
    assert result.data == {"fitting_id": 12345}
    assert result.error == ""


def test_a_malformed_201_body_does_not_raise_and_reports_the_status():
    """A response WAS received -- status is real -- but its body did not
    parse. Raising here would discard the 201 status along with the
    broken body; post_once must instead return it so the caller still
    knows a response came back."""
    transport = FakeTransport(_Response(201, b"not json"))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 201
    assert result.data is None
    assert result.error != ""


def test_a_408_is_returned_once_never_retried():
    transport = FakeTransport(
        _http_error(408, json.dumps({"error": "timeout"}).encode())
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 408
    assert len(transport.requests) == 1


def test_a_420_is_returned_once_never_retried():
    headers = _headers(X_Esi_Error_Limit_Reset=30)
    transport = FakeTransport(
        _http_error(420, json.dumps({"error": "error limited"}).encode(), headers)
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 420
    assert "error limited" in result.error
    assert len(transport.requests) == 1


def test_a_429_is_returned_once_never_retried():
    headers = _headers(Retry_After=5)
    transport = FakeTransport(
        _http_error(429, json.dumps({"error": "throttled"}).encode(), headers)
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 429
    assert "Retry-After=5" in result.error
    assert len(transport.requests) == 1


def test_a_deterministic_4xx_is_returned_once():
    transport = FakeTransport(
        _http_error(422, json.dumps({"error": "invalid item"}).encode())
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 422
    assert "invalid item" in result.error


def test_a_5xx_never_retries():
    transport = FakeTransport(_http_error(503, b'{"error":"boom"}'))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 503
    assert len(transport.requests) == 1


def test_the_success_response_body_is_bounded():
    payload = b'{"pad": "' + b"y" * (eveesi.MAX_SUCCESS_BODY_BYTES + 10) + b'"}'
    transport = FakeTransport(_Response(201, payload))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 201
    assert result.data is None
    assert "exceeded" in result.error


def test_the_error_response_body_is_bounded():
    body = json.dumps({"error": "x" * 5000}).encode("utf-8")
    result = client_for_http_error(400, body).post_once(PATH, BODY, token=TOKEN)
    assert len(result.error) == 2048


def test_response_headers_are_bounded_in_count():
    """A hostile or misbehaving proxy could hand back thousands of
    headers; MutationResponse.headers must not grow without bound just
    because the wire did."""
    many_headers = _headers(**{f"X-Extra-{i}": i for i in range(200)})
    transport = FakeTransport(_Response(201, b"{}", many_headers))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert len(result.headers) <= eveesi.MAX_MUTATION_HEADERS


def test_response_headers_are_captured_on_success():
    headers = _headers(ETag='W/"abc"')
    transport = FakeTransport(_Response(201, b'{"fitting_id": 1}', headers))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.headers.get("ETag") == 'W/"abc"'


def test_response_headers_are_captured_on_an_http_error():
    headers = _headers(Retry_After=5)
    transport = FakeTransport(_http_error(429, b'{"error":"throttled"}', headers))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.headers.get("Retry-After") == "5"


def test_a_redirect_is_never_followed_and_surfaces_as_its_real_status():
    """_NoRedirectHandler makes a real 3xx surface as an ordinary
    HTTPError rather than being followed -- post_once must report that
    3xx as a real, received response, not translate it into anything
    else."""
    transport = FakeTransport(
        _http_error(302, headers=_headers(Location="https://evil.example/"))
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 302


def test_the_access_token_is_redacted_from_the_error_text():
    token = "eyJhbGciOiJSUzI1NiJ9.super-secret-access-token.sig"
    body = json.dumps({"error": f"invalid token {token}"}).encode("utf-8")
    result = client_for_http_error(400, body).post_once(PATH, BODY, token=token)
    assert token not in result.error
    assert "[redacted]" in result.error


def test_the_access_token_is_redacted_from_a_network_error():
    token = "eyJhbGciOiJSUzI1NiJ9.super-secret-access-token.sig"

    def transport(request, timeout=None):
        raise ConnectionResetError(f"peer closed while sending {token}")

    result = eveesi.EsiClient(user_agent="A", transport=transport).post_once(
        PATH, BODY, token=token
    )
    assert token not in result.error


def test_the_access_token_never_reaches_response_headers_verbatim():
    """A hostile or misconfigured proxy echoing the request back in a
    response header (e.g. a diagnostic X-Request-Authorization) must not
    leak the bearer token into MutationResponse.headers, which is exactly
    as loggable as .error."""
    headers = _headers(X_Debug_Echo=f"Bearer {TOKEN}")
    transport = FakeTransport(_http_error(400, b'{"error":"bad request"}', headers))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert TOKEN not in "".join(result.headers.values())


def test_post_once_sends_the_bearer_token_and_json_body():
    transport = FakeTransport(_Response(201, b'{"fitting_id": 1}'))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    client.post_once(PATH, BODY, token=TOKEN)
    request = transport.requests[0]
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.data.decode("utf-8")) == BODY


def test_an_invalid_path_raises_before_any_request_is_made():
    transport = FakeTransport(_Response(201))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    try:
        client.post_once("/characters/42/fittings?x=1", BODY, token=TOKEN)
        raised = False
    except ValueError:
        raised = True
    assert raised is True
    assert transport.requests == []


def test_post_once_never_sleeps():
    """A mutation is not idempotent, so nothing about post_once should
    ever pause and retry -- confirmed by never wiring a sleep at all: if
    post_once tried to call self._sleep, the default time.sleep would
    actually block this test, which it does not."""
    transport = FakeTransport(_http_error(503))
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.status == 503


def test_a_timeout_reading_the_body_preserves_the_real_status_as_received():
    """The status line and headers already arrived before the body read
    failed -- this is a definite response with a lost body, not "no
    response at all". Without the fix, TimeoutError from response.read()
    fell through to the same handler as a connection that never answered,
    reporting response_received=False and status=None even though a real
    500 (or any other status) had already been received."""
    transport = FakeTransport(
        _ResponseThatFailsOnRead(500, TimeoutError("read timed out"))
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 500
    assert result.data is None
    assert result.error != ""


def test_an_oserror_reading_the_body_preserves_the_real_status_as_received():
    transport = FakeTransport(
        _ResponseThatFailsOnRead(201, ConnectionResetError("connection reset"))
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 201
    assert result.data is None


def test_an_incomplete_read_preserves_the_real_status_as_received():
    """http.client.IncompleteRead is raised by http.client's own
    chunked/length-based body reader and is NOT an OSError subclass (it
    subclasses http.client.HTTPException, which subclasses Exception
    directly) -- without a dedicated clause for it, this exception would
    escape post_once entirely rather than being caught by any handler,
    the exact "escapes entirely" failure mode this test guards against.
    """
    transport = FakeTransport(
        _ResponseThatFailsOnRead(201, http.client.IncompleteRead(b"partial", 10))
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=TOKEN)
    assert result.response_received is True
    assert result.status == 201
    assert result.data is None
    assert result.error != ""


def test_a_body_read_failure_message_is_redacted():
    token = "eyJhbGciOiJSUzI1NiJ9.super-secret-access-token.sig"
    transport = FakeTransport(
        _ResponseThatFailsOnRead(500, TimeoutError(f"stalled after sending {token}"))
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=token)
    assert token not in result.error
    assert "[redacted]" in result.error


def test_the_token_is_redacted_even_when_only_a_rate_limit_header_carries_it():
    """_append_rate_limit's header values are exactly as attacker/proxy-
    controlled as the response body: a hostile or misconfigured proxy
    echoing the Authorization header back into Retry-After (or an
    error-limit header) must not leak the live bearer token into
    MutationResponse.error just because the leak came from a header
    instead of the body."""
    token = "eyJhbGciOiJSUzI1NiJ9.super-secret-access-token.sig"
    headers = _headers(Retry_After=token)
    transport = FakeTransport(
        _http_error(429, json.dumps({"error": "throttled"}).encode(), headers)
    )
    client = eveesi.EsiClient(user_agent="A", transport=transport)
    result = client.post_once(PATH, BODY, token=token)
    assert token not in result.error
    assert "[redacted]" in result.error


def test_a_long_no_response_exception_message_is_bounded():
    def transport(request, timeout=None):
        raise ConnectionResetError("x" * 5000)

    result = eveesi.EsiClient(user_agent="A", transport=transport).post_once(
        PATH, BODY, token=TOKEN
    )
    assert result.response_received is False
    assert len(result.error) <= 2048


def test_a_no_response_exception_message_with_control_characters_is_sanitized():
    def transport(request, timeout=None):
        raise ConnectionResetError("reset\x00\x07 by peer\ncontinued")

    result = eveesi.EsiClient(user_agent="A", transport=transport).post_once(
        PATH, BODY, token=TOKEN
    )
    assert result.response_received is False
    assert "\x00" not in result.error
    assert "\x07" not in result.error
    assert "\n" not in result.error
