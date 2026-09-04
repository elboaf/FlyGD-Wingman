"""Compatibility re-export: EVE application identity now lives in
`wingman.eveauth.application`, which owns it because Fittings
authenticates against the same CCP application and shares the redirect,
the PKCE flow, and the JWT validator.

Every name below, INCLUDING `CLIENT_ID` and `is_configured`, is the exact
same object as its `eveauth.application` original -- there is no local
re-declaration and no second `is_configured()` implementation. An earlier
version of this module re-declared both so that monkeypatching
`wingman.eveskills.application.CLIENT_ID` would still drive its own
`is_configured()`; that made `eveauth.application` and this module two
independent sources of truth for the same client id, and nothing forced
them to agree. `wingman.eveskills.controller` (the only production
consumer that used to read `CLIENT_ID` through this module) now imports
`wingman.eveauth.application` directly instead, and every test that
configures or resets the client id patches that same owning module --
see test_eveskills_paths.py and test_eveskills_controller.py's
`build_auth`. Patching `CLIENT_ID` here would therefore patch a name
nothing production reads any more; there is exactly one runtime owner,
and this module is a pure alias to it.

`SCOPES` is the one deliberate exception: Skills' own read-only pair,
preserved as the exact ordered tuple every existing external caller and
test already reads. `eveauth.application.SKILLS_SCOPES` is the same two
scopes as an (order-agnostic) `frozenset`, shared with the capability
lookup `CAPABILITY_SCOPES` uses; this tuple is a literal, not derived
from it, so its exact tuple identity is not itself a promise -- only the
two scopes it contains.
"""

from ..eveauth.application import (
    ACCEPTED_ISSUERS,
    CLIENT_ID,
    ESI_BASE,
    ESI_COMPATIBILITY_DATE,
    ESI_HOST,
    REDIRECT_HOST,
    REDIRECT_PATH,
    REDIRECT_PORT,
    REDIRECT_URI,
    SSO_AUTHORIZE,
    SSO_HOST,
    SSO_METADATA,
    SSO_TOKEN,
    USER_AGENT,
    is_configured,
)

SCOPES = (
    "esi-skills.read_skills.v1",
    "esi-skills.read_skillqueue.v1",
)

__all__ = [
    "ACCEPTED_ISSUERS",
    "CLIENT_ID",
    "ESI_BASE",
    "ESI_COMPATIBILITY_DATE",
    "ESI_HOST",
    "REDIRECT_HOST",
    "REDIRECT_PATH",
    "REDIRECT_PORT",
    "REDIRECT_URI",
    "SCOPES",
    "SSO_AUTHORIZE",
    "SSO_HOST",
    "SSO_METADATA",
    "SSO_TOKEN",
    "USER_AGENT",
    "is_configured",
]
