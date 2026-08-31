---
description: Capture every Wingman screen for UX review
argument-hint: "[checkout path or worktree name; defaults to this repo root]"
---

Capture a full screenshot set of FlyGD Wingman for UX review, using
`scripts/shoot_screens.py`.

Target checkout: ${ARGUMENTS:-this repository's root}.

Resolve the target before doing anything else:

- With no argument, use `git rev-parse --show-toplevel`.
- If the argument names an existing path, resolve it to an absolute path.
- If it is a bare worktree name (for example `ux-screenshots`), inspect
  `git worktree list --porcelain` from the repository root and select the
  worktree whose directory basename exactly matches. Do not assume a
  harness-specific worktree directory.
- If no checkout matches, stop and report that clearly rather than shooting
  a different tree.

Resolve the Windows form of the checkout path (`/mnt/c/...` to `C:\...`),
because the script runs as a Windows process.

Windows only. The script drives a real WebView2 window over the Chrome
DevTools Protocol; there is nothing to capture on Linux or macOS.

## Step 1 — ensure the CDP venv exists

The script runs under a **Windows** interpreter and needs `websocket-client`.
That venv lives in gitignored `tmp/`, so it does not survive a fresh clone or
`git clean -fdx`. Check for it and rebuild it silently when missing — do not
make the user diagnose a bare `ModuleNotFoundError`:

```
ls <checkout>/tmp/shootvenv/Scripts/python.exe
```

If absent, locate a Windows Python that can import the app's own dependencies.
Search `%LOCALAPPDATA%\Programs\Python` and `C:\Python*`; **do not trust
`where.exe python`**, which surfaces only the Microsoft Store stub and reports
"Python was not found". Then run:

```
'<windows-python>' -m venv '<checkout-win>\tmp\shootvenv'
'<checkout>/tmp/shootvenv/Scripts/python.exe' -m pip install -q websocket-client
```

## Step 2 — hand the command to the user; do not run it yourself

The script asks the user to quit Wingman from its tray icon, then waits. Tool
call output is buffered, so running it yourself can hide that prompt until its
wait has already timed out. Print the command for the user to run with Pi's `!` shell prefix and let them
drive it. Keep it on one physical line so a pasted newline cannot become part
of a quoted path. After substituting the resolved WSL checkout path, use this
short form; `wslpath` derives the Windows argument after `cd`:

```
! cd <checkout> && tmp/shootvenv/Scripts/python.exe scripts/shoot_screens.py --checkout "$(wslpath -w "$PWD")"
```

Say briefly what to expect: it asks them to right-click the Wingman tray icon
and choose Quit (only the tray menu can exit it — `close()` hides; see
`wingman/ui/api.py`), then launches from the selected checkout, walks **11
screens**, and relaunches their app afterward. The set includes the focused
**Profiles — Identify accounts** and **Profiles — Backups** routes. If Wingman
is not running when they start, it says so and skips the restore.

Mention `--port` if the default is busy, `--settle-ms` if a screen looks
half-drawn, and `--out` only when relevant.

## Step 3 — review the set

Read `<out_dir>/manifest.json` and report:

- `shot_count` against `screens_total`, and anything listed in `failed`.
- `eve_shown`. When false, **seven screens** are legitimately skipped because
  the EVE gate hides three Settings sections and four Profiles/Skills routes;
  say so explicitly, or a set of four reads as truncated.
- `engine_present`. When false, Settings — Bookmarks shows the shooter's
  engine-missing state rather than the real configured screen; call that out.
- `branch`, `sha`, and `dirty`. Confirm the set came from the checkout the user
  intended. A set from the wrong checkout is worse than no set: it reports
  another tree's UI under this branch's name.

Then **open every PNG**. Do not review from the file listing. The failure this
tool exists to catch is a screen that renders blank but well-formed: handlers
register at the top of each module's IIFE, so one bad name throws mid-module
and every registration below it silently never runs. In `ls` output that is
indistinguishable from a good screen.

Review what you see against `DESIGN.md` (how a screen is built) and `PRODUCT.md`
(what belongs in the product).
