"""Compatibility re-export: EVE application identity now lives in
`wingman.eveauth.application`, which owns it because Fittings
authenticates against the same CCP application and shares the redirect,
the PKCE flow, and the JWT validator.

`CLIENT_ID`, `SCOPES`, and `is_configured()` are re-declared here rather
than merely imported, because both production code and tests reach them
as `wingman.eveskills.application.<name>` and monkeypatch `CLIENT_ID`
through that same qualified name (see test_eveskills_paths.py and
test_eveskills_controller.py's `build_auth`). `is_configured()` reads
`CLIENT_ID` as a bare module global, resolved through whichever module
it is DEFINED in -- a function merely imported from `eveauth.application`
would keep reading that module's own `CLIENT_ID`, silently ignoring a
patch made here. Re-declaring both, with `is_configured()`'s body
unchanged, is what keeps that monkeypatch working exactly as it did
before this extraction.

`SCOPES` is Skills' own read-only pair, preserved as the exact ordered
tuple every existing caller and test already reads -- `eveauth.
application.SKILLS_SCOPES` is the same two scopes as an (order-agnostic)
`frozenset`, shared with the capability lookup `CAPABILITY_SCOPES` uses;
this tuple is the one Skills has always exposed and is not derived from
it, so the exact tuple identity below is not itself a promise, only the
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
)

_PLACEHOLDER_CLIENT_ID = "REPLACE_WITH_REGISTERED_EVE_CLIENT_ID"

SCOPES = (
    "esi-skills.read_skills.v1",
    "esi-skills.read_skillqueue.v1",
)


def is_configured() -> bool:
    """True once a real client id has replaced the placeholder.

    Re-declared, not re-exported: see the module docstring for why this
    module's OWN `CLIENT_ID` global -- not `eveauth.application`'s -- is
    what must drive this check for existing monkeypatch-based tests to
    keep working unchanged.
    """
    return bool(CLIENT_ID) and CLIENT_ID != _PLACEHOLDER_CLIENT_ID


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
