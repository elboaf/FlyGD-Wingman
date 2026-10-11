"""Baked-in probe identity (2026-10-11, the user's explicit call).

The user weighed the credential-sharing concern and chose simplicity for
the testing phase: the shared bot's token and the guild id ship as
constants here, so every install works out of the box and the only
per-user step is picking a Discord name on the Streaming card.

The trade is explicit and accepted: anyone holding this binary holds
the token. That is fine while Wingman ships inside the corp it
belongs to; it is the thing to revisit before any wider distribution
(see the relay/proxy discussion in the Go Live memory/spec -- the
token-per-member design was already rejected; a relay is the next
shape if "other groups" ever becomes real).

These are REPLACEABLE credentials, not sacred ones: the token can be
reset in the Developer Portal and a new build cut; a leaked token
costs one portal reset, never guild access (bot permissions are only
View Channels + Connect).
"""

BAKED_BOT_TOKEN = (
    "MTU1ODU3OTg3ODY5MjEzNTAxNQ."
    "GtP4_6."
    "KV3ZYnj4AllzBZCfvZgX1zpXmtt_Fnz8aFM7IU"
)

# The FlyGD guild the shared bot watches (2026-10-11).
BAKED_GUILD_ID = "576238803824410629"
