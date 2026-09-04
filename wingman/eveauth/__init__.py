"""Shared EVE SSO authentication primitives.

Everything in this package is capability-agnostic: it authenticates a
character against CCP's servers and validates the token that comes back,
and it has no notion of what the caller intends to do with that token
afterwards. Skills (read-only skill and skill-queue data) and Fittings
(read and write fitting data) are the two capabilities that exist today;
both authenticate through this package and neither imports the other.

`application.py` is the one place a capability's scope set is looked up
(`CAPABILITY_SCOPES[SKILLS]`, `CAPABILITY_SCOPES[FITTINGS]`) and the one
place that says there is no "all scopes" default: `sso.authorize_url`
requires its caller to name an explicit scope set, always.

`wingman.eveskills.{application,dpapi,tokens,jwt,loopback,sso}` re-export
this package's public names for backward compatibility; new code should
import from here directly.
"""

from .application import FITTINGS, SKILLS, FULL_AUTH_CAPABILITIES, FULL_AUTH_SCOPES
from .controller import (
    AccessTokenResult,
    AuthorityCharacter,
    AuthorityController,
    CharacterParticipant,
    LifecycleLease,
    MutationResult,
)

__all__ = [
    "FITTINGS",
    "SKILLS",
    "FULL_AUTH_CAPABILITIES",
    "FULL_AUTH_SCOPES",
    "AccessTokenResult",
    "AuthorityCharacter",
    "AuthorityController",
    "CharacterParticipant",
    "LifecycleLease",
    "MutationResult",
]
