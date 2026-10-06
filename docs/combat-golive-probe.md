# Capture-visibility probe runbook (#312)

Decides the unknowns the combat Go Live spec (revision 3) rests on, before
any feature code is written:

1. **Tier** — does Discord's game capture show DWM-composited thumbnail
   content, or a black/empty window? (A build / B screen-capture fallback /
   C abandon.)
2. **Pin** — does the stream's per-process window pin land on the probe's
   mirror window even though it was created *after* registration, sits at
   the bottom of the z-order, and is never focused?
3. **Style sweep** — only if 2 fails: does a caption strip or
   `WS_EX_TOOLWINDOW` change what Discord's enumerator picks?

Estimated time: 15–20 minutes. Everything observed goes into the evidence
template at the bottom of this file and then into #312. The tier result is
the gate: the spec says the feature does not start until the probe reports
A or B.

## Prerequisites

- The box you stream from, with Discord signed in and joined to a voice
  channel (an empty one is fine — Go Live needs the channel, not an
  audience).
- A second viewer (phone is ideal) in that voice channel, so "what the
  fleet sees" is observed independently of your own Discord client's
  preview.
- Two windows to mirror. EVE clients are the real subject; a second-best
  stand-in is any two windows whose titles share a substring (two Notepad
  windows titled `alpha` / `bravo`).
- The test build of the mirror (issue #315): from the repo checkout,

  ```
  python -m PyInstaller packaging/mirror.spec --noconfirm \
      --distpath build/mirror-dist --workpath build/mirror-work
  ```

  The exe is `build/mirror-dist/wingman-mirror/wingman-mirror.exe`. The
  probe script (`scripts/capture_visibility_probe.py`) remains as the
  reference implementation, but do **not** register `python.exe`: the
  dedicated image name is the point of the rev-3 design, and registering
  an interpreter makes every Python process on the box the "game" — a
  pin leg could then land on the wrong process and poison the evidence.

The mirror window is the mirror under test: top-level, captioned, created
at the bottom of the z-order, never activated, never minimized (it swallows
its own minimize unless you explicitly run step 6). The thumbnail it shows
is the house DWM wrapper, the exact mechanism the real mirror will use.

## Step 0 — launch and orient

```
build\mirror-dist\wingman-mirror\wingman-mirror.exe --src-title "EVE -"
```

Run it from a normal console so the commands are typable (double-clicking
works too, but you lose the console). `--src-title` defaults to `Notepad`.

- The console prints the exe's own path — you need it in step 1.
- A 800×600 window appears showing the first matching source
  (default: a window with `Notepad` in the title; override with
  `--src-title "EVE -"` to go straight at EVE clients).
- `l` lists visible top-level windows if the pick was wrong.
- A status line prints every 5 s; the full console log is the evidence
  trail.

## Step 1 — register the game

Discord → User Settings → Registered Games → **Add it** → browse to the
`wingman-mirror.exe` path the console printed. Discord should then show
the mirror process as a detected game. If it instead shows it under "no
game detected", use the "Add it" path anyway — that is the manual
registration the spec's setup ceremony assumes.

## Step 2 — start the stream at the mirror

In the voice channel: Go Live (Share Your Screen) → pick the **registered
game** entry for the probe (not a monitor, not a window capture). Discord
pins one window of the process now. The viewer should see the thumbnail
content (the mirrored source), or black — that contrast is the whole
point.

## Step 3 — the tier leg (probe question 1)

For each mirror state below, wait ~5 s (two status lines) and record what
the viewer sees — live content, frozen frame, or black:

| # | Action (console key) | Viewer sees |
|---|----------------------|-------------|
| 3a | mirror in front, untouched | |
| 3b | cover the mirror completely with another window | |
| 3c | `3` (parks the mirror off-screen, bottom z-order) | |

- **3a/3b/3c show live content → Tier A.** Thumbnail content survives
  game capture. Build as specified.
- **Black in all three, but the mirror is visible on your own monitor →
  candidate Tier B.** Confirm with one extra check: stop the stream,
  restart it as a *window/screen capture* of the probe instead of game
  capture. If that works, Tier B: ship with documented screen-capture
  setup.
- **Black everywhere including window capture → Tier C.** The feature
  waits for a Discord-side change; nothing lands.

## Step 4 — the pin leg (probe question 2)

The real mirror will exist *before* the user registers it in some installs
and *after* in others (the spec's ceremony registers the mirror exe, then
starts the mirror). Exercise the uncomfortable orders — after each restart,
re-pick the stream source if Discord dropped the pin, and note whether you
had to:

| # | Action | Pin landed on mirror? | Needed re-pick? |
|---|--------|----------------------|-----------------|
| 4a | Register first, then launch probe (already done above) | | |
| 4b | Quit probe (`q`), restart it, watch the existing stream | | |
| 4c | Stop stream; launch a *second* probe instance; stream; note which instance Discord pinned | | |
| 4d | With the stream live, focus other apps for 30 s (never the mirror); does the stream survive focus churn? | | |

`2` (arm focus-follow) after 4a: switch focus between two EVE clients —
the thumbnail must follow, and the viewer must see the switch. That
validates the rebind loop end to end.

## Step 5 — style sweep (only if step 4 failed to pin the mirror)

One factor at a time; after each `t`/`c` the window is recreated, so
re-pick the stream source and record whether the pin behavior changed:

- `t` — toggles `WS_EX_TOOLWINDOW` (hides from Alt-Tab and most
  enumerators). If this *fixes* pinning, note it: the spec treats it as a
  trade-off (invisible to capture enumerators), not a default.
- `c` — toggles the caption. The spec prefers keeping the caption (a
  captionless window may be harder for the picker to treat as a game
  window); a result either way is evidence.

## Step 6 — minimize confirmation (expected failure, on purpose)

`5` allows exactly one minimize. Per the spec's visibility states, Windows
stops compositing a minimized window's surface, so the stream should go
black/frozen. Confirm, then restore the window (`r` rebinds the thumbnail
after any source change). This documents the failure the real mirror
prevents by never minimizing.

## Recording the result

Paste the console log's key lines plus this filled template into #312:

```
Probe result (#312 capture-visibility gate)
- Tier: A / B / C            (step 3; B requires the window-capture check)
- States live / covered / off-screen: ... / ... / ...
- Pin: lands / re-pick needed / wrong window   (step 4a–d)
- Focus churn survival: yes / no
- Style sweep: n/a | toolwindow: ... | captionless: ...  (step 5)
- Minimize: black confirmed / stream survived (unexpected!)   (step 6)
- Discord build info (User Settings → Appearance → version)
- Windows build (winver)
- Console evidence: <key timestamped lines>
```

Decision rule (verbatim from the spec): **A — build as specified; B —
ship with documented screen-capture setup; C — abandon, document, no code
lands.** The feature is not started until the probe reports A or B.

## Troubleshooting

- **`!! no visible window title contains ...`** — run `l`, pick a real
  title substring, restart with `--src-title`.
- **`!! DwmRegisterThumbnail FAILED`** — DWM composition is off or the
  source died between enumerate and register; restart the probe.
- **Discord offers no "Add it" button** — Discord only offers manual
  registration when it fails to auto-detect a game; if the process is
  already listed, use it as-is.
- **Stream entry shows the probe but the viewer sees your desktop** — you
  picked a monitor, not the registered game; stop and re-pick (step 2).
- **Two probe instances, pin landed on the wrong one** — that is a pin-leg
  finding (4c), not a probe bug; record which instance was pinned (the
  status lines identify phases).
