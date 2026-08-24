"""EVE application identity: client id, redirect, scopes, endpoints.

The client id is a plain source constant, not a build-time injected
value, matching TriffView's EveApplication.cs:12. EVE's flow is PKCE
public-client -- client_id only, no secret -- so there is no
confidentiality argument for injection the way there is for the Google
desktop secret that release.yml:78-90 injects.

What that costs is recorded rather than glossed: a source checkout and a
release share one identity in CCP's dashboard, a fork inherits Wingman's
name on its users' consent screens unless it edits one line, and a
revocation for abuse from any of them takes every release together. If
any of that becomes real, the fix is to move this one constant to
build-time injection alongside the Google one. This module exists to be
that single point.
"""
from .. import __version__ as _version

# Not yet registered at developers.eveonline.com. is_configured() is
# what keeps a placeholder build from launching a browser at CCP with
# this literal in the query string -- the resulting error page is not a
# recognisable diagnosis for "this build was never registered".
_PLACEHOLDER_CLIENT_ID = "REPLACE_WITH_REGISTERED_EVE_CLIENT_ID"

CLIENT_ID = _PLACEHOLDER_CLIENT_ID

# The redirect is registered with CCP and must match byte for byte, so
# the parts and the assembled URI are kept in one place: loopback.py
# validates the request's Host and path against these same constants,
# and a hand-written URI that drifted would fail our own listener rather
# than the redirect.
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 51779
REDIRECT_PATH = "/callback/"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

# 51779 sits clear of TriffView's 51777 so both applications can be
# installed together. There is deliberately no fallback port: the URI is
# registered, so binding elsewhere would produce a redirect CCP refuses.
# A bind failure is reported plainly instead.

# Read-only, and exactly two. Widening this tuple widens the consent
# screen every user sees; nothing in this subsystem writes to ESI.
SCOPES = (
    "esi-skills.read_skills.v1",
    "esi-skills.read_skillqueue.v1",
)

# CCP asks third-party clients to identify themselves. Matches the shape
# discord.py:169-170 already sends, for the same reason: an anonymous
# agent is what gets an application throttled without warning.
USER_AGENT = (f"FlyGD-Wingman/{_version} "
              "(+https://github.com/elboaf/FlyGD-Wingman)")

SSO_AUTHORIZE = "https://login.eveonline.com/v2/oauth/authorize"
SSO_TOKEN = "https://login.eveonline.com/v2/oauth/token"
SSO_METADATA = (
    "https://login.eveonline.com/.well-known/oauth-authorization-server")
SSO_HOST = "login.eveonline.com"

# All three spellings are accepted, matching TriffView's own set
# (EveJwtValidator.cs:12-15): the bare authority, the full origin, and
# the full origin with a trailing slash -- OAuth issuer identifiers
# routinely appear with and without the trailing slash. jwt.py compares
# the `iss` claim against this set by equality and nothing else, so a
# missing spelling is not a near-miss: it is a rejected token and a
# character that can never authenticate.
ACCEPTED_ISSUERS = frozenset({
    "login.eveonline.com",
    "https://login.eveonline.com",
    "https://login.eveonline.com/",
})

ESI_BASE = "https://esi.evetech.net"
ESI_HOST = "esi.evetech.net"
# Pinned, as in the source. A stale value degrades to whatever ESI
# decides rather than failing loudly, which is why it is a named
# constant a reader can find rather than a literal in a header dict.
ESI_COMPATIBILITY_DATE = "2026-08-12"


def is_configured() -> bool:
    """True once a real client id has replaced the placeholder."""
    return bool(CLIENT_ID) and CLIENT_ID != _PLACEHOLDER_CLIENT_ID
