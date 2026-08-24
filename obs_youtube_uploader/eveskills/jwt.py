"""EVE SSO access-token validation: claim checks plus an RS256 signature.

Signature verification runs against `cryptography`, which this application
already ships. google-auth depends on it unconditionally (uv.lock:382-387)
and 50.0.0 is bundled into every release today, so verification here is ten
lines against an audited implementation rather than a hand-rolled RSA
primitive -- see EveJwtValidator.cs, which this module ports.
"""
import base64
import binascii
import json
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

from . import application

CLOCK_SKEW_S = 120
JWKS_TTL_S = 300

MAX_TOKEN_CHARS = 32 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_JWKS_BYTES = 256 * 1024
TIMEOUT_S = 20.0

# The one algorithm this module will ever verify. See validate() for why the
# check sits where it does.
_ALGORITHM = "RS256"

_CHARACTER_SUBJECT = re.compile(r"^CHARACTER:EVE:([1-9][0-9]{0,18})$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]*$")


class JwtError(Exception):
    """Any reason an access token was not accepted."""


@dataclass(frozen=True)
class EveIdentity:
    character_id: int
    name: str
    owner_hash: str
    scopes: frozenset[str]


def _b64url_decode(segment: str) -> bytes:
    """Decode one base64url segment, rejecting anything outside the alphabet.

    base64.urlsafe_b64decode is lenient about characters it does not
    recognise -- it discards them -- so the alphabet is checked here first.
    A segment that decodes to different bytes than it reads as is exactly
    the ambiguity signature verification exists to remove.
    """
    if not _B64URL.match(segment):
        raise JwtError("EVE SSO returned an unreadable access token.")
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, binascii.Error) as exc:
        raise JwtError("EVE SSO returned an unreadable access token.") from exc


def _decode_json_segment(segment: str) -> dict:
    try:
        parsed = json.loads(_b64url_decode(segment).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise JwtError("EVE SSO returned an unreadable access token.") from exc
    if not isinstance(parsed, dict):
        raise JwtError("EVE SSO returned an unreadable access token.")
    return parsed


def validate(token: str, *, client_id: str,
             required_scopes: Iterable[str],
             key_source,
             now: datetime | None = None,
             skew_s: int = CLOCK_SKEW_S) -> EveIdentity:
    """Validate an EVE SSO access token and return the identity it carries.

    Raises JwtError for every rejection; there is no partial success.
    """
    if not isinstance(token, str) or not token.strip():
        raise JwtError("EVE SSO returned an invalid access token.")
    if len(token) > MAX_TOKEN_CHARS:
        # Bounded before the split: everything below decodes segments, and
        # an unbounded string is unbounded work ahead of the first check.
        raise JwtError("EVE SSO returned an invalid access token.")
    pieces = token.split(".")
    if len(pieces) != 3:
        raise JwtError("EVE SSO returned an unreadable access token.")
    head_b64, body_b64, sig_b64 = pieces

    header = _decode_json_segment(head_b64)
    # Algorithm pinning, on the UNVALIDATED header, BEFORE a key is chosen.
    # The ordering is not incidental: reading `alg` after picking a key is
    # precisely what lets alg:none through, because by then something has
    # already decided how to verify.
    #
    # Pinning is not the whole HMAC-confusion defence either. The real
    # defence is structural: nothing below dispatches on the token's own
    # `alg` to select a verifier or a key type. There is ONE path, it is
    # RSA/PKCS#1v1.5/SHA-256, and a token asking for anything else is
    # rejected rather than routed.
    if header.get("alg") != _ALGORITHM:
        raise JwtError("EVE SSO access token used an unexpected signing algorithm.")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid.strip():
        # No kid means no key selection. Trying every key instead would keep
        # a rotated-out key usable long after CCP retired it.
        raise JwtError("EVE SSO access token did not name a signing key.")

    keys = key_source.keys()
    if kid not in keys:
        # Exactly one forced refresh on an unknown kid: CCP rotates, and the
        # cache may simply be stale. A refresh that itself fails is swallowed
        # so the previous keys stay in play and the rejection below reports
        # "unknown key" rather than surfacing a fetch failure -- the token is
        # unverifiable either way, and the accurate message is the useful one.
        try:
            keys = key_source.keys(force=True)
        except JwtError:
            pass
    public_key = keys.get(kid)
    if public_key is None:
        raise JwtError("EVE SSO access token was signed by an unknown key.")

    # PKCS#1 v1.5 with SHA-256 is what RS256 means. `cryptography` raises
    # InvalidSignature and nothing else for a bad signature, so the except
    # clause is deliberately narrow: any other error type here would mean a
    # malformed key object, which must not be swallowed as "bad signature".
    signing_input = f"{head_b64}.{body_b64}".encode("ascii")
    signature = _b64url_decode(sig_b64)
    try:
        public_key.verify(signature, signing_input,
                           padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise JwtError("EVE SSO access token failed signature verification.") from exc

    claims = _decode_json_segment(body_b64)
    return _read_claims(claims, client_id=client_id,
                         required_scopes=required_scopes,
                         now=now, skew_s=skew_s)


def _is_control(character: str) -> bool:
    # Unicode category Cc is exactly C0 (0x00-0x1F) plus DEL and C1
    # (0x7F-0x9F) -- the same set the ported implementation rejected.
    return unicodedata.category(character) == "Cc"


def _read_claims(claims: dict, *, client_id, required_scopes, now, skew_s) -> EveIdentity:
    issuer = claims.get("iss")
    # Membership in a fixed set, deliberately not a suffix match:
    # "login.eveonline.com.evil.test" must not pass.
    if not isinstance(issuer, str) or issuer not in application.ACCEPTED_ISSUERS:
        raise JwtError("EVE SSO access token came from an unexpected issuer.")

    # The audience is a CONJUNCTION, not a choice. CCP stamps the literal
    # "EVE Online" into every token it mints for every application, so that
    # value alone says nothing about who the token was for; the client id is
    # what makes it OURS. Accepting either half alone accepts a token minted
    # for somebody else's application.
    audiences = claims.get("aud")
    if isinstance(audiences, str):
        # RFC 7519 allows a bare string. It can never satisfy the
        # conjunction, but reading it as a list of characters would be a
        # much stranger failure than reading it as one value.
        audiences = [audiences]
    if not isinstance(audiences, list):
        raise JwtError("EVE SSO access token was issued for a different audience.")
    present = {value for value in audiences if isinstance(value, str)}
    if "EVE Online" not in present or client_id not in present:
        raise JwtError("EVE SSO access token was issued for a different audience.")

    authorized_party = claims.get("azp")
    if authorized_party is not None and authorized_party != client_id:
        raise JwtError("EVE SSO access token was authorized to a different client.")

    expiry = claims.get("exp")
    # bool is an int subclass, and `exp: true` must not read as one second
    # past the epoch.
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
        raise JwtError("EVE SSO access token had no usable expiry.")
    moment = now or datetime.now(timezone.utc)
    if expiry + skew_s <= moment.timestamp():
        raise JwtError("EVE SSO access token has expired.")

    subject = claims.get("sub")
    match = _CHARACTER_SUBJECT.match(subject) if isinstance(subject, str) else None
    if match is None:
        # EVE mints subjects for corporations and other entity kinds too. A
        # corporation id parsed as a character id would key the roster on a
        # number no ESI skills response will ever match.
        raise JwtError("EVE SSO access token had an invalid character subject.")
    character_id = int(match.group(1))

    raw_name = claims.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    if not 1 <= len(name) <= 100 or any(_is_control(ch) for ch in name):
        # A newline here would break every log line and every single-line
        # label the roster renders the name into.
        raise JwtError("EVE SSO access token had an invalid character name.")

    raw_owner = claims.get("owner")
    if raw_owner is None:
        # Absent is normal, not a failure: the owner hash only contributes
        # to the character-transfer check, and a token without one simply
        # cannot contribute to it.
        owner_hash = ""
    else:
        owner_hash = raw_owner.strip() if isinstance(raw_owner, str) else ""
        if not 8 <= len(owner_hash) <= 256 or any(_is_control(ch) for ch in owner_hash):
            raise JwtError("EVE SSO access token had an invalid owner claim.")

    granted = _read_scopes(claims.get("scp"))
    missing = sorted(scope for scope in required_scopes if scope not in granted)
    if missing:
        # Named, because the message is what the user acts on.
        raise JwtError("EVE SSO access token is missing required scopes: "
                        + ", ".join(missing) + ".")

    return EveIdentity(character_id=character_id, name=name,
                        owner_hash=owner_hash, scopes=frozenset(granted))


def _read_scopes(raw: object) -> frozenset[str]:
    """Read `scp` in all three shapes EVE emits.

    A single-scope token carries a bare string, a multi-scope token carries
    either a space-separated string or a JSON array, and a token minted with
    no scopes omits the claim. All three are valid responses, so none of
    them may raise.

    The failure this guards against is not hypothetical: reading a string
    with a list reader (or the reverse) yields one "scope" per character,
    and the resulting message names scopes that look nothing like what the
    token granted.
    """
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        # split() with no argument collapses runs of whitespace and drops
        # empties, which covers both the single-scope and separated forms.
        return frozenset(raw.split())
    if isinstance(raw, list):
        return frozenset(item.strip() for item in raw
                          if isinstance(item, str) and item.strip())
    # Neither shape. Reading this as "no scopes" would hide a response
    # nobody understands behind a plausible-looking permissions error.
    raise JwtError("EVE SSO access token had an unreadable scope claim.")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects on the metadata and JWKS fetches.

    Both of these responses decide which keys this process will trust. A
    redirect on either would let anything sitting in front of
    login.eveonline.com relocate that decision to a host the scheme-and-host
    pin in `_load` never gets to see -- urllib's default
    HTTPRedirectHandler.redirect_request() carries the request across the
    redirect with no same-origin check on Location, so without this handler
    a metadata document that never named a rogue host could still end up
    having this process fetch, cache, and verify tokens against that host's
    keys. Returning None here tells urllib "don't redirect"; the 3xx then
    surfaces as an ordinary HTTPError, exactly like any other non-2xx
    status. Ported whole from discord.py:175-197 / esi.py's own copy, for
    the identical reason.
    """

    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


# Module-level so every call shares one opener, matching discord.py's and
# esi.py's _opener -- and so a test can assert on _opener.handlers directly
# rather than only on _NoRedirectHandler in isolation.
_opener = urllib.request.build_opener(_NoRedirectHandler)


def _default_transport(request, timeout=None):
    return _opener.open(request, timeout=timeout)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rsa_signing_key(entry: object):
    """Select one JWKS entry as (kid, RSAPublicKey), or None to drop it.

    Filtering here rather than at lookup time is what makes a kid naming a
    non-RSA key a rejection and never a fallback: an unusable entry is
    simply absent from the map, and validate() reports an unknown key.
    """
    if not isinstance(entry, dict):
        return None
    if entry.get("kty") != "RSA":
        return None
    use = entry.get("use")
    # `use` is optional in a JWKS; absent means unrestricted. Only an
    # explicit non-"sig" value disqualifies an entry.
    if use is not None and use != "sig":
        return None
    kid = entry.get("kid")
    if not isinstance(kid, str) or not kid.strip():
        return None
    modulus, exponent = entry.get("n"), entry.get("e")
    if not isinstance(modulus, str) or not isinstance(exponent, str):
        return None
    try:
        n = int.from_bytes(_b64url_decode(modulus), "big")
        e = int.from_bytes(_b64url_decode(exponent), "big")
    except JwtError:
        return None
    if n <= 0 or e <= 0:
        return None
    try:
        return kid, RSAPublicNumbers(e, n).public_key()
    except ValueError:
        # cryptography rejects malformed key parameters (an even exponent,
        # an implausible modulus). Dropping just this entry is right: the
        # rest of the key set is still perfectly usable.
        return None


class SigningKeySource:
    """Fetches and caches EVE's JWKS signing keys.

    `_version` (EveSigningKeySource.cs's `_refreshVersion`) is what turns a
    burst of concurrent forced refreshes into one shared fetch instead of
    one per caller. A live CCP key rotation is exactly that burst: every
    character mid-session hits an unknown kid within moments of each other
    and calls `keys(force=True)`. Without the version check, each of those
    calls -- serialized behind the lock, but still individually -- would
    refetch after acquiring it, hammering login.eveonline.com N times for
    one rotation. With it, a caller that observes the version bump while it
    was waiting for the lock knows somebody else already did the refresh it
    wanted, and reuses that result instead of doing its own.
    """

    def __init__(self, *, transport=_default_transport, now=_utcnow,
                 ttl_s: int = JWKS_TTL_S) -> None:
        self._transport = transport
        self._now = now
        self._ttl_s = ttl_s
        # Refreshes happen on worker threads; the lock keeps a burst of
        # unknown-kid refreshes from becoming a burst of concurrent fetches.
        self._lock = threading.Lock()
        self._keys: dict[str, object] = {}
        self._expires: datetime | None = None
        self._version = 0

    def keys(self, *, force: bool = False) -> dict[str, object]:
        # Read outside the lock, before waiting for it -- matching
        # EveSigningKeySource.cs:40, which captures `observedVersion` before
        # `await _gate.WaitAsync(...)`. This is what lets a caller tell "no
        # one has refreshed since I decided I needed one" apart from "someone
        # already did the refresh I was about to duplicate".
        observed_version = self._version

        with self._lock:
            moment = self._now()
            fresh = bool(self._keys) and self._expires is not None and self._expires > moment
            if fresh and not force:
                return dict(self._keys)
            if force and self._keys and self._version != observed_version:
                # Someone else refreshed while this call waited for the
                # lock. Their result already satisfies this caller's forced
                # request, and fetching again would only hammer CCP's
                # endpoint for the same rotation.
                return dict(self._keys)
            # The cache is replaced ONLY on a fully successful load. _load
            # raises before either assignment, so a metadata blip, a bad
            # issuer, or an empty JWKS all leave the previous keys in place
            # and usable -- the difference between "one request failed" and
            # "this process can no longer validate anything".
            loaded = self._load()
            self._keys = loaded
            self._expires = moment + timedelta(seconds=self._ttl_s)
            self._version += 1
            # A copy, so a caller mutating the result cannot poison the
            # cache for every later validation.
            return dict(self._keys)

    def _load(self) -> dict[str, object]:
        document = self._fetch_json(application.SSO_METADATA, MAX_METADATA_BYTES)
        if not isinstance(document, dict):
            raise JwtError("EVE SSO metadata was not a JSON object.")
        issuer = document.get("issuer")
        if not isinstance(issuer, str) or issuer not in application.ACCEPTED_ISSUERS:
            # Checked before the JWKS fetch, so a hostile metadata document
            # never gets to make a second request happen at all.
            raise JwtError("EVE SSO metadata returned an unexpected issuer.")
        jwks_uri = document.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise JwtError("EVE SSO metadata returned an unexpected JWKS address.")
        parsed = urlparse(jwks_uri)
        # Absolute HTTPS on the SSO host, and an equality check rather than
        # a suffix match: the metadata document is the one input allowed to
        # name a URL whose contents this process then trusts, and a
        # relative, plaintext, or off-host value is exactly how that becomes
        # key substitution.
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.hostname.lower() != application.SSO_HOST):
            raise JwtError("EVE SSO metadata returned an unexpected JWKS address.")

        key_set = self._fetch_json(jwks_uri, MAX_JWKS_BYTES)
        entries = key_set.get("keys") if isinstance(key_set, dict) else None
        if not isinstance(entries, list):
            raise JwtError("EVE SSO returned an unreadable key set.")
        keys: dict[str, object] = {}
        for entry in entries:
            selected = _rsa_signing_key(entry)
            if selected is not None:
                keys[selected[0]] = selected[1]
        if not keys:
            # Caching an empty set would fail every token for a full TTL.
            raise JwtError("EVE SSO returned no usable signing keys.")
        return keys

    def _fetch_json(self, url: str, limit: int) -> object:
        request = urllib.request.Request(
            url, headers={"User-agent": application.USER_AGENT,
                           "Accept": "application/json"},
            method="GET")
        try:
            with self._transport(request, timeout=TIMEOUT_S) as response:
                # limit + 1 so an oversized body is detected rather than
                # silently truncated into something that still parses.
                raw = response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            raise JwtError(f"EVE SSO key fetch returned {exc.code}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise JwtError("EVE SSO key fetch could not reach "
                            f"{application.SSO_HOST}.") from exc
        if len(raw) > limit:
            raise JwtError("EVE SSO response exceeded the configured limit.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise JwtError("EVE SSO returned an unreadable key document.") from exc
