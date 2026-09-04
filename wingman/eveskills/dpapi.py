"""Compatibility re-export: DPAPI wrapping now lives in
`wingman.eveauth.dpapi`. Shared with Fittings, which stores its own ESI
refresh token the same way Skills does -- nothing here was ever
Skills-specific.

Every name below is imported explicitly, including the underscore-
prefixed `_crypt32`/`_kernel32` -- test_eveskills_dpapi.py asserts on
their `lru_cache` identity directly, and a bare
`from ..eveauth.dpapi import *` would drop both, since Python's wildcard
import skips underscore-prefixed names by default.
"""

from ..eveauth.dpapi import (
    DATA_BLOB,
    _crypt32,
    _kernel32,
    available,
    protect,
    unprotect,
)

__all__ = [
    "DATA_BLOB",
    "_crypt32",
    "_kernel32",
    "available",
    "protect",
    "unprotect",
]
