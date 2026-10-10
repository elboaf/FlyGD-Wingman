"""Discord presence probe for #334 (Go Live closed loop, feasibility gate).

Decides the unknowns the closed-loop spec rests on, before any feature code
is written:

1. **Reach** — does a bot the user creates receive the user's own presence
   flipping to STREAMING (activity type 1) when Go Live starts, and away
   when it stops? At what latency?
2. **Silent breaks** — what does the gateway report when Activity Privacy
   is off, the user goes Invisible, the bot loses the guild, or the
   connection drops? (Is the degrade path *observable*, not just assumed?)
3. **Ceremony** — how much setup does the user actually perform? (Recorded
   by hand in the runbook; the script only prints what it needs.)

Run THIS PROCESS on the streaming box (the box that runs Discord):

    uv run --with websockets python scripts/discord_presence_probe.py --token <BOT_TOKEN>

Follow docs/discord-presence-probe.md. The console prints a timestamped
evidence trail to paste into #334.

Design notes:
- websockets is used via `uv run --with websockets` (ephemeral) on purpose:
  the repo gains no dependency for a throwaway probe. If this becomes a
  product feature, the dependency decision happens in the feature ticket,
  not here.
- stdlib only otherwise. One thread: the websocket read loop. Anything
  ambiguous is printed raw — this is evidence collection, not a client.

Throwaway tool: nothing here ships, imports no product state.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
OP_DISPATCH = 0
OP_IDENTIFY = 2
OP_HELLO = 10
OP_HEARTBEAT = 1
OP_HEARTBEAT_ACK = 11

ACTIVITY_STREAMING = 1


def _stamp() -> str:
    return time.strftime("%H:%M:%S")


def _activity_line(activity: dict) -> str:
    t = activity.get("type")
    name = activity.get("name", "?")
    url = activity.get("url")
    kind = {0: "GAME", 1: "STREAMING", 2: "LISTENING", 4: "CUSTOM"}.get(t, str(t))
    return f"  activity: {kind} name={name!r} url={url!r}"


def _is_streaming(activities: list[dict]) -> bool:
    return any(a.get("type") == ACTIVITY_STREAMING for a in activities)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--token", required=True, help="bot token from the Developer Portal"
    )
    ap.add_argument(
        "--guild", required=True, help="guild id the user shares with the bot"
    )
    ap.add_argument("--user", required=True, help="the user id to watch (your own)")
    args = ap.parse_args()

    # websockets is used via `uv run --with websockets` (ephemeral) on purpose:
    # the repo gains no dependency for a throwaway probe. If this becomes a
    # product feature, the dependency decision happens in the feature ticket,
    # not here.
    import ssl

    from websockets.sync.client import connect

    # Presence needs GUILD_PRESENCES (256) + GUILD_MEMBERS (2) subscribed in
    # the identify payload AND enabled in the portal; GUILDS (1) for READY.
    payload_intents = 1 | 2 | 256

    state = {"hb": None, "seq": None, "acked": True}

    def _send(ws, obj):
        ws.send(json.dumps(obj))

    def _heartbeat(ws):
        while True:
            time.sleep(30)
            hb = state["hb"]
            if hb is None:
                continue
            try:
                _send(ws, {"op": OP_HEARTBEAT, "d": state["seq"]})
                print(f"[{_stamp()}] heartbeat sent (seq={state['seq']})")
            except Exception as exc:  # noqa: BLE001 -- connection dead; read loop will notice
                print(f"[{_stamp()}] !! heartbeat failed: {exc}")
                return

    def _present(presence: dict) -> None:
        uid = presence.get("user", {}).get("id")
        if uid != args.user:
            return  # only the watched user is evidence; others printed on --verbose only
        status = presence.get("status")
        activities = presence.get("activities", [])
        lines = [_activity_line(a) for a in activities]
        streaming = _is_streaming(activities)
        verdict = "STREAMING" if streaming else "not streaming"
        print(f"[{_stamp()}] PRESENCE user={uid} status={status} -> {verdict}")
        for line in lines:
            print(line)

    print(f"[{_stamp()}] connecting {GATEWAY_URL}")
    with connect(GATEWAY_URL, ssl=ssl.create_default_context()) as ws:
        hello = json.loads(ws.recv())
        state["hb"] = hello["d"]["heartbeat_interval"]
        print(f"[{_stamp()}] HELLO heartbeat_interval={state['hb']}ms")
        threading.Thread(target=_heartbeat, args=(ws,), daemon=True).start()

        _send(
            ws,
            {
                "op": OP_IDENTIFY,
                "d": {
                    "token": args.token,
                    "intents": payload_intents,
                    "properties": {
                        "os": "windows",
                        "browser": "wingman-probe",
                        "device": "wingman-probe",
                    },
                },
            },
        )
        print(
            f"[{_stamp()}] IDENTIFY sent intents={payload_intents} "
            f"(GUILDS=1, GUILD_MEMBERS=2, GUILD_PRESENCES=256)"
        )

        while True:
            try:
                raw = ws.recv(timeout=90)
            except Exception as exc:  # noqa: BLE001 -- any socket death IS evidence
                print(f"[{_stamp()}] !! recv failed / timed out: {exc!r}")
                print(
                    f"[{_stamp()}]    (a timeout after 90s with no READY is itself evidence — record it)"
                )
                return 3
            payload = json.loads(raw)
            op = payload.get("op")
            if op == OP_DISPATCH:
                t = payload.get("t")
                state["seq"] = payload.get("s")
                if t == "READY":
                    gu = [g["id"] for g in payload["d"].get("guilds", [])]
                    print(f"[{_stamp()}] READY guilds={gu} (want [{args.guild}])")
                    if args.guild not in gu:
                        print(
                            f"[{_stamp()}] !! bot is NOT in guild {args.guild} — "
                            f"invite it (runbook step 3), then restart"
                        )
                elif t == "PRESENCE_UPDATE":
                    _present(payload["d"])
                else:
                    print(f"[{_stamp()}] dispatch {t}")
            elif op == OP_HEARTBEAT_ACK:
                print(f"[{_stamp()}] heartbeat acked")
            elif op == 7:  # reconnect
                print(
                    f"[{_stamp()}] !! server asked RECONNECT — record this as a gateway-drop observation"
                )
                return 4
            else:
                print(f"[{_stamp()}] op={op}")


if __name__ == "__main__":
    sys.exit(main())
