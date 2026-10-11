"""Build-time probe identity (2026-10-11, the user's explicit call).

The shared bot's token and the guild id do NOT live in the source tree:
they are placeholders here, rewritten by the build chain
(.github/actions/build-installer/action.yml) from the repository
secrets DISCORD_BOT_TOKEN and DISCORD_GUILD_ID, the same way
wingman/credentials.py's OAuth placeholders are. Every release install
works out of the box and the only per-user step is picking a Discord
name on the Streaming card; running from source (and CI's pytest,
which never imports this file) sees only the placeholders.

The trade is explicit and accepted: anyone holding a release binary
holds the token. That is fine while Wingman ships inside the corp it
belongs to; it is the thing to revisit before any wider distribution
(see the relay/proxy discussion in the Go Live memory/spec -- the
token-per-member design was already rejected; a relay is the next
shape if "other groups" ever becomes real).

These are REPLACEABLE credentials, not sacred ones: the token can be
reset in the Developer Portal and the secret updated; a leaked token
costs one portal reset, never guild access (bot permissions are only
View Channels + Connect).
"""

BAKED_BOT_TOKEN = "REPLACE_AT_BUILD_TIME"

# The FlyGD guild the shared bot watches.
BAKED_GUILD_ID = "REPLACE_AT_BUILD_TIME"


def is_placeholder() -> bool:
    """True when running from source without real identity injected.

    The build chain does a literal string replace of the placeholder
    text across the whole file, including the right-hand side of the
    two constants above. So comparing a constant against a literal
    placeholder would still be true in a release build (both sides
    substituted) and false-negatives the check.

    Instead assemble the sentinel at runtime from fragments that never
    appear contiguously in this file's source text. The build chain's
    substring replace can only rewrite a literal, unbroken match, so it
    cannot touch a value built from separate fragments joined at
    runtime -- the sentinel stays fixed while the constants change
    underneath it in a real build.
    """
    sentinel = "REPLACE" + "_AT_BUILD" + "_TIME"
    return sentinel == BAKED_BOT_TOKEN
