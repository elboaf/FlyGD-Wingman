"""EVE SSO: PKCE generation, the authorize URL, and the token endpoint.

There is no client secret in this module, and there must never be one. The
EVE application is registered as a PUBLIC client: it ships to end users, so
a secret compiled into it would be readable by everyone holding the binary
and would protect exactly nothing. PKCE is what stands in for it, which is
why the verifier checks below are not cosmetic.
"""
import base64
import hashlib
import json
import os
import string
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import application
from .loopback import safe_oauth_code

MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
MAX_ACCESS_TOKEN_CHARS = 32 * 1024
MAX_REFRESH_TOKEN_CHARS = 2048
MAX_CODE_CHARS = 2048
MAX_EXPIRES_IN_S = 86_400
TIMEOUT_S = 20.0

# Failures meaning the stored grant is gone for good. Anything else -- 5xx,
# a network drop, an unfamiliar OAuth code -- is transient, and the split is
# what decides whether the roster row shows a re-authenticate banner or just
# an error with last-good data still visible.
_DEFINITIVE = frozenset({"invalid_grant", "identity_mismatch", "owner_changed"})

# RFC 7636's unreserved set for the code verifier.
_VERIFIER_CHARS = frozenset(string.ascii_letters + string.digits + "-._~")


@dataclass(frozen=True)
class Pkce:
    state: str
    verifier: str
    challenge: str


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int


class OAuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def definitive(self) -> bool:
        """True when re-authenticating is the only way forward.

        Widening this set logs users out over a bad gateway; narrowing it
        leaves a dead token retrying forever.
        """
        return self.code in _DEFINITIVE


def _b64url(raw: bytes) -> str:
    # Unpadded: "=" would need escaping in the URL, and S256 is defined over
    # the unpadded form.
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pkce(*, randbytes=os.urandom) -> Pkce:
    """Mint a fresh state, verifier, and S256 challenge."""
    state = _b64url(randbytes(32))
    verifier = _b64url(randbytes(32))
    # RFC 7636 S256 hashes the ASCII bytes of the ENCODED verifier, not the
    # random bytes behind it. Hashing the raw entropy instead produces a
    # challenge the server cannot reproduce, and the only symptom is
    # invalid_grant at the token endpoint -- which reads as a bad code, not
    # as a bad challenge, and costs an afternoon to find.
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return Pkce(state=state, verifier=verifier, challenge=challenge)


def authorize_url(pkce: Pkce) -> str:
    """Build the URL the browser is sent to."""
    query = {
        "response_type": "code",
        "redirect_uri": application.REDIRECT_URI,
        "client_id": application.CLIENT_ID,
        # Sorted, for a reproducible URL and an identical consent screen
        # between runs.
        "scope": " ".join(sorted(application.SCOPES)),
        "state": pkce.state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
    }
    # safe="" so that ":" and "/" in the redirect URI and the spaces in the
    # scope list are all escaped. Left raw, the query would end at the first
    # character CCP's parser disagreed about, and a truncated redirect_uri
    # is a rejected authorization rather than a visible error.
    encoded = "&".join(
        f"{urllib.parse.quote(key, safe='')}={urllib.parse.quote(value, safe='')}"
        for key, value in query.items())
    return f"{application.SSO_AUTHORIZE}?{encoded}"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on the token endpoint.

    The POST body carries the authorization code or the refresh token. A 3xx
    would let anything sitting in front of login.eveonline.com have urllib
    resend that credential to wherever the Location header points. Same seam
    and same reasoning as esi.py and jwt.py, ported from discord.py:175-197.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def exchange_code(code: str, verifier: str, *,
                  transport=_default_transport) -> TokenSet:
    """Trade an authorization code for a token set."""
    # Checked locally: sending a blank code or a malformed verifier spends a
    # round trip to be told about a bug that is entirely on this side.
    # Whitespace-aware (not code.strip()) so a whitespace-only code -- not
    # code, but not a usable one either -- is caught here, matching
    # EveSso.cs:83's IsNullOrWhiteSpace(code). A bare truthiness check
    # would let "   " sail through and spend the very round trip this
    # guard exists to avoid.
    if not code.strip() or len(code) > MAX_CODE_CHARS or "\0" in code:
        raise OAuthError(0, "invalid_request", "The authorization code was invalid.")
    if not 43 <= len(verifier) <= 128 or any(ch not in _VERIFIER_CHARS for ch in verifier):
        raise OAuthError(0, "invalid_request", "The PKCE verifier was invalid.")
    payload = _post_token({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": application.CLIENT_ID,
        "code_verifier": verifier,
        "redirect_uri": application.REDIRECT_URI,
    }, transport)
    return _read_token_set(payload, require_refresh_token=True)


def refresh_token(token: str, *, transport=_default_transport) -> TokenSet:
    """Trade a stored refresh token for a fresh token set."""
    # Whitespace-aware for the same reason as exchange_code's code guard:
    # EveSso.cs:105 rejects a whitespace-only refresh token with
    # IsNullOrWhiteSpace, and `not token` alone would let "   " through to
    # the wire.
    if not token.strip() or len(token) > MAX_REFRESH_TOKEN_CHARS or "\0" in token:
        raise OAuthError(0, "invalid_request", "The stored refresh token was invalid.")
    payload = _post_token({
        "grant_type": "refresh_token",
        "refresh_token": token,
        "client_id": application.CLIENT_ID,
    }, transport)
    return _read_token_set(payload, require_refresh_token=False)


def _post_token(form: dict, transport) -> dict:
    body = urllib.parse.urlencode(form).encode("ascii")
    request = urllib.request.Request(
        application.SSO_TOKEN, data=body,
        headers={"Content-type": "application/x-www-form-urlencoded",
                 "Accept": "application/json",
                 "User-agent": application.USER_AGENT},
        method="POST")
    try:
        with transport(request, timeout=TIMEOUT_S) as response:
            # limit + 1 so an oversized body is detected rather than
            # silently truncated into something that still parses.
            raw = response.read(MAX_TOKEN_RESPONSE_BYTES + 1)
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        # Unlike discord.py, this path DOES read a non-2xx body: the OAuth
        # error code lives in it, and the definitive/transient split -- which
        # decides whether the user is told to re-authenticate -- has nowhere
        # else to come from. Everything read here goes through
        # safe_oauth_code before it can reach a message.
        detail = b""
        try:
            detail = exc.read(MAX_TOKEN_RESPONSE_BYTES + 1)
        except OSError:
            pass
        code = _read_error_code(detail)
        raise OAuthError(exc.code, code,
                         f"EVE SSO token request returned {exc.code} ({code}).") from exc
    except (urllib.error.URLError, OSError) as exc:
        # Transient by construction: the code is not in _DEFINITIVE, so a
        # flaky connection can never cost the user their stored token.
        raise OAuthError(0, "network", "EVE SSO could not be reached.") from exc

    if len(raw) > MAX_TOKEN_RESPONSE_BYTES:
        raise OAuthError(status, "invalid_response",
                         "EVE SSO returned an invalid token response.")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise OAuthError(status, "invalid_response",
                         "EVE SSO returned an invalid token response.") from exc
    if not isinstance(parsed, dict):
        # Every hop below would raise AttributeError on a list, and this is
        # the failure path, where that would replace the real diagnosis with
        # a type error.
        raise OAuthError(status, "invalid_response",
                         "EVE SSO returned an invalid token response.")
    return parsed


def _read_error_code(detail: bytes) -> str:
    """Pull the OAuth error code out of a non-2xx body, safely.

    The body is written by whatever answered the request, so the value goes
    through the same [A-Za-z0-9_-] filter the callback error does before it
    can reach a message. A filtered value that no longer equals a literal in
    _DEFINITIVE is therefore transient, which is the safe direction: a
    hostile body cannot log the user out.
    """
    try:
        parsed = json.loads(detail.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "oauth_error"
    if not isinstance(parsed, dict):
        return "oauth_error"
    return safe_oauth_code(parsed.get("error"))


def _read_token_set(payload: dict, *, require_refresh_token: bool) -> TokenSet:
    access = payload.get("access_token")
    if (not isinstance(access, str) or not access.strip()
            or len(access) > MAX_ACCESS_TOKEN_CHARS):
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an invalid access token.")

    refresh = payload.get("refresh_token", "")
    if refresh is None:
        refresh = ""
    if (not isinstance(refresh, str) or len(refresh) > MAX_REFRESH_TOKEN_CHARS
            or "\0" in refresh):
        # Bounded because this is about to be encrypted and written to disk.
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an invalid refresh token.")
    # Required on a code exchange, OPTIONAL on a refresh. EVE sometimes
    # answers a refresh without reissuing one and expects the caller to keep
    # the token it already holds; demanding one here would turn a perfectly
    # normal response into a forced re-authentication.
    if require_refresh_token and not refresh.strip():
        raise OAuthError(200, "invalid_response", "EVE SSO returned no refresh token.")

    expires = payload.get("expires_in")
    # bool is an int subclass, and `expires_in: true` must not read as 1.
    if (isinstance(expires, bool) or not isinstance(expires, int)
            or not 0 < expires <= MAX_EXPIRES_IN_S):
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an invalid token lifetime.")

    token_type = payload.get("token_type")
    # Case-insensitive: CCP has spelled it both ways, and the bearer-auth
    # header the caller builds from it is identical either way.
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise OAuthError(200, "invalid_response",
                         "EVE SSO returned an unexpected token type.")

    return TokenSet(access_token=access, refresh_token=refresh, expires_in=expires)
