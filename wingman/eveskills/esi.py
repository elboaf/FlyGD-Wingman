"""Compatibility re-export: Skills' ESI client now lives in `wingman.eveesi`.

Nothing here writes to ESI on Skills' behalf -- the two scopes Skills
requests are read-only, and the only POST Skills makes is the
unauthenticated universe/ids lookup. `post_once` and `MutationResponse`
exist for Fittings; re-exporting them here changes nothing Skills calls,
but keeps this module a complete mirror of `eveesi` rather than a
hand-picked subset that would silently fall behind it.

Every name below is imported explicitly, including the underscore-
prefixed ones test_eveskills_esi.py asserts on directly (`_opener`,
`_NoRedirectHandler`) -- a bare `from .eveesi import *` would drop those,
since Python's wildcard import skips underscore-prefixed names by
default.
"""

from ..eveesi import (
    BASE_BACKOFF_S,
    MAX_ATTEMPTS,
    MAX_BACKOFF_S,
    MAX_ERROR_BODY_BYTES,
    MAX_SUCCESS_BODY_BYTES,
    NETWORK_BACKOFF_S,
    RETRY_STATUSES,
    TIMEOUT_S,
    EsiClient,
    EsiResponse,
    MutationResponse,
    _NoRedirectHandler,
    _opener,
    application,
    validate_path,
)

__all__ = [
    "BASE_BACKOFF_S",
    "MAX_ATTEMPTS",
    "MAX_BACKOFF_S",
    "MAX_ERROR_BODY_BYTES",
    "MAX_SUCCESS_BODY_BYTES",
    "NETWORK_BACKOFF_S",
    "RETRY_STATUSES",
    "TIMEOUT_S",
    "EsiClient",
    "EsiResponse",
    "MutationResponse",
    "_NoRedirectHandler",
    "_opener",
    "application",
    "validate_path",
]
