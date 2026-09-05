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
`wingman/ui/api.py`), then launches from the selected checkout, walks **33
screens**, including **Settings — Characters**, **Settings — Characters
(waiting)**, **Settings — Characters (partial cleanup)**, **Settings —
Characters (narrow 840x625)** and **Fittings — Narrow (840x625)**, and
relaunches their app afterward. The set also includes the focused
**Profiles — Identify accounts** and **Profiles — Backups** routes. If
Wingman is not running when they start, it says so and skips the restore.

Mention `--port` if the default is busy, `--settle-ms` if a screen looks
half-drawn, and `--out` only when relevant.

## Step 3 — review the set in bounded visual batches

Read `<out_dir>/manifest.json` and validate and report all of these fields:

- `shot_count` against `screens_total`, plus every entry in `failed` and
  `skipped`.
- `eve_shown`. When false, the set is correctly reduced to the four non-EVE
  screens and the manifest's `skipped` list must name every EVE-gated screen;
  say so explicitly, or a set of four reads as truncated.
- `engine_present`. When false, Settings — Bookmarks shows the shooter's
  engine-missing state rather than the real configured screen; call that out.
- `branch`, `sha`, and `dirty`. Confirm the set came from the checkout the user
  intended. A set from the wrong checkout is worse than no set: it reports
  another tree's UI under this branch's name.

Before opening images, inventory every expected PNG from the manifest: exact
filename, byte size, dimensions when practical, and total screenshot-set size.
Reconcile the inventory with `manifest.json`; report missing, extra, duplicate,
or mismatched files rather than silently changing the expected set.

> **Inspect every screenshot** means every screenshot receives documented
> visual coverage. It does not mean every full-resolution PNG is attached to
> one model conversation. Image request bytes, not just model tokens, are a
> hard resource limit.

Do not load the full screenshot suite into the main Pi session. In particular:

- do not open every original PNG in the main context;
- do not read many original PNGs in one parallel tool batch; and
- do not rely on displayed token usage or token compaction as an image-payload
  safety check. Base64 request size and envelope overhead remain even when Pi's
  image token estimate looks small.

Prefer isolated screenshot-review subagents when available. Partition the
expected PNGs so each visual worker receives **no more than 4 images** and
**no more than 6 MiB total of original image files**. Both limits apply: account
for base64 expansion and request-envelope overhead, and reduce the image count
further whenever needed to stay under the byte cap. Each worker must visually
open every assigned image and return only concise, structured findings keyed by
exact filename. For each image, it must identify blank or partially initialized
content, clipping, overflow, overlap, stale state, and anything else visibly
incorrect. Keep image data in that isolated context; only textual findings
return to the main session.

If isolated visual contexts are unavailable, create temporary labeled contact
sheets or compressed review derivatives instead:

- preserve the original PNGs unchanged;
- use no more than 4–6 screenshots per sheet and label each panel with its exact
  filename;
- constrain the longest edge to approximately 1600–2000 pixels and prefer
  compressed JPEG or WebP when transparency is unnecessary;
- inspect derivative byte sizes before loading them, and keep all image data
  introduced into the active context comfortably below 8 MiB;
- open an original selectively only when small text or a suspected defect needs
  full-resolution confirmation; and
- use available system tools or libraries; do not add a project dependency for
  temporary review artifacts.

Maintain a coverage ledger with one entry for every screenshot expected by the
manifest: filename, visually inspected yes/no, blank/initialized status, visual
findings, and whether full-resolution inspection was needed. Do not claim a
complete review until every expected screenshot is represented and marked as
visually inspected. A file listing or manifest check is not visual coverage:
the failure this tool exists to catch is a blank but well-formed screen, which
is indistinguishable from a good screen in `ls` output.

## Step 4 — run the full Impeccable critique without reattaching the suite

Do not substitute a lightweight inline UX review. Invoke the `impeccable` skill
and follow its `critique` workflow in full, using the captured PNG set as the
visual target and the selected checkout as the source target:

- Load `PRODUCT.md` and `DESIGN.md` from the selected checkout.
- Preserve the two required assessment tracks. Run the visual/design assessment
  with the same isolated batching rules as Step 3: every expected screenshot
  must receive genuine visual inspection, but no visual worker may receive more
  than 4 images or 6 MiB of source images. Reports must be concise and keyed by
  exact filename. If subagents are unavailable, use the bounded derivative
  fallback above rather than attaching all originals to one context.
- Run a separate, image-free synthesis step that combines the filename-keyed
  visual batch reports. Do not reattach the screenshots for synthesis.
- Keep the automated assessment in its own isolated, image-free context. It
  must run the deterministic detector against `<checkout>/wingman/web` and
  distinguish real findings from contextual false positives as the critique
  workflow requires.
- Reconcile the manifest coverage ledger, every visual batch report, automated
  findings, `PRODUCT.md`, and `DESIGN.md` in the final critique. Synthesize the
  required Nielsen heuristic scores, cognitive-load results, anti-pattern
  findings, prioritized issues, and relevant persona walkthroughs.
- Clearly distinguish direct visual evidence from interaction behavior that
  static screenshots cannot prove.
- Treat the captured set as a static target. Unless a separately reachable live
  browser tab already exists, report that browser overlays were skipped; do not
  rerun the shooter or app merely to obtain or inject overlays.
- Review recommendations against `DESIGN.md` (how a screen is built) and
  `PRODUCT.md` (what belongs in the product), rather than applying generic web
  conventions over documented product decisions.

Ask the critique's targeted follow-up questions and wait for the user's answers
before presenting its final recommended-action sequence.
