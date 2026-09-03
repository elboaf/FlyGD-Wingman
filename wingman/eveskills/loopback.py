"""Compatibility re-export: the OAuth loopback listener now lives in
`wingman.eveauth.loopback`. Shared with Fittings -- the callback that
serves EVE's redirect is identical regardless of which capability's
consent screen the user just completed.
"""

from ..eveauth.loopback import (
    AUTH_TIMEOUT_S,
    CONNECTION_TIMEOUT_S,
    MAX_HEADER_BYTES,
    MAX_LINE_BYTES,
    MAX_QUERY_KEY_CHARS,
    MAX_QUERY_VALUE_CHARS,
    Callback,
    CallbackCancelled,
    CallbackTimeout,
    LoopbackListener,
    parse_request,
    safe_oauth_code,
)

__all__ = [
    "AUTH_TIMEOUT_S",
    "CONNECTION_TIMEOUT_S",
    "MAX_HEADER_BYTES",
    "MAX_LINE_BYTES",
    "MAX_QUERY_KEY_CHARS",
    "MAX_QUERY_VALUE_CHARS",
    "Callback",
    "CallbackCancelled",
    "CallbackTimeout",
    "LoopbackListener",
    "parse_request",
    "safe_oauth_code",
]
