"""One-time setup for the Go Live probe (#335) — interactive, run by hand.

Asks for three things, does everything else:
  1. the bot token (paste; it is validated against Discord, then stored
     DPAPI-protected — never printed, never written to settings)
  2. which guild (auto-detected when the bot is in exactly one)
  3. which member is you (picked from the member list)

Then writes the identity into Wingman's settings and runs ONE real
probe to prove the loop can see the stream state. Run from the repo:

    uv run --no-sync python scripts/probe_setup.py
"""

import json
import sys
import urllib.request

REPO = __file__.rsplit("\\scripts", 1)[0] if "\\scripts" in __file__ else "."
sys.path.insert(0, REPO)

from wingman import settings  # noqa: E402
from wingman.streaming.probe import probe_live_state  # noqa: E402
from wingman.streaming.probebot import (  # noqa: E402
    BotTokenStore,
    validate_token_format,
)

API = "https://discord.com/api/v10"
SSL = {"https": __import__("ssl")._create_unverified_context()}  # schannel-free box


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bot " + token})
    return json.load(urllib.request.urlopen(req, timeout=15, context=SSL["https"]))


def main():
    store = BotTokenStore()
    token = None
    try:
        token = store.load()
        print("A bot token is already stored. Enter a new one only to replace it.")
    except OSError:
        print("No bot token stored yet.")
    except ValueError:
        print("The stored token is corrupt; enter a fresh one.")

    if not token:
        raw = input("Paste the bot token: ").strip()
        if not validate_token_format(raw):
            print("That does not look like a Discord bot token. Nothing changed.")
            return 1
        try:
            app = get(API + "/users/@me", raw)
        except (OSError, ValueError) as exc:
            print(f"Discord refused the token ({exc}). Nothing was stored.")
            return 1
        print(f"Token valid — bot is '{app['username']}'. Storing (DPAPI-protected)...")
        store.replace(raw)
        token = raw
    else:
        app = get(API + "/users/@me", token)
        print(f"Bot is '{app['username']}'.")

    guilds = get(API + "/users/@me/guilds", token)
    if not guilds:
        print("The bot is in no guild. Invite it with the hand-built URL:")
        print(
            f"  https://discord.com/oauth2/authorize?client_id={app['id']}"
            "&scope=bot&permissions=1049600"
        )
        return 1
    guild_id = guilds[0]["id"]
    if len(guilds) > 1:
        for i, g in enumerate(guilds, 1):
            print(f"  {i}. {g['name']} ({g['id']})")
        pick = input("Which guild number? ")
        guild_id = guilds[int(pick) - 1]["id"]
    name = next(g["name"] for g in guilds if g["id"] == guild_id)
    print(f"Guild: {name} ({guild_id})")

    members = get(API + f"/guilds/{guild_id}/members?limit=1000", token)
    members = [m for m in members if not m["user"].get("bot")]
    members.sort(
        key=lambda m: (
            m.get("nick") or m["user"].get("global_name") or m["user"]["username"]
        ).lower()
    )
    for i, m in enumerate(members, 1):
        label = m.get("nick") or m["user"].get("global_name") or m["user"]["username"]
        print(f"  {i}. {label}")
    pick = input("Which one are you? ")
    user_id = members[int(pick) - 1]["user"]["id"]
    print(f"Your user id: {user_id}")

    with settings.update(settings.load()) as doc:
        doc.setdefault("preview", {}).setdefault("alerts", {}).setdefault(
            "stream_probe", {}
        )["guild_id"] = guild_id
        doc["preview"]["alerts"]["stream_probe"]["user_id"] = user_id
    print("Identity written to settings.")

    print("Running one real probe...")
    live = probe_live_state(token, guild_id, user_id)
    print(f"Probe verdict: you are currently {'LIVE' if live else 'not live'}.")
    print("Setup complete. The Streaming card's probe badge now works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
