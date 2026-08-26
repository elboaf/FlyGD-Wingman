"""EVE SSO access-token validation.

Every token in this file is signed for real, at test time, with an RSA
keypair generated in-process. That keeps the suite hermetic -- no network,
no checked-in private key, no fixture that quietly expires -- while still
exercising the same `cryptography` verify() call production uses. A test
that stubbed out signature verification would pass just as happily against
a module that never verified anything.
"""

import base64
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from wingman.eveskills import jwt as evejwt

CLIENT_ID = "9a1f7d2c4b6e48f0a3d5c7e9b1f3a5d7"

REQUIRED = ("esi-skills.read_skills.v1", "esi-skills.read_skillqueue.v1")


@pytest.fixture(scope="module")
def keypair():
    """One 2048-bit keypair for the whole module.

    Generation costs ~100ms; per-test generation would add seconds to a
    suite that is otherwise instant, and nothing here depends on a fresh
    key except the wrong-key test, which makes its own.
    """
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign(private_key, payload: dict, *, header: dict | None = None) -> str:
    """Mint a real JWT. `header` overrides the default RS256/kid header."""
    head = dict(header if header is not None else {"alg": "RS256", "kid": "k1"})
    head_b64 = b64(json.dumps(head, separators=(",", ":")).encode("utf-8"))
    body_b64 = b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{head_b64}.{body_b64}.{b64(signature)}"


def claims(**overrides) -> dict:
    now = int(time.time())
    payload = {
        "iss": "login.eveonline.com",
        "aud": ["EVE Online", CLIENT_ID],
        "sub": "CHARACTER:EVE:95465499",
        "name": "Test Pilot",
        "owner": "abcdefgh12345678",
        "exp": now + 1200,
        "scp": "esi-skills.read_skills.v1 esi-skills.read_skillqueue.v1",
    }
    payload.update(overrides)
    return payload


class FakeKeys:
    """A SigningKeySource stand-in that counts forced refreshes."""

    def __init__(self, mapping):
        self._mapping = dict(mapping)
        self.forced = 0

    def keys(self, *, force=False):
        if force:
            self.forced += 1
        return dict(self._mapping)


class ExplodingKeys:
    """Fails the test if a key is ever requested."""

    def keys(self, *, force=False):
        raise AssertionError("a key was selected before `alg` was pinned")


def validate(token, key_source, **kwargs):
    kwargs.setdefault("client_id", CLIENT_ID)
    kwargs.setdefault("required_scopes", REQUIRED)
    return evejwt.validate(token, key_source=key_source, **kwargs)


def test_rejects_blank_and_oversized_tokens():
    """Neither shape can be a JWT, and both are cheap to reject up front.

    The size cap matters more than it looks: everything below splits and
    base64-decodes the token, so an unbounded string is unbounded work
    before the first real check.
    """
    for bad in ("", "   ", "x" * (32 * 1024 + 1)):
        with pytest.raises(evejwt.JwtError):
            validate(bad, ExplodingKeys())


def test_rejects_tokens_without_exactly_three_segments():
    """Two segments is an unsigned token; four is not a JWS at all."""
    for bad in ("only-one", "two.parts", "a.b.c.d"):
        with pytest.raises(evejwt.JwtError):
            validate(bad, ExplodingKeys())


def test_alg_none_is_rejected_before_any_key_is_selected(keypair):
    """Algorithm pinning happens on the unvalidated header, first.

    ExplodingKeys asserts if a key is ever requested, so this test fails
    loudly if a future refactor moves key selection ahead of the `alg`
    check -- which is exactly the ordering that lets alg:none through.
    """
    token = sign(keypair, claims(), header={"alg": "none", "kid": "k1"})
    with pytest.raises(evejwt.JwtError, match="signing algorithm"):
        validate(token, ExplodingKeys())


def test_hs256_is_rejected_before_any_key_is_selected(keypair):
    """The HMAC-confusion shape: a token asking to be verified with a
    symmetric algorithm is rejected outright, never routed to a different
    verifier."""
    token = sign(keypair, claims(), header={"alg": "HS256", "kid": "k1"})
    with pytest.raises(evejwt.JwtError, match="signing algorithm"):
        validate(token, ExplodingKeys())


def test_missing_kid_is_rejected(keypair):
    """A token that names no key cannot be verified against a key set, and
    guessing -- trying every key -- is how a rotated-out key stays usable
    long after CCP retired it."""
    token = sign(keypair, claims(), header={"alg": "RS256"})
    with pytest.raises(evejwt.JwtError, match="signing key"):
        validate(token, ExplodingKeys())


def test_accepts_a_correctly_signed_token(keypair):
    """The happy path, verified against the real cryptography primitive."""
    token = sign(keypair, claims())
    identity = validate(token, FakeKeys({"k1": keypair.public_key()}))
    assert identity is not None


def test_rejects_a_token_signed_by_a_different_key(keypair):
    """A structurally perfect token signed by someone else's key.

    Every claim in this token is valid; only the signature is wrong. If
    verification were ever stubbed, weakened, or reordered behind the claim
    checks, this is the test that catches it.
    """
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign(impostor, claims())
    with pytest.raises(evejwt.JwtError, match="signature"):
        validate(token, FakeKeys({"k1": keypair.public_key()}))


def test_rejects_a_token_whose_payload_was_edited(keypair):
    """Tamper with the body after signing and the signature must fail.

    This is the check that makes every claim assertion below meaningful:
    without it, claim validation would be reading attacker-controlled JSON.
    """
    token = sign(keypair, claims())
    head_b64, _, sig_b64 = token.split(".")
    forged = b64(json.dumps(claims(sub="CHARACTER:EVE:1")).encode("utf-8"))
    with pytest.raises(evejwt.JwtError, match="signature"):
        validate(
            f"{head_b64}.{forged}.{sig_b64}", FakeKeys({"k1": keypair.public_key()})
        )


def test_rejects_a_signature_outside_the_base64url_alphabet(keypair):
    """urlsafe_b64decode silently discards characters it does not know, so
    the alphabet is checked before decoding -- otherwise a signature would
    decode to different bytes than it reads as."""
    head_b64, body_b64, _ = sign(keypair, claims()).split(".")
    with pytest.raises(evejwt.JwtError, match="unreadable"):
        validate(
            f"{head_b64}.{body_b64}.not*a*signature",
            FakeKeys({"k1": keypair.public_key()}),
        )


def test_a_trailing_newline_is_not_a_valid_base64url_segment(keypair):
    """`$` matches at the true end of a string AND immediately before a
    trailing newline, so a naive `re.match(r"^[A-Za-z0-9_-]*$", ...)` lets
    "abc\\n" through the alphabet guard -- `fullmatch` is what actually
    enforces "the whole segment is base64url, no exceptions"."""
    token = sign(keypair, claims())
    with pytest.raises(evejwt.JwtError, match="unreadable"):
        validate(token + "\n", FakeKeys({"k1": keypair.public_key()}))


def test_signature_covers_the_literal_segments_not_a_reserialised_payload(keypair):
    """Every other token in this file is signed with canonical JSON
    (separators=(",", ":"), no whitespace, module-default key order), so an
    implementation that decoded the payload, re-serialised it, and verified
    THAT would still pass every one of them -- by luck, since Python's
    canonical dumps happens to round-trip byte for byte. This token is
    signed with deliberately non-canonical JSON (extra whitespace, and the
    header keys in a different order) to pin down that verification runs
    against the ORIGINAL base64url segments, not a re-encoded form.
    """
    header = {"kid": "k1", "alg": "RS256"}  # reordered vs. every other fixture
    payload = claims()
    head_b64 = b64(json.dumps(header, indent=2).encode("utf-8"))
    body_b64 = b64(json.dumps(payload, indent=2).encode("utf-8"))
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = keypair.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    token = f"{head_b64}.{body_b64}.{b64(signature)}"
    identity = validate(token, FakeKeys({"k1": keypair.public_key()}))
    assert identity.character_id == 95465499


def test_unknown_kid_forces_exactly_one_refresh(keypair):
    """An unknown kid triggers one forced refresh, then a rejection.

    One, not a loop: CCP rotates keys, so a stale cache is worth a single
    retry, but a kid that stays unknown must not turn every bad token into
    repeated fetches against login.eveonline.com.
    """
    source = FakeKeys({"k1": keypair.public_key()})
    token = sign(keypair, claims(), header={"alg": "RS256", "kid": "rotated"})
    with pytest.raises(evejwt.JwtError, match="unknown key"):
        validate(token, source)
    assert source.forced == 1


def test_a_failed_forced_refresh_still_reports_an_unknown_key(keypair):
    """A network failure during the refresh must not replace the diagnosis.

    The token is unverifiable either way; reporting "unknown key" is
    accurate and actionable, while surfacing a fetch failure sends the user
    looking at their connection instead of at a rotated key.
    """

    class Flaky:
        def keys(self, *, force=False):
            if force:
                raise evejwt.JwtError("metadata fetch failed")
            return {"k1": keypair.public_key()}

    token = sign(keypair, claims(), header={"alg": "RS256", "kid": "rotated"})
    with pytest.raises(evejwt.JwtError, match="unknown key"):
        validate(token, Flaky())


@pytest.fixture
def keys(keypair):
    return FakeKeys({"k1": keypair.public_key()})


def test_accepts_every_form_of_the_issuer(keypair, keys):
    """CCP has emitted all three spellings; all three are the same issuer."""
    for issuer in (
        "https://login.eveonline.com",
        "https://login.eveonline.com/",
        "login.eveonline.com",
    ):
        identity = validate(sign(keypair, claims(iss=issuer)), keys)
        assert identity.character_id == 95465499


def test_rejects_an_unexpected_issuer(keypair, keys):
    """Not a suffix match: "login.eveonline.com.evil.test" must not pass."""
    with pytest.raises(evejwt.JwtError, match="issuer"):
        validate(
            sign(keypair, claims(iss="https://login.eveonline.com.evil.test")), keys
        )


def test_audience_is_a_conjunction_not_a_choice(keypair, keys):
    """`aud` must contain BOTH "EVE Online" AND our client id.

    CCP stamps "EVE Online" into every token it mints, for every
    application, so that value alone proves nothing about who the token was
    for. The client id alone is likewise not enough to know it came from the
    EVE issuer at all. Accepting either half on its own would accept a token
    minted for somebody else's application.
    """
    assert validate(sign(keypair, claims()), keys).character_id == 95465499
    with pytest.raises(evejwt.JwtError, match="audience"):
        validate(sign(keypair, claims(aud=["EVE Online"])), keys)
    with pytest.raises(evejwt.JwtError, match="audience"):
        validate(sign(keypair, claims(aud=[CLIENT_ID])), keys)


def test_a_string_audience_is_read_as_a_single_value(keypair, keys):
    """RFC 7519 allows a bare string, and a bare string can never satisfy
    the conjunction -- which is the correct outcome, not a crash."""
    with pytest.raises(evejwt.JwtError, match="audience"):
        validate(sign(keypair, claims(aud="EVE Online")), keys)


def test_azp_must_match_when_present_and_is_optional_when_absent(keypair, keys):
    """An absent azp is normal; a present-and-wrong azp is a different app."""
    payload = claims()
    payload.pop("azp", None)
    assert validate(sign(keypair, payload), keys).character_id == 95465499
    assert validate(sign(keypair, claims(azp=CLIENT_ID)), keys).character_id == 95465499
    with pytest.raises(evejwt.JwtError, match="different client"):
        validate(sign(keypair, claims(azp="someone-else")), keys)


def test_expiry_allows_two_minutes_of_skew(keypair, keys):
    """Desktop clocks drift. Two minutes is the ported allowance.

    `now` is injected rather than slept for, so this asserts the boundary
    exactly instead of approximately.
    """
    moment = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    expiry = int(moment.timestamp()) - 60  # expired a minute ago
    assert validate(sign(keypair, claims(exp=expiry)), keys, now=moment)
    stale = int(moment.timestamp()) - 121  # past the 120s allowance
    with pytest.raises(evejwt.JwtError, match="expired"):
        validate(sign(keypair, claims(exp=stale)), keys, now=moment)


def test_rejects_a_missing_or_non_numeric_expiry(keypair, keys):
    """A token with no expiry never expires, which is not a token we accept.

    `True` is included because bool subclasses int, and `exp: true` reading
    as 1 second past the epoch would be an expiry check that always failed
    for the wrong reason.
    """
    payload = claims()
    del payload["exp"]
    with pytest.raises(evejwt.JwtError, match="expiry"):
        validate(sign(keypair, payload), keys)
    for bad in ("soon", None, True, [1]):
        with pytest.raises(evejwt.JwtError, match="expiry"):
            validate(sign(keypair, claims(exp=bad)), keys)


def test_rejects_a_non_finite_expiry(keypair, keys):
    """json.loads("1e400") overflows to float('inf'), and `inf + skew_s <=
    now` is always False -- so without an explicit isfinite check, an
    out-of-range numeric exp would silently read as never-expiring rather
    than as the unusable value it is. NaN fails the same comparison in the
    same silent way.
    """
    for bad in (float("inf"), float("-inf"), float("nan")):
        with pytest.raises(evejwt.JwtError, match="expiry"):
            validate(sign(keypair, claims(exp=bad)), keys)


def test_nbf_allows_two_minutes_of_skew(keypair, keys):
    """EveJwtValidator.cs:120 sets ValidateLifetime = true, which checks
    notBefore against the same clock skew as expires -- a lifetime check
    the source performs that a bare `exp` check alone does not. nbf is
    optional per RFC 7519, so its absence (exercised by every other test in
    this file, none of which set it) must keep validating; only a PRESENT
    nbf beyond the skew is a rejection.
    """
    moment = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    almost_valid = int(moment.timestamp()) + 60  # a minute from now
    assert validate(sign(keypair, claims(nbf=almost_valid)), keys, now=moment)
    not_yet = int(moment.timestamp()) + 121  # past the 120s allowance
    with pytest.raises(evejwt.JwtError, match="not yet valid"):
        validate(sign(keypair, claims(nbf=not_yet)), keys, now=moment)


def test_rejects_a_non_numeric_or_non_finite_nbf(keypair, keys):
    for bad in ("soon", True, [1], float("inf"), float("nan")):
        with pytest.raises(evejwt.JwtError, match="not-before"):
            validate(sign(keypair, claims(nbf=bad)), keys)


def test_subject_must_be_a_character_subject(keypair, keys):
    """CHARACTER:EVE:<id> and nothing else.

    EVE mints subjects for corporations and other entity kinds too. A
    corporation id parsed as a character id would key the whole roster on a
    number that never matches an ESI skills response. The leading-zero and
    trailing-space cases are the ones a looser regex lets through.
    """
    for bad in (
        "CORPORATION:EVE:98000001",
        "CHARACTER:EVE:0",
        "CHARACTER:EVE:0123",
        "CHARACTER:EVE:",
        "95465499",
        "CHARACTER:EVE:95465499 ",
        "character:eve:95465499",
    ):
        with pytest.raises(evejwt.JwtError, match="character subject"):
            validate(sign(keypair, claims(sub=bad)), keys)


def test_character_id_is_bounded_to_int64(keypair, keys):
    """The regex allows up to 19 digits. EveJwtValidator.cs:76 pairs the
    same regex with long.TryParse(...) && characterId > 0, so a subject
    that overflows Int64 is rejected there. Python's arbitrary-precision
    int has no such ceiling on its own, and nothing downstream is safe to
    assume a 64-bit column the moment this guard is missing.
    """
    with pytest.raises(evejwt.JwtError, match="character subject"):
        validate(sign(keypair, claims(sub="CHARACTER:EVE:9999999999999999999")), keys)


def test_name_is_trimmed_and_bounded(keypair, keys):
    payload = claims(name="  Test Pilot  ")
    assert validate(sign(keypair, payload), keys).name == "Test Pilot"
    for bad in ("", "   ", "x" * 101):
        with pytest.raises(evejwt.JwtError, match="character name"):
            validate(sign(keypair, claims(name=bad)), keys)


def test_name_rejects_control_characters(keypair, keys):
    """A newline in a character name would break every log line and every
    single-line label the roster renders it into."""
    for bad in ("Test\nPilot", "Test\x00Pilot", "Test\x7fPilot"):
        with pytest.raises(evejwt.JwtError, match="character name"):
            validate(sign(keypair, claims(name=bad)), keys)


def test_owner_is_optional_but_bounded_when_present(keypair, keys):
    """An absent owner hash reads as "", not as a failure.

    The owner hash is how a character transfer is detected later; a token
    without one simply cannot contribute to that check, which is different
    from the token being malformed.
    """
    payload = claims()
    del payload["owner"]
    assert validate(sign(keypair, payload), keys).owner_hash == ""
    assert validate(sign(keypair, claims()), keys).owner_hash == "abcdefgh12345678"
    for bad in ("short", "x" * 257, "abcdefg\nh"):
        with pytest.raises(evejwt.JwtError, match="owner"):
            validate(sign(keypair, claims(owner=bad)), keys)


def test_scp_as_a_space_separated_string(keypair, keys):
    """The shape EVE emits for a multi-scope token today."""
    identity = validate(
        sign(
            keypair,
            claims(scp="esi-skills.read_skills.v1 esi-skills.read_skillqueue.v1"),
        ),
        keys,
    )
    assert identity.scopes == frozenset(REQUIRED)


def test_scp_as_a_json_array(keypair, keys):
    """The other shape EVE emits, and the one that breaks a naive reader.

    Running a string reader's split() over a list, or a list reader over a
    string, yields one "scope" per character -- which then fails the subset
    check with a message naming scopes that look nothing like the ones the
    token actually granted.
    """
    identity = validate(sign(keypair, claims(scp=list(REQUIRED))), keys)
    assert identity.scopes == frozenset(REQUIRED)


def test_scp_as_a_bare_string_for_a_single_scope(keypair, keys):
    """A single-scope token carries a plain string with no separator."""
    identity = evejwt.validate(
        sign(keypair, claims(scp="esi-skills.read_skills.v1")),
        client_id=CLIENT_ID,
        required_scopes=("esi-skills.read_skills.v1",),
        key_source=keys,
    )
    assert identity.scopes == frozenset({"esi-skills.read_skills.v1"})


def test_absent_scp_reads_as_no_scopes_not_as_an_error(keypair, keys):
    """A token minted with no scopes omits the claim entirely.

    Treating the absent case as malformed would reject a structurally valid
    token; it fails below on the subset check instead, which reports the
    actual problem -- missing scopes -- rather than "unreadable token".
    """
    payload = claims()
    del payload["scp"]
    with pytest.raises(evejwt.JwtError, match="missing required scopes"):
        validate(sign(keypair, payload), keys)


def test_required_scopes_are_a_subset_so_extras_are_fine(keypair, keys):
    """CCP may grant more than we asked for; that is not an error.

    Requiring equality would break the moment a user re-consents to a
    superset, or CCP widens what a scope implies.
    """
    granted = [*list(REQUIRED), "esi-characters.read_notifications.v1"]
    identity = validate(sign(keypair, claims(scp=granted)), keys)
    assert frozenset(REQUIRED) <= identity.scopes


def test_missing_scopes_are_named_in_the_message(keypair, keys):
    """The message is what the user acts on, so it names what is missing."""
    with pytest.raises(
        evejwt.JwtError, match=re.escape("esi-skills.read_skillqueue.v1")
    ):
        validate(sign(keypair, claims(scp="esi-skills.read_skills.v1")), keys)


def test_a_scope_claim_of_an_unexpected_type_is_rejected(keypair, keys):
    """A number is neither of the two shapes EVE emits, and silently
    reading it as "no scopes" would hide a response nobody understands."""
    with pytest.raises(evejwt.JwtError, match="scope claim"):
        validate(sign(keypair, claims(scp=42)), keys)


def jwks_entry(public_key, kid="k1", **overrides):
    """Serialise an RSA public key as a JWKS entry."""
    numbers = public_key.public_numbers()

    def encode(value: int) -> str:
        return b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    entry = {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "n": encode(numbers.n),
        "e": encode(numbers.e),
    }
    entry.update(overrides)
    return entry


class FakeHttp:
    """Serves canned JSON per URL and records every fetch.

    A value that is an Exception instance is raised instead of served,
    which is how the failed-refresh test takes the transport offline
    mid-run.
    """

    def __init__(self, documents):
        self.documents = dict(documents)
        self.fetched = []
        self.lock = threading.Lock()

    def __call__(self, request, timeout=None):
        url = request.full_url
        with self.lock:
            self.fetched.append(url)
        document = self.documents.get(url)
        if document is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if isinstance(document, Exception):
            raise document
        payload = json.dumps(document).encode("utf-8")

        class Response:
            def read(self, amount=None):
                return payload if amount is None else payload[:amount]

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return Response()


METADATA_URL = "https://login.eveonline.com/.well-known/oauth-authorization-server"
JWKS_URL = "https://login.eveonline.com/oauth/jwks"


def metadata(**overrides):
    document = {"issuer": "https://login.eveonline.com", "jwks_uri": JWKS_URL}
    document.update(overrides)
    return document


class FakeClock:
    def __init__(self, start=None):
        self.moment = start or datetime(2026, 8, 24, 12, 0, tzinfo=UTC)

    def __call__(self):
        return self.moment

    def advance(self, seconds):
        self.moment = self.moment + timedelta(seconds=seconds)


def test_key_source_fetches_metadata_then_jwks(keypair):
    """Two hops, in order: the metadata document names the JWKS address."""
    http = FakeHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]},
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    assert list(source.keys()) == ["k1"]
    assert http.fetched == [METADATA_URL, JWKS_URL]


def test_keys_are_cached_for_five_minutes(keypair):
    """One fetch pair per TTL window, not one per token validated."""
    clock = FakeClock()
    http = FakeHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]},
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=clock)
    source.keys()
    clock.advance(299)
    source.keys()
    assert len(http.fetched) == 2
    clock.advance(2)
    source.keys()
    assert len(http.fetched) == 4


def test_force_refetches_inside_the_ttl(keypair):
    """The unknown-kid path needs a way past a cache that is still fresh."""
    clock = FakeClock()
    http = FakeHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]},
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=clock)
    source.keys()
    source.keys(force=True)
    assert len(http.fetched) == 4


def test_a_failed_refresh_leaves_the_previous_keys_usable(keypair):
    """The cache is replaced only on a fully successful fetch.

    This is the difference between "one request failed" and "this process
    can no longer validate anything". The forced refresh below raises, and
    the next non-forced call must still hand back the keys already held.
    """
    clock = FakeClock()
    http = FakeHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]},
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=clock)
    assert list(source.keys()) == ["k1"]
    http.documents[METADATA_URL] = urllib.error.URLError("offline")
    with pytest.raises(evejwt.JwtError):
        source.keys(force=True)
    assert list(source.keys()) == ["k1"]


def test_rejects_metadata_with_an_unexpected_issuer(keypair):
    """And never fetches the JWKS the bad document named."""
    http = FakeHttp(
        {
            METADATA_URL: metadata(issuer="https://evil.test"),
            JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]},
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="issuer"):
        source.keys()
    assert http.fetched == [METADATA_URL]


def test_rejects_a_jwks_uri_that_is_not_absolute_https_on_the_sso_host():
    """The metadata document is the one input allowed to name a URL whose
    contents this process then trusts. A relative, plaintext, or off-host
    jwks_uri is precisely how that becomes key substitution -- and the
    third case below is why the host check is not a suffix match."""
    for bad in (
        "/oauth/jwks",
        "http://login.eveonline.com/oauth/jwks",
        "https://login.eveonline.com.evil.test/oauth/jwks",
        "https://evil.test/oauth/jwks",
        "not a url",
        "",
    ):
        http = FakeHttp({METADATA_URL: metadata(jwks_uri=bad)})
        source = evejwt.SigningKeySource(transport=http, now=FakeClock())
        with pytest.raises(evejwt.JwtError, match="JWKS address"):
            source.keys()


def test_filters_jwks_to_rsa_signing_keys_with_a_kid(keypair):
    """Non-RSA keys, encryption keys, and keyless entries are dropped here.

    Dropping at load time rather than at lookup is what makes a kid naming a
    non-RSA key a REJECTION and never a fallback: the key is simply absent
    from the map, and validate() reports an unknown key.
    """
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    http = FakeHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {
                "keys": [
                    {
                        "kty": "EC",
                        "use": "sig",
                        "kid": "ec-key",
                        "crv": "P-256",
                        "x": "AAAA",
                        "y": "AAAA",
                    },
                    jwks_entry(other.public_key(), kid="enc-key", use="enc"),
                    jwks_entry(other.public_key(), kid="  "),
                    "not-even-an-object",
                    jwks_entry(keypair.public_key(), kid="k1"),
                ]
            },
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    assert list(source.keys()) == ["k1"]


def test_a_kid_naming_a_non_rsa_key_is_rejected_never_a_fallback(keypair):
    """End to end: the token names the EC entry, and validation fails with
    "unknown key" rather than quietly verifying against the RSA one."""
    http = FakeHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {
                "keys": [
                    {
                        "kty": "EC",
                        "use": "sig",
                        "kid": "ec-key",
                        "crv": "P-256",
                        "x": "AAAA",
                        "y": "AAAA",
                    },
                    jwks_entry(keypair.public_key(), kid="k1"),
                ]
            },
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    token = sign(keypair, claims(), header={"alg": "RS256", "kid": "ec-key"})
    with pytest.raises(evejwt.JwtError, match="unknown key"):
        validate(token, source)


def test_an_entry_without_use_is_still_accepted(keypair):
    """`use` is optional in a JWKS, and absent means unrestricted.
    Requiring it would reject a perfectly valid key set."""
    entry = jwks_entry(keypair.public_key())
    del entry["use"]
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: {"keys": [entry]}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    assert list(source.keys()) == ["k1"]


def test_an_empty_key_set_is_a_failure_not_an_empty_cache():
    """Caching an empty set would fail every token for the next 5 minutes,
    long after whatever caused it had gone away."""
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: {"keys": []}})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="no usable signing keys"):
        source.keys()


def test_a_non_object_key_document_is_rejected():
    http = FakeHttp({METADATA_URL: metadata(), JWKS_URL: ["k1"]})
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="unreadable key set"):
        source.keys()


def test_an_http_failure_on_the_metadata_fetch_is_reported(keypair):
    http = FakeHttp({})  # every URL 404s
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    with pytest.raises(evejwt.JwtError, match="404"):
        source.keys()


# --- Mandatory correction 1: no-redirect opener on both fetches ------------
#
# The metadata and JWKS fetches decide which keys this process will trust.
# A followed redirect on either one hands that decision to a host the
# metadata document never named and the host-pin check in _load() never
# got to see -- verifying a token against attacker-supplied keys defeats
# signature verification completely. Ported from esi.py's own pair of
# tests (test_the_default_opener_refuses_redirects and
# test_a_cross_host_redirect_does_not_leak_the_authorization_header),
# which this pair is modelled on line for line.


def test_the_default_opener_refuses_redirects():
    """Guards _default_transport's actual wiring, not just _NoRedirectHandler
    in isolation -- every other test in this file injects a fake transport,
    so nothing else would catch a refactor that rebuilt _opener without the
    no-redirect handler (which would then silently follow a Location header
    to a host the metadata document never named)."""
    names = [type(h).__name__ for h in evejwt._opener.handlers]
    assert "HTTPRedirectHandler" not in names
    assert "_NoRedirectHandler" in names


def test_a_redirect_does_not_relocate_key_trust():
    """The property that actually matters: _NoRedirectHandler.redirect_request
    must return None for a 302, on either the metadata or the JWKS hop --
    that None is what makes urllib raise the 302 as an ordinary HTTPError
    instead of building and sending a follow-up request to wherever
    Location points. Calling redirect_request directly (rather than
    spinning a real HTTP server) tests the exact method the stdlib itself
    calls to decide whether to forward the request, without depending on
    network timing or ports -- so this test cannot rot into one that
    passes merely because no redirect ever arrives in practice.
    """
    handler = evejwt._NoRedirectHandler()
    request = urllib.request.Request(METADATA_URL)
    redirect_headers = {}
    result = handler.redirect_request(
        request, None, 302, "Found", redirect_headers, "https://evil.test/oauth/jwks"
    )
    assert result is None


# --- Mandatory correction 2: coalesced forced refreshes --------------------
#
# EveSigningKeySource.cs:34,40,70 carries a version counter so a burst of
# concurrent unknown-kid validations -- exactly what a live CCP key
# rotation produces, with every character refreshing at once -- performs
# ONE shared fetch rather than one per waiting thread. A single-caller test
# cannot tell a coalesced implementation apart from one that simply fetches
# every time it is asked; only concurrent callers can.


def test_concurrent_forced_refreshes_share_a_single_fetch(keypair):
    """N threads all observe an unknown kid at once and all call
    keys(force=True). Only the first to acquire the lock should actually
    fetch; the rest, arriving after that fetch bumped the version, must
    see their own force request already satisfied and reuse its result.

    This has to be deterministic, not merely likely: a fixed sleep before
    releasing the winner's blocked fetch is a race by construction -- a
    descheduled thread that has not yet queued behind the lock when the
    sleep ends will read the POST-bump version, see it equal its own
    observed_version, and refetch, which is a false failure that teaches
    people to re-run rather than investigate.

    `_HandoffLock` below removes the guesswork. `keys()` reads
    `observed_version = self._version` and only THEN touches the lock, so
    a thread that has reached the lock at all has -- in its own program
    order, on its own thread -- already done that read. The wrapper lets
    exactly one thread (whichever wins the real, non-blocking acquire)
    through as the winner, and sends every other thread through
    `queued.wait()` before it is allowed to make the real, blocking
    acquire call. The test's own `queued.wait()` call is the barrier's
    final party, so it returns only once all 7 losers have arrived -- which
    is to say, only once all 7 have themselves already read
    observed_version and found the lock held. Only then is the winner's
    blocked fetch released. No timing assumption is left standing.
    """
    release = threading.Event()
    release.set()  # pre-released: the warm-up fetch below must not block

    class SlowHttp(FakeHttp):
        def __call__(self, request, timeout=None):
            if request.full_url == JWKS_URL:
                release.wait(timeout=5)
            return super().__call__(request, timeout=timeout)

    http = SlowHttp(
        {
            METADATA_URL: metadata(),
            JWKS_URL: {"keys": [jwks_entry(keypair.public_key())]},
        }
    )
    source = evejwt.SigningKeySource(transport=http, now=FakeClock())
    source.keys()  # warm the cache so every thread below is a forced refresh
    http.fetched.clear()
    release.clear()  # now arm the gate for the actual concurrency test

    real_lock = source._lock
    queued = threading.Barrier(8)  # the 7 losers, plus this thread's own wait()

    class _HandoffLock:
        def __enter__(self):
            if real_lock.acquire(blocking=False):
                return self
            queued.wait(timeout=5)
            real_lock.acquire()
            return self

        def __exit__(self, *exc):
            real_lock.release()
            return False

    source._lock = _HandoffLock()

    results = []

    def worker():
        results.append(source.keys(force=True))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    queued.wait(timeout=5)  # returns only once every loser has queued
    release.set()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 8
    assert all(list(result) == ["k1"] for result in results)
    # One metadata fetch and one JWKS fetch, not eight of each.
    assert http.fetched.count(METADATA_URL) == 1
    assert http.fetched.count(JWKS_URL) == 1
