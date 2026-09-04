"""Regression: the EVE application client id has exactly one runtime
owner, `wingman.eveauth.application.CLIENT_ID`, and every authentication
primitive that touches a client id -- the authorize URL, the token
exchange, the configuration guard, and JWT validation -- reads that same
patched value.

This is the fix for a split-brain bug: `wingman.eveskills.application`
used to re-DECLARE `CLIENT_ID` and `is_configured()` rather than
re-export them, so patching the compatibility module's copy left
`sso`/`jwt` (which read `eveauth.application` directly) authorizing and
validating against the ORIGINAL, unpatched client id. Patching only the
owning module now, and asserting every one of these four surfaces agrees
with it, is what would catch that regression coming back.
"""

import base64
import json
import time
import urllib.parse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from wingman.eveauth import application, jwt, sso
from wingman.eveskills import application as eveskills_application

PATCHED_CLIENT_ID = "test-consistency-client-id"


def query_of(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    return dict(urllib.parse.parse_qsl(parsed.query, strict_parsing=True))


def form_of(request) -> dict:
    return dict(
        urllib.parse.parse_qsl(request.data.decode("ascii"), strict_parsing=True)
    )


class FakeTransport:
    """Records the request and serves a canned token response."""

    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outer = self

        class Response:
            status = 200

            def read(self, amount=None):
                return outer.body if amount is None else outer.body[:amount]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sign_jwt(private_key, payload: dict) -> str:
    header = {"alg": "RS256", "kid": "k1"}
    head_b64 = _b64(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{head_b64}.{body_b64}.{_b64(signature)}"


class _FakeKeySource:
    """The minimal `key_source` surface `jwt.validate` calls: `.keys()`."""

    def __init__(self, mapping):
        self._mapping = dict(mapping)

    def keys(self, *, force=False):
        return dict(self._mapping)


def test_authorize_url_exchange_configuration_and_jwt_all_see_one_client_id(
    monkeypatch,
):
    """One patch, on the one owning module, and every downstream surface
    agrees -- this is the property a split-brain client id would break."""
    monkeypatch.setattr(application, "CLIENT_ID", PATCHED_CLIENT_ID)

    # 1. The configuration guard, checked through BOTH the owning module
    #    and the Skills compatibility re-export -- they must be the exact
    #    same function, not two implementations that could disagree.
    assert application.is_configured() is True
    assert eveskills_application.is_configured() is True
    assert eveskills_application.is_configured is application.is_configured

    # 2. The authorize URL names the patched client id, not the one the
    #    module started with.
    pkce = sso.generate_pkce()
    url = sso.authorize_url(pkce, application.SKILLS_SCOPES)
    assert query_of(url)["client_id"] == PATCHED_CLIENT_ID

    # 3. The token exchange's POST body names the same patched client id.
    transport = FakeTransport(
        {
            "access_token": "at-value",
            "refresh_token": "rt-value",
            "expires_in": 1199,
            "token_type": "Bearer",
        }
    )
    sso.exchange_code(
        "thecode",
        "v" * 43,  # a syntactically valid PKCE verifier; not checked past shape
        transport=transport,
    )
    assert form_of(transport.requests[0])["client_id"] == PATCHED_CLIENT_ID

    # 4. A token minted for the SAME patched client id validates; jwt.py
    #    reads `client_id` from whatever the caller passes, and production
    #    callers (SkillsController) pass `application.CLIENT_ID` -- so a
    #    token minted for the id `authorize_url`/`exchange_code` just used
    #    above must be the one `validate()` accepts.
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    token = _sign_jwt(
        private_key,
        {
            "iss": "login.eveonline.com",
            "aud": ["EVE Online", PATCHED_CLIENT_ID],
            "sub": "CHARACTER:EVE:95465499",
            "name": "Test Pilot",
            "owner": "abcdefgh12345678",
            "exp": now + 1200,
            "scp": " ".join(sorted(application.SKILLS_SCOPES)),
        },
    )
    key_source = _FakeKeySource({"k1": private_key.public_key()})
    identity = jwt.validate(
        token,
        client_id=application.CLIENT_ID,
        required_scopes=application.SKILLS_SCOPES,
        key_source=key_source,
    )
    assert identity.character_id == 95465499

    # And the reverse: a token minted for a DIFFERENT client id -- as if
    # some other surface had used the pre-patch value -- must still be
    # rejected, proving this is a real audience check and not a tautology.
    stale_token = _sign_jwt(
        private_key,
        {
            "iss": "login.eveonline.com",
            "aud": ["EVE Online", "some-other-client-id"],
            "sub": "CHARACTER:EVE:95465499",
            "name": "Test Pilot",
            "owner": "abcdefgh12345678",
            "exp": now + 1200,
            "scp": " ".join(sorted(application.SKILLS_SCOPES)),
        },
    )
    try:
        jwt.validate(
            stale_token,
            client_id=application.CLIENT_ID,
            required_scopes=application.SKILLS_SCOPES,
            key_source=key_source,
        )
    except jwt.JwtError:
        pass
    else:
        raise AssertionError(
            "a token minted for a different client id must not validate "
            "against the patched CLIENT_ID"
        )
