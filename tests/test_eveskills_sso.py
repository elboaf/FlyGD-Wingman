"""EVE SSO: PKCE, the authorize URL, and the token endpoint.

No network anywhere in this file. The token endpoint is exercised through
the injected transport seam, the same shape discord.py uses.
"""

import inspect
import io
import json
import urllib.error
import urllib.parse

import pytest

from obs_youtube_uploader.eveskills import application, sso

# RFC 7636 Appendix B, verbatim. These 32 octets encode to the verifier
# below, whose ASCII bytes hash to the challenge below. Any drift in the
# encoding, the hash input, or the padding shows up here immediately.
RFC7636_OCTETS = bytes(
    [
        116,
        24,
        223,
        180,
        151,
        153,
        224,
        37,
        79,
        250,
        96,
        125,
        216,
        173,
        187,
        186,
        22,
        212,
        37,
        77,
        105,
        214,
        191,
        240,
        91,
        88,
        5,
        88,
        83,
        132,
        141,
        121,
    ]
)
RFC7636_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC7636_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_pkce_matches_the_rfc_7636_s256_vector():
    """S256 hashes the ASCII bytes of the ENCODED verifier.

    Hashing the raw 32 random bytes instead produces a challenge the server
    cannot reproduce, and the only symptom is invalid_grant at the token
    endpoint -- a failure that reads as a bad code, not as a bad challenge.
    The published vector is the cheapest possible way to pin this.
    """
    pkce = sso.generate_pkce(randbytes=lambda count: RFC7636_OCTETS[:count])
    assert pkce.verifier == RFC7636_VERIFIER
    assert pkce.challenge == RFC7636_CHALLENGE


def test_pkce_draws_thirty_two_bytes_each_for_state_and_verifier():
    """Two independent draws, 32 bytes apiece."""
    drawn = []

    def randbytes(count):
        drawn.append(count)
        return bytes([len(drawn)]) * count

    pkce = sso.generate_pkce(randbytes=randbytes)
    assert drawn == [32, 32]
    assert pkce.state != pkce.verifier


def test_pkce_values_are_base64url_without_padding():
    """Padding would need escaping in the URL and is not part of S256."""
    pkce = sso.generate_pkce()
    for value in (pkce.state, pkce.verifier, pkce.challenge):
        assert "=" not in value and "+" not in value and "/" not in value
        assert len(value) == 43  # 32 bytes, unpadded


def test_generate_pkce_is_random_by_default():
    """The production default must actually draw fresh entropy."""
    assert sso.generate_pkce().state != sso.generate_pkce().state


def query_of(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    # strict_parsing so a malformed pair is an error rather than a silent
    # drop, plus an explicit duplicate check parse_qsl would hide.
    pairs = urllib.parse.parse_qsl(parsed.query, strict_parsing=True)
    assert len(pairs) == len(dict(pairs)), "authorize URL had a duplicate key"
    return dict(pairs)


def test_authorize_url_carries_every_required_parameter():
    pkce = sso.generate_pkce()
    url = sso.authorize_url(pkce)
    assert url.startswith(application.SSO_AUTHORIZE + "?")
    assert query_of(url) == {
        "response_type": "code",
        "redirect_uri": application.REDIRECT_URI,
        "client_id": application.CLIENT_ID,
        "scope": " ".join(sorted(application.SCOPES)),
        "state": pkce.state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
    }


def test_authorize_url_encodes_every_key_and_value():
    """The redirect URI carries "://" and "/", and the scope list carries
    spaces. Left raw, the query would end at the first character CCP's
    parser disagreed about -- and a truncated redirect_uri is a rejected
    authorization, not a visible error."""
    url = sso.authorize_url(sso.generate_pkce())
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A51779%2Fcallback%2F" in url
    assert " " not in url


def test_authorize_url_sorts_the_scopes():
    """A stable order keeps the URL reproducible and the consent screen
    identical between runs."""
    scope = query_of(sso.authorize_url(sso.generate_pkce()))["scope"]
    assert scope == " ".join(sorted(scope.split(" ")))


def test_no_client_secret_appears_anywhere():
    """This is a PUBLIC client: it ships to end users, so any secret baked
    into the binary would be readable by everyone holding it and would
    protect nothing at all. PKCE is what stands in for one."""
    source = inspect.getsource(sso)
    assert "client_secret" not in source
    assert "Authorization" not in source


VERIFIER = RFC7636_VERIFIER

GOOD = {
    "access_token": "at-value",
    "refresh_token": "rt-value",
    "expires_in": 1199,
    "token_type": "Bearer",
}


class FakeTransport:
    """Records the request and serves a canned JSON body."""

    def __init__(self, payload, status=200):
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outer = self

        class Response:
            status = outer.status

            def read(self, amount=None):
                return outer.body if amount is None else outer.body[:amount]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


def error_transport(status, payload):
    """A transport that raises HTTPError, the way urllib does on a non-2xx."""
    body = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload

    def transport(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, status, "Error", {}, io.BytesIO(body)
        )

    return transport


def form_of(request) -> dict:
    return dict(
        urllib.parse.parse_qsl(request.data.decode("ascii"), strict_parsing=True)
    )


def test_exchange_code_posts_the_authorization_code_grant():
    transport = FakeTransport(GOOD)
    tokens = sso.exchange_code("thecode", VERIFIER, transport=transport)
    request = transport.requests[0]
    assert request.full_url == application.SSO_TOKEN
    assert request.get_method() == "POST"
    assert form_of(request) == {
        "grant_type": "authorization_code",
        "code": "thecode",
        "client_id": application.CLIENT_ID,
        "code_verifier": VERIFIER,
        "redirect_uri": application.REDIRECT_URI,
    }
    assert tokens == sso.TokenSet("at-value", "rt-value", 1199)


def test_refresh_token_posts_the_refresh_grant():
    transport = FakeTransport(GOOD)
    tokens = sso.refresh_token("rt-old", transport=transport)
    assert form_of(transport.requests[0]) == {
        "grant_type": "refresh_token",
        "refresh_token": "rt-old",
        "client_id": application.CLIENT_ID,
    }
    assert tokens.access_token == "at-value"


def test_the_request_is_form_encoded_and_carries_the_user_agent():
    """CCP asks every client to identify itself, and the token endpoint only
    accepts form encoding."""
    transport = FakeTransport(GOOD)
    sso.refresh_token("rt-old", transport=transport)
    headers = {
        key.lower(): value for key, value in transport.requests[0].header_items()
    }
    assert headers["content-type"] == "application/x-www-form-urlencoded"
    assert headers["user-agent"] == application.USER_AGENT


def test_refresh_token_may_omit_a_new_refresh_token():
    """EVE sometimes answers a refresh without reissuing one.

    Treating that as a failure would force a re-authentication out of a
    perfectly normal response. The caller keeps the token it already holds,
    which is why "" is a valid value here and not an error.
    """
    payload = dict(GOOD)
    del payload["refresh_token"]
    tokens = sso.refresh_token("rt-old", transport=FakeTransport(payload))
    assert tokens.refresh_token == ""


def test_exchange_code_requires_a_refresh_token():
    """A code exchange with no refresh token yields a session that dies in
    twenty minutes with nothing stored to recover it."""
    payload = dict(GOOD)
    del payload["refresh_token"]
    with pytest.raises(sso.OAuthError, match="no refresh token"):
        sso.exchange_code("thecode", VERIFIER, transport=FakeTransport(payload))


def test_rejects_a_blank_or_oversized_access_token():
    for value in ("", "   ", "x" * (32 * 1024 + 1)):
        payload = dict(GOOD, access_token=value)
        with pytest.raises(sso.OAuthError, match="access token"):
            sso.refresh_token("rt", transport=FakeTransport(payload))


def test_rejects_an_oversized_refresh_token():
    """The token is about to be encrypted and written to disk; an unbounded
    one is an unbounded state file."""
    payload = dict(GOOD, refresh_token="x" * 2049)
    with pytest.raises(sso.OAuthError, match="refresh token"):
        sso.refresh_token("rt", transport=FakeTransport(payload))


def test_rejects_a_response_refresh_token_containing_a_nul():
    """The local-input NUL guard on the token this module SENDS has a twin
    on the token EVE SENDS BACK: both are about to be encrypted and written
    to disk, and a NUL surviving either path corrupts that state file the
    same way."""
    payload = dict(GOOD, refresh_token="rt-val\0ue")
    with pytest.raises(sso.OAuthError, match="refresh token"):
        sso.refresh_token("rt", transport=FakeTransport(payload))


def test_rejects_an_out_of_range_lifetime():
    """0 means already expired and a day-plus means something is wrong with
    the response -- and either would be stored as a refresh deadline.

    `True` is in the list because bool subclasses int, and `expires_in: true`
    would otherwise read as one second.
    """
    for value in (0, -1, 86_401, "1199", True, None):
        payload = dict(GOOD, expires_in=value)
        with pytest.raises(sso.OAuthError, match="token lifetime"):
            sso.refresh_token("rt", transport=FakeTransport(payload))


def test_token_type_is_compared_case_insensitively():
    """CCP has spelled it both ways, and the header this produces is
    identical either way."""
    for value in ("Bearer", "bearer", "BEARER"):
        payload = dict(GOOD, token_type=value)
        assert sso.refresh_token("rt", transport=FakeTransport(payload))
    with pytest.raises(sso.OAuthError, match="token type"):
        sso.refresh_token("rt", transport=FakeTransport(dict(GOOD, token_type="MAC")))


def test_rejects_a_non_json_body():
    """A proxy's HTML error page arrives with a 200 often enough to matter."""

    def transport(request, timeout=None):
        class Response:
            status = 200

            def read(self, amount=None):
                return b"<html>gateway</html>"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()

    with pytest.raises(sso.OAuthError, match="invalid token response"):
        sso.refresh_token("rt", transport=transport)


def test_rejects_a_json_body_that_is_not_an_object():
    """Every hop below would raise AttributeError on a list, and this runs
    on the path where that would replace the real diagnosis."""
    with pytest.raises(sso.OAuthError, match="invalid token response"):
        sso.refresh_token("rt", transport=FakeTransport(["at-value"]))


def test_rejects_inputs_before_they_reach_the_wire():
    """A blank code or a malformed verifier is a local bug, and sending it
    would spend a round trip to be told so."""
    unused = FakeTransport(GOOD)
    with pytest.raises(sso.OAuthError):
        sso.exchange_code("", VERIFIER, transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.exchange_code("code", "short", transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.exchange_code("code", "!" * 50, transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.refresh_token("", transport=unused)
    with pytest.raises(sso.OAuthError):
        sso.refresh_token("rt\0value", transport=unused)
    assert unused.requests == []


def _transport_that_must_not_be_called(request, timeout=None):
    """A transport that fails the test outright if the guard it's paired
    with let anything reach the wire -- stricter than merely recording the
    call, since an assertion after the fact could be skipped by an earlier
    unrelated failure."""
    pytest.fail("a locally-invalid input reached the transport")


def test_rejects_a_whitespace_only_code():
    """`not code` alone (bare truthiness) is False for "   ", so a
    whitespace-only code would sail through to the wire -- reproducing
    EveSso.cs:83's IsNullOrWhiteSpace(code) guard is what catches it here
    instead, at the cost of a round trip this check exists to avoid."""
    with pytest.raises(sso.OAuthError, match="authorization code"):
        sso.exchange_code("   ", VERIFIER, transport=_transport_that_must_not_be_called)


def test_rejects_a_whitespace_only_refresh_token():
    """Same reasoning as the whitespace-only code, for the stored refresh
    token: EveSso.cs:105 rejects it with IsNullOrWhiteSpace, and a bare
    truthiness check here would not."""
    with pytest.raises(sso.OAuthError, match="refresh token"):
        sso.refresh_token("   ", transport=_transport_that_must_not_be_called)


def test_definitive_codes_are_exactly_the_three():
    """The split drives the UI: a definitive failure clears the stored token
    and shows a re-authenticate banner, while a transient one leaves
    last-good data on screen. Widening this set logs users out over a bad
    gateway; narrowing it leaves a dead token retrying forever."""
    for code in ("invalid_grant", "identity_mismatch", "owner_changed"):
        assert sso.OAuthError(400, code, "x").definitive is True
    for code in (
        "invalid_request",
        "server_error",
        "temporarily_unavailable",
        "network",
        "oauth_error",
        "invalid_response",
        "",
    ):
        assert sso.OAuthError(500, code, "x").definitive is False


def test_an_invalid_grant_response_is_classified_definitive():
    """The revoked-refresh-token case, end to end."""
    transport = error_transport(
        400, {"error": "invalid_grant", "error_description": "token revoked"}
    )
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "invalid_grant"
    assert caught.value.status == 400
    assert caught.value.definitive is True


def test_a_server_error_is_transient():
    """CCP's 5xx must not cost the user their stored token."""
    transport = error_transport(503, {"error": "server_error"})
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.definitive is False


def test_a_network_failure_is_transient_and_carries_no_status():
    def transport(request, timeout=None):
        raise urllib.error.URLError("offline")

    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "network"
    assert caught.value.status == 0
    assert caught.value.definitive is False


def test_an_unparseable_error_body_falls_back_to_oauth_error():
    """A gateway HTML page is still a failure, just not a classified one --
    and an unclassified failure is transient, which is the safe default."""
    transport = error_transport(502, b"<html>bad gateway</html>")
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "oauth_error"
    assert caught.value.definitive is False


def test_a_hostile_error_code_cannot_reach_the_message():
    """The error code goes into a user-visible message, so it passes through
    the same [A-Za-z0-9_-] filter the callback error does. A body controlled
    by whatever answered the request must not carry markup or a newline into
    the UI -- and because the filtered value no longer equals the literal,
    it is NOT definitive either: a hostile body cannot log the user out."""
    transport = error_transport(
        400, {"error": "<script>alert(1)</script>\ninvalid_grant"}
    )
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert "<" not in caught.value.code and "\n" not in caught.value.code
    assert "<" not in str(caught.value)
    assert caught.value.definitive is False


def test_an_error_code_of_the_wrong_json_type_is_neutered():
    """`{"error": {"code": "invalid_grant"}}` is not a string; every hop is
    type-checked rather than trusted, because this runs on the failure path
    where a TypeError would replace the real diagnosis."""
    transport = error_transport(400, {"error": {"code": "invalid_grant"}})
    with pytest.raises(sso.OAuthError) as caught:
        sso.refresh_token("rt-old", transport=transport)
    assert caught.value.code == "oauth_error"


def test_an_oauth_error_message_is_readable():
    """The status and the code both appear, because the pair is what a bug
    report needs and neither alone identifies the failure."""
    transport = error_transport(400, {"error": "invalid_grant"})
    with pytest.raises(sso.OAuthError, match=r"400.*invalid_grant"):
        sso.refresh_token("rt-old", transport=transport)


def test_default_transport_refuses_redirects():
    """Same seam and same reasoning as esi.py and jwt.py: the POST body
    carries the authorization code or the refresh token, and a 3xx would let
    anything sitting in front of login.eveonline.com have urllib resend that
    credential to wherever Location points. Calling the stdlib decision
    point directly, with no server, pins the handler itself rather than the
    request that happens to trigger it."""
    handler = sso._NoRedirectHandler()
    assert (
        handler.redirect_request(
            None, None, 302, "Found", {}, "https://attacker.example/steal"
        )
        is None
    )
