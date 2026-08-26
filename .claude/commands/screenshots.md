---
description: Capture a screenshot of every Wingman screen for UX review
argument-hint: "[checkout path or worktree name; defaults to this repo root]"
---

Capture a full screenshot set of FlyGD Wingman for UX review, using
`scripts/shoot_screens.py`.

Target checkout: $ARGUMENTS — if empty, use this repository's root. If given a
bare worktree name (e.g. `ux-screenshots`), expand it to
`<repo-root>/.claude/worktrees/<name>`. Resolve the Windows form of that path
(`/mnt/c/...` → `C:\...`) since the script runs as a Windows process.

Windows only. The script drives a real WebView2 window over the Chrome DevTools
Protocol; there is nothing to capture on Linux or macOS.

## Step 1 — ensure the CDP venv exists

The script runs under a **Windows** interpreter and needs `websocket-client`.
That venv lives in gitignored `tmp/`, so it does not survive a fresh clone or a
`git clean -fdx`. Check for it and rebuild it silently when missing — do not
make the user diagnose a bare `ModuleNotFoundError`:

```
ls <checkout>/tmp/shootvenv/Scripts/python.exe
```

If absent, locate a Windows Python that can import the app's own dependencies.
Search `%LOCALAPPDATA%\Programs\Python` and `C:\Python*`; **do not trust
`where.exe python`**, which surfaces only the Microsoft Store stub and reports
"Python was not found" — concluding from it that no Windows Python exists is a
mistake that has already cost this project a verification pass. Then:

```
'<windows-python>' -m venv '<checkout-win>\tmp\shootvenv'
'<checkout>/tmp/shootvenv/Scripts/python.exe' -m pip install -q websocket-client
```

## Step 2 — hand the command to the user; do not run it yourself

The script asks the user to quit Wingman from its tray icon, then waits. Run
from a tool call, its output is buffered and that prompt does not reach them
until after the wait has already timed out — two runs were lost to this before
the cause was found. So print the command for the user to run with the `!`
prefix and let them drive it:

```
! cd <checkout> && '<checkout>/tmp/shootvenv/Scripts/python.exe' scripts/shoot_screens.py --checkout '<checkout-win>'
```

Say briefly what to expect: it asks them to right-click the Wingman tray icon
and choose Quit (only the tray menu can exit it — `close()` hides, see
`wingman/ui/api.py`), then launches from the checkout, walks nine screens, and
relaunches their app afterwards. If Wingman is not running when they start, it
says so and skips the restore.

Mention `--port` (if the default is busy), `--settle-ms` (raise it if a screen
looks half-drawn) and `--out` only when relevant.

## Step 3 — review the set

Read `<out_dir>/manifest.json` and report:

- `shot_count` against `screens_total`, and anything listed in `failed`.
- `eve_shown`. When false, five screens are legitimately skipped because the
  EVE gate hides two routes and three Settings sections — say so explicitly, or
  a set of four reads as truncated.
- `branch`, `sha`, `dirty` — confirm the set came from the tree the user meant
  to shoot. A set from the wrong checkout is worse than no set: it reports
  another tree's UI under this branch's name.

Then **open the PNGs**. Do not review from the file listing. The failure this
tool exists to catch is a screen that renders blank but well-formed: handlers
register at the top of each module's IIFE, so one bad name throws mid-module and
every registration below it silently never runs — the screen loads as an inert,
empty copy of itself with no error anywhere. In `ls` output that is
indistinguishable from a good screen.

Review what you see against `DESIGN.md` (how a screen is built) and `PRODUCT.md`
(what belongs in the product) — both are short and hold the rules that are not
in the code.
