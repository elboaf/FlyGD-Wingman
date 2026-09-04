"""Compatibility re-export: EVE SSO access-token validation now lives in
`wingman.eveauth.jwt`. Shared with Fittings -- both capabilities'
access tokens are the same EVE SSO JWTs, validated by the identical
signature and claim checks regardless of which scopes they carry.

Every name below is imported explicitly, including the underscore-
prefixed `_opener`/`_NoRedirectHandler` -- test_eveskills_jwt.py asserts
on both directly, and a bare `from ..eveauth.jwt import *` would drop
them.
"""

from ..eveauth.jwt import (
    CLOCK_SKEW_S,
    JWKS_TTL_S,
    MAX_JWKS_BYTES,
    MAX_METADATA_BYTES,
    MAX_TOKEN_CHARS,
    TIMEOUT_S,
    EveIdentity,
    JwtError,
    SigningKeySource,
    _NoRedirectHandler,
    _opener,
    validate,
)

__all__ = [
    "CLOCK_SKEW_S",
    "JWKS_TTL_S",
    "MAX_JWKS_BYTES",
    "MAX_METADATA_BYTES",
    "MAX_TOKEN_CHARS",
    "TIMEOUT_S",
    "EveIdentity",
    "JwtError",
    "SigningKeySource",
    "_NoRedirectHandler",
    "_opener",
    "validate",
]
