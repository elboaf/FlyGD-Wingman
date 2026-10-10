# Discord presence probe runbook (#334)

Decides the unknowns the Go Live closed-loop spec (the #333 umbrella) rests
on, before any feature code is written:

1. **Reach** — does a bot receive the user's own presence flipping to
   STREAMING (activity `type: 1`) when Go Live starts, and away when it
   stops? At what latency?
2. **Silent breaks** — what is observed when Activity Privacy is off, the
   user goes Invisible, or the gateway drops? Is the degrade path
   observable, not just assumed?
3. **Ceremony** — how much setup does the user actually perform?

Estimated time: 15–20 minutes after the one-time bot setup (5–10 minutes,
first run only). Everything observed goes into the evidence template at the
bottom and then into #334. The tier result is the gate: #333's children do
not start until the probe reports A or B (same discipline as #312's
capture-visibility probe).

## Prerequisites

- The box you stream from, with Discord signed in.
- One-time setup (record every step you perform — that IS the ceremony
  measurement for question 3):
  1. <https://discord.com/developers/applications> → New Application →
     name it (e.g. `wingman-probe`). Applications → Bot → Reset Token →
     copy the token (shown once).
  2. On the same Bot page, enable **Presence Intent** and **Server
     Members Intent** (both toggles). Save.
  3. OAuth2 → URL Generator: scopes `bot`, bot permissions
     **View Channels** only; open the generated URL, pick your community
     guild, authorize.
  4. Copy your own user ID: Discord → User Settings → Advanced → enable
     Developer Mode → right-click your name in the guild → Copy User ID.

## Run

```powershell
uv run --with websockets python scripts/discord_presence_probe.py --token <BOT_TOKEN> --guild <GUILD_ID> --user <YOUR_USER_ID>
```

Wait for the `READY guilds=[...]` line. Keep the console visible for the
whole leg.

## Step 1 — the reach leg (probe question 1)

1. In the voice channel, start Go Live (Share Your Screen) the way the
   shipped Streaming card does — via the mirror, per #312's setup walk.
   Watch the console: within a few seconds you want a

   ```
   [HH:MM:SS] PRESENCE user=<you> status=online -> STREAMING
     activity: STREAMING name=<...> url='https://twitch.tv/...' (or youtube)
   ```

   line. Note the latency (chord press → line) roughly; the template asks
   for seconds.
2. Stop the stream (its quiet period will do it, or stop by hand). Expect
   the matching `-> not streaming` line. Note latency again.
3. Do the same once with a manual Go Live (started by hand, not by the
   chord) — this is the origin #336's skip must cover, so confirm the
   presence signal is identical whichever way the stream started.

## Step 2 — the silent-breaks leg (probe question 2)

After each change, watch the console for ~60 s and record what (if
anything) arrives. **Absence of any event is itself evidence — record it.**

| # | Action | Expected bad case | Observed |
|---|--------|-------------------|----------|
| 2a | User Settings → Privacy: turn **Activity Privacy** off, restart stream | No STREAMING presence ever arrives | |
| 2b | Restore Activity Privacy; go **Invisible** (self-set status) while streaming | Presence absent, or shown but status≠online | |
| 2c | Back online, stream running: kill the probe's network (or just note the heartbeat lines stop) | Heartbeat failures / recv timeout printed — degrade must be observable | |
| 2d | Restart the probe: does a stream that started while the bot was OFFLINE produce a presence event late (on READY) or never? | Tells the feature whether a late-joining observer can trust state | |

## Step 3 — ceremony cost (probe question 3)

Fill in by hand: minutes spent, number of portals visited, anything that
would scare a non-technical multiboxer (token secrecy warnings, invite
permission fears). One honest paragraph is enough.

## Recording the result

Paste the console's key lines plus this filled template into #334:

```
Probe result (#334 presence gate)
- Tier: A / B / C                          (step 1; B if reach works but ceremony/fragility is heavy)
- Start observed: yes/no, latency ...s     (step 1)
- Stop observed: yes/no, latency ...s      (step 1)
- Manual-start stream also observed: yes/no (step 1.3)
- Activity Privacy off: no events / ...    (step 2a)
- Invisible while streaming: ...           (step 2b)
- Gateway drop observable: yes/no          (step 2c)
- Stream started while bot offline: ...    (step 2d)
- Ceremony: <paragraph>                    (step 3)
- Discord build info (User Settings → Appearance → version)
- Windows build (winver)
- Console evidence: <key timestamped lines>
```

Decision rule (verbatim from #334): **A — build the closed loop as
specced; B — ship skip/re-sync best-effort with open-loop fallback and a
downgraded card; C — close #335/#336/#337, reduce the umbrella to
documented limitations.** The children are not started until the probe
reports A or B.

## Troubleshooting

- **`Used disallowed intents`** — the two portal toggles in setup step 2
  are off. Turn them on and restart the probe.
- **`READY guilds=[]`** — the bot isn't in the guild; redo the invite
  (setup step 3).
- **READY fine but no PRESENCE_UPDATE ever, even on your own status
  change** — Presence Intent missing from either the portal (step 2) or
  it would fail at identify; this outcome is itself a Tier C data point.
- **`!! recv failed / timed out`** — network or Discord-side drop; record
  it under step 2c evidence and rerun.
- **Token shown once and lost** — Applications → Bot → Reset Token again.
