"""Compatibility re-export: EVE SSO PKCE, the authorize URL, and the
token endpoint now live in `wingman.eveauth.sso`. Shared with Fittings,
which authenticates through this exact flow with its own scope set.

`authorize_url` keeps the signature `eveauth.sso` gives it: `scopes` is a
required argument with no default. A Skills caller passes
`application.SCOPES` (this module's own two-scope tuple) explicitly,
exactly as a Fittings caller passes its own scopes -- there is no
capability-specific wrapper here that would let one narrow request leak
back in as an implicit default for the other.

Every name below is imported explicitly, including the underscore-
prefixed `_NoRedirectHandler` -- test_eveskills_sso.py asserts on it
directly.
"""

from ..eveauth.sso import (
    MAX_ACCESS_TOKEN_CHARS,
    MAX_CODE_CHARS,
    MAX_EXPIRES_IN_S,
    MAX_REFRESH_TOKEN_CHARS,
    MAX_TOKEN_RESPONSE_BYTES,
    TIMEOUT_S,
    OAuthError,
    Pkce,
    TokenSet,
    _NoRedirectHandler,
    authorize_url,
    exchange_code,
    generate_pkce,
    refresh_token,
)

__all__ = [
    "MAX_ACCESS_TOKEN_CHARS",
    "MAX_CODE_CHARS",
    "MAX_EXPIRES_IN_S",
    "MAX_REFRESH_TOKEN_CHARS",
    "MAX_TOKEN_RESPONSE_BYTES",
    "TIMEOUT_S",
    "OAuthError",
    "Pkce",
    "TokenSet",
    "_NoRedirectHandler",
    "authorize_url",
    "exchange_code",
    "generate_pkce",
    "refresh_token",
]
