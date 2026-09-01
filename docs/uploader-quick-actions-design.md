# Uploader quick actions — design (revision 2)

Three additions to the Uploader, requested together:

1. **Post the last hour** — post combat logs for the last 60 minutes to
   Discord, with no video and no selection involved.
2. **Right-click › Play** — open the recording under the pointer in the
   Windows default player.
3. **Right-click › Rename…** — rename that recording on disk, preserving
   its extension.

**[agreed]** marks a decision already settled with the maintainer.
**[r2]** marks a change made after an independent review of revision 1,
which found three of its factual claims wrong. Those corrections are
recorded inline rather than silently applied, because two of them are the
kind that would otherwise be re-derived and re-broken.


## Why these belong here

`PRODUCT.md` puts uploading fight footage among the three primaries, and
the Uploader is the one destination in the app that is *about a folder's
contents*. `index.html`'s note at `#btn-open-folder` records the gap these
close: until `Open folder` landed, every file affordance on this screen
acted on the YouTube link rather than the file, so a recording that is
missing, mis-named, or not what OBS was supposed to produce had to be
inspected outside Wingman. Play and Rename are the two things the user
currently leaves the app to do, and both act on the row already under the
pointer.

Post the last hour is a different argument. Combat logs today are the
*tail of an upload* (`Api._upload_done` → `_post_combat_logs`), so the only
way to send logs is to publish a video. The requested case is the fight
that was not recorded, or was recorded and is not worth uploading. The
feature is built; what is missing is a route to it that does not go
through YouTube — which also keeps `PRODUCT.md`'s independence rule
("must not require … a Google account to use the EVE tools") intact.


## 1. Post the last hour

### Behaviour

- **[agreed]** The window is the 60 minutes ending at the click:
  `end = datetime.now(UTC)`, `start = end - 1h`. Not derived from any
  recording.
- **[agreed]** Whole overlapping log files, exactly as the upload tail
  does. `combatlog.select_logs` takes any gamelog whose session overlaps
  the window plus its five-minute padding, and `build_archive` zips them
  whole. A session log open since morning goes up in full. Nothing is
  trimmed per line.
- **[agreed]** Unavailable while a video upload or another log post runs.
- **[agreed]** No confirmation dialog. The maintainer's call: this is a
  known group posting known logs to its own webhook, and a dialog on every
  click is the recurring-friction pattern `format_upload_confirm`'s
  docstring warns about in a different key.
- No selection, no ffprobe, no `_probe_now`. The window is wall-clock, so
  `_post_combat_logs`'s entire "no readable duration" branch does not
  apply.
- Cap and drop-note behaviour inherited unchanged (`MAX_FILES = 64`,
  `dropped_note`), so a truncated export still says so.

### Placement — **[r2] the panel, as a second card, placed last**

Revision 1 put this in a new panel card and did not notice that
`tests/test_uploader_page.py:517-526` asserts `len(headings) == 1` inside
`#route-main`. Verified: that test goes red on a second `<h2>`.

The test is amended, deliberately, and the amendment is the argument:

> Uploader 2's finding is *one concept must not appear under two names*
> (`UPLOAD` and `PUBLISH`, with the Upload button in the card not called
> Upload). Combat logs are a second **concept**, not a second name for
> this one — they go to Discord, not YouTube, and they are reachable with
> no Google account at all. The test becomes: the panel's *upload* card is
> one card, its heading does not echo the tab name, and the Upload button
> is inside it.

The list footer was considered and rejected **[r2]**: the reviewer
proposed it, but every control there acts on the *recording* folder
(`Open folder`'s own justification is that "its object is the folder"),
and gamelogs are a different folder entirely. It would also add a third
wrapped line to a footer that already wraps at the floor, taking that
height from the list.

**The new card goes LAST in the panel, and that placement is the whole
answer to the height objection.** The reviewer's arithmetic — panel
content ≈460px against ≈516px available at 625 CSS, so a second card
(~96px, ~150 with the note showing) is what *makes* the pane scroll — is
directionally right and is accepted. What it does not account for is
*which* control ends up below the fold. Ordering the new card after the
upload card means `Upload` and everything above it keep their exact
current position, and the thing that may need a scroll at the floor is the
least-pressed control on the screen. Uploader 9's complaint was that the
most-pressed control was last in an overflowing stack; this preserves that
fix rather than undoing it.

Not verified: the numbers above are derived from `style.css` declarations,
not rendered. The smoke pass measures the panel at 840×625 and at 200%
(where `.panel` is 248px) and this design is wrong if `Upload` is not
fully visible there.

**Words.** Heading `Combat logs`, button `Post the last hour`. Not
"Post last hour's logs" under a heading reading "Combat logs" — PRODUCT.md
forbids a line that only restates its heading. No trailing `…`: the button
opens nothing.

**Treatment.** `.btn`. `DESIGN.md`: one accent per screen or none, and
this screen's accent is `Upload`.

`#logs-note` moves into this card, because after this change the sentence
has a control to belong to. It keeps reading `INERT_NOTES["no_webhook"]`
off the settings payload; the string does not move to the page.

### Enabled state — **[r2] not gated on the webhook**

Revision 1 disabled the button when no webhook was configured. That is
wrong, and the reason is verified rather than argued: **there is no
`_push("onSettings", …)` anywhere in `wingman/ui/api.py`** — `web/app.js:340`
is the sole caller and it runs once, at page load. `ui/api.py:2129-2145`
states the rule outright. So the page's idea of "is a webhook configured"
is fixed for the session, and gating on it means: configure a webhook in
Settings, come back, and the button is dead until restart, with a note
explaining why that is also stale. `WM.setEnabled`'s own comment forbids
exactly this ("nothing here is permitted to disable the only route to its
own precondition"), and `_with_webhook_status` exists because this bug was
already fixed once for `Show`/`Remove`.

So:

| state | control |
|---|---|
| a video upload or a log post is running | disabled, via a pushed event |
| everything else | **live** |

Every refusal — no webhook, an unparseable webhook, no gamelogs folder, no
logs in the window, a Discord rejection — is composed in Python and
reported on the status strip. This is the posture the screen already
takes: `list.js` says it twice ("Sends unconditionally … a page-side early
return would swallow the one that says WHY nothing opened"), and
`panel.js` says it for `Upload`.

`#logs-note` keeps saying the no-webhook fact where it is true. It is now
a note beside a live control rather than a note beside nothing.

### Busy state — **[r2] a second predicate, not a wider one**

Revision 1 proposed widening `_busy()`. Rejected. `_busy()` is read by
`__main__.py:283` (`poll_tick`, to defer list rebuilds), by
`_confirm_quit_if_busy`, by `start_upload`'s guard, and as the default for
every `_status`/`_progress` push — and each of those writes a *different
sentence* about it. Widening it makes `format_quit_confirm` say "An upload
is N% complete" during a log post, where `_last_pct` is a stale number
from a previous job.

Instead:

- `_busy()` — unchanged. Still "an upload thread is alive". Every existing
  caller keeps its exact current meaning, including `poll_tick` (a log
  post touches no rows, so deferring the list for it would be a regression
  with no benefit) and Quit (a log post is seconds and loses a Discord
  post, not a multi-gigabyte transfer).
- `_logs_busy()` — new. "A standalone log-post thread is alive."
- `start_upload` additionally refuses on `_logs_busy()`, with its own
  sentence: `Combat logs are being posted. Try again in a moment.` — not
  "An upload is already in progress", which would be false.
- `post_recent_logs` refuses on either, each with its own sentence.

The `_status` default is left alone. The standalone worker passes `busy`
explicitly on every line, exactly as `_combat_log_worker` already does.

### Threading

- `post_recent_logs()` is a bridge method: it validates what it can
  without blocking, then dispatches a daemon thread. The bridge thread
  must not block, and `select_logs` walks the whole Gamelogs folder.
- **The thread handle is assigned before `.start()`**, as `start_upload`
  does (`api.py:1165-1169`). Otherwise a second click one millisecond
  later slips past `_logs_busy()`.
- The disabled state is pushed as `onLogPostRunning {running: bool}`
  **[r2]** — named for the fact, following `onCancelAvailable`'s precedent
  of naming the control's state rather than a vague availability.
- **The push is not the guard.** `_push` swallows every `evaluate_js`
  failure, and `_confirm_quit_if_busy`'s docstring records that a push into
  a *hidden* window is swallowed outright — this is a tray app whose window
  is routinely hidden. So a disarm can be lost and the button left dead for
  the session. Two defences, both required: the disarm is in a `finally` at
  the outermost frame, **and** `post_recent_logs` re-pushes the current
  state on every call, so a click on a wrongly-disabled button that arrives
  anyway (keyboard, stale render) both works and repairs the display.

### Reuse — **[r2] extract the preconditions, not just the summary**

Revision 1 proposed only making `_combat_log_worker`'s `summary` optional.
That leaves the *preamble* — parse the webhook, tell absent from
unparseable, resolve the gamelogs folder, handle "not found"
(`api.py:1650-1673`) — to be written a second time, in a codebase whose
stated rule is that anything written twice drifts.

- `_log_target() -> (hook, gamelogs_dir, error)`. Pure precondition
  resolution, no reporting. Both callers use it; each phrases its own
  error, because the upload tail must say "Combat logs skipped: …" via
  `_skip_logs` and the standalone post must not (there is no upload to be
  skipped *from*).
- `_combat_log_worker(..., summary: str | None)`. With a summary, every
  terminal line leads with it, unchanged — round 3's finding 13. Without
  one, the terminal lines stand alone: `Posted combatlogs-….zip (15 KB).`
  Finding 13's rule is *the primary action is said first*; here the log
  post **is** the primary action, so a bare sentence satisfies it.


## 2. Right-click › Play

- New `#ctxmenu` item opening the recording with the Windows shell default
  (`os.startfile`, behind the `sys.platform` check `open_recording_dir`
  already uses, so the module still imports on Linux for the suite).
- **[r2] Always enabled.** Revision 1 said "enabled whenever the row
  resolves to a file that exists … the same mechanism with a different
  predicate". It is not the same mechanism: `list.js:400-406` computes
  `has = !!(row && row.link)` from a field already in the row payload.
  Existence is not in `Row` (`ui/rows.py:32-51`), is not pushed, and cannot
  be learned synchronously in a `contextmenu` handler. Adding an `exists`
  field would be worse — `rebuild()` only ever emits rows for files that
  existed at scan time, so it would be `true` for every row, always. Under
  `WM.setEnabled`'s rule the app does *not* already know this cannot be
  carried out, so Play stays live and reports on the strip.
- Runs on a short-lived worker: `os.startfile` can block on a slow shell
  handler or a disconnected share, and the bridge thread must not.
- Failures land on the status strip, not a dialog, matching
  `open_recording_dir`'s stated reasoning: nothing is destroyed, nothing is
  half-done. `That recording is no longer there.` /
  `That file could not be opened.`
- No association for `.mkv` is **not** a failure: Windows shows its own
  picker and `os.startfile` returns cleanly. Nothing is reported.
- **Double-click is unchanged.** It still opens the YouTube link. Changing
  it is a question about the row's primary gesture, and was not asked for.

**Naming.** `Play`, no ellipsis: `DESIGN.md`'s `…` means *this opens a
surface you then act in* (`Browse…`, `Edit…`). Play completes the action,
like `Open in browser`, which carries none.

**Menu order and a separator.** The menu becomes two file actions then two
link actions, which act on different objects — the menu has until now read
entirely as "things you can do with the YouTube video". File actions
first (they act on the row's subject), then a `.ctxsep` rule, then
`Copy link` / `Open in browser`. The separator is a `<div>` with a border,
so it sets no display and needs no `[hidden]` override.

**Not in scope, recorded so the next reader does not think it was
missed:** the menu is mouse-only — there is no Shift+F10 or Menu-key
route, and `list.js`'s keyboard support (Tab, ↑/↓, Space) does not reach
it. Right-click is what was asked for.


## 3. Right-click › Rename…

### The dialog

`WM.prompt` (`panel.js`), never `window.prompt`. This is page-initiated,
so `Api._confirm` would deadlock the thread that has to deliver the
answer — `DESIGN.md`'s confirmation table is explicit.

- **[agreed]** Prefilled with the **stem** only; Wingman reappends the
  original extension. A user cannot turn `.mkv` into `.mp4` by typing,
  which would be a rename claiming a remux happened.
- Cancel (`null`) and an unchanged stem are no-ops.
- `ctxId` is captured before the dialog opens, because `hideMenu()` nulls
  it (`list.js:396`) — the bug `ctxCopy` already avoids by taking a local
  copy first.
- A rejected name re-opens the prompt with the typed text preserved, so a
  typo does not cost the whole name. The page sends and renders; it does
  not judge.

### Refusal, decided in Python

The page sends the raw stem; `rename_recording(row_id, stem)` decides and
returns `{ok, error}`. The page validates nothing, for the reason
`panel.js` already records about `start_upload`: a page-side early return
swallows the specific sentence Python composed.

| case | why |
|---|---|
| **an upload is running** | see below — this is the one that protects data |
| empty or whitespace-only | there is no name |
| contains `\` or `/` | a rename must not move the file |
| contains `< > : " \| ? *` or a control character | Windows will not create it |
| a trailing dot or space | Windows silently strips it, so the name you get is not the name you typed |
| a reserved device name (`CON`, `PRN`, `AUX`, `NUL`, `COM0`–`9`, `LPT0`–`9`, `CONIN$`, `CONOUT$`), checked on the **stem** | Windows reserves these, extension or not |
| `.` or `..` | `PurePath.with_name` raises `ValueError`, which would escape to the bridge |
| the target already exists | **never overwrite** |
| the row id is unknown | the list rebuilt under the dialog — see below |
| the file is gone | say so; it is a different sentence from the one above |
| `OSError` | in use, permissions, path too long |

**`Path.rename`, never `os.replace`. [r2]** Revision 1 wrote
"`os.replace`/`rename`" in the ordering paragraph while arguing two
paragraphs earlier that not overwriting is the point. `os.replace` is
`MoveFileExW` with `MOVEFILE_REPLACE_EXISTING` — it is precisely the call
that destroys the target recording. The pre-check exists to produce a good
sentence; `Path.rename`'s own `FileExistsError` is the actual protection.

**A stale row id is not "the file is gone". [r2]** `WM.prompt` resolves
seconds later, and a watcher poll landing in that window calls
`list_rows(preselect=…)`, which re-mints every id (`api.py:730-737`). The
rename then resolves to `None` while the file is sitting on screen. Two
states, two sentences: `The list refreshed while that dialog was open.
Try again.` versus `That recording is no longer there.`

**Case-only renames are NOT VERIFIED and are gated on a smoke result.
[r2]** `fight.mkv` → `Fight.mkv` is the rename a user is most likely to
want. Revision 1 asserted a `samefile`/normalised-case pre-check fixes it.
That fixes only the pre-check; whether `MoveFileExW` *without*
`REPLACE_EXISTING` itself succeeds for a case-only change on NTFS cannot
be established from a Linux worktree, and neither revision verified it.
Also, `Path.samefile` raises `FileNotFoundError` when the target does not
exist, which is the normal case, so the pre-check needs that branch or it
raises on every successful rename. The implementation therefore:

- compares with `os.path.normcase` equality first, and treats a
  case-only change as "not a collision" without calling `samefile`;
- carries a smoke item that performs one, on Windows, before this is
  called done. If `Path.rename` refuses it, the fallback is a two-step
  rename through a temporary name, and that is a decision to bring back
  rather than to improvise.

### Refused while an upload is running — **[r2] the defect revision 1 missed**

Revision 1 relied on Windows refusing to rename an open file. That holds
for a **plain** upload: `MediaFileUpload(str(path))` (`api.py:1409`) opens
without `FILE_SHARE_DELETE`. **It does not hold for a stitched upload** —
there the open handle is on the merged temporary (`api.py:1305-1316`), and
every source recording is closed the moment ffmpeg finishes. So during the
whole upload phase of a stitch the sources are freely renameable, and
afterwards:

```python
for row_id, item in zip(job.ids, job.items):
    self._link(row_id, vid, item)                                   # api.py:1319
...
links.remember(self._link_store, info.path, info.size, info.mtime, url)  # api.py:1222
```

`info` is the `VideoInfo` captured **before dispatch** — `UploadJob`'s
docstring says so, and `_link`'s docstring explains at length why it must
not re-resolve. So the URL is persisted under the pre-rename path,
`list_rows` looks it up under the post-rename path and misses, and the ↗
is gone permanently, because nothing rebuilds `links.json`
(`links.py`'s module docstring). `RetryState` holds the same stale items.

Migrating a running worker's captured state is the wrong fix. The rename
is refused for the duration:

> `That recording is part of the upload running now. The upload records
> its YouTube link against the current name, so renaming it now would lose
> the link.`

One predicate (`_busy()`), one sentence, and it closes the plain case too
rather than depending on a sharing side-effect that only one of the two
code paths happens to have.

### State that must move with the file

Four stores are keyed by path. A rename changes neither size nor mtime, so
each migration is a key move with the entry preserved.

| store | key | consequence of not migrating |
|---|---|---|
| `watcher.seen` | `str(path)` | the file looks new and is **announced as a finished recording**, days later, reading as a bug about OBS |
| `links` (persisted) | `str(path)` | the ↗ is lost, permanently — nothing rebuilds it |
| `durations` (persisted) | `str(path)` | one re-probe; cosmetic, free to carry |
| `RowSnapshot._links` | `Path` | **[r2]** the fourth, missed in revision 1 — it is what the *cell* renders from (`rows.py:139-163`) |

- `Watcher.rename(old, new)` — moves the `seen` entry and any `_pending`
  entry, then `_save()`. A new method rather than `forget(old)`, because
  `forget` is exactly what makes the watcher announce it again. Tolerates
  a missing source entry (does not invent one, does not leave `new`
  unseen) and `self._watcher is None`, which `_delete_worker` already
  does (`api.py:869`).
- `links.rename(store, old, new)` and `durations.rename(cache, old, new)`
  — key moves in the module that owns the key, each with that module's
  existing save posture (atomic; best-effort). **An existing entry at the
  destination is overwritten** — `lookup` validates `(size, mtime)`, so a
  stale orphan there can never match anyway, and orphans are expected
  (`links.py` prunes nothing).
- `RowSnapshot.rename(row_id, new_path)` — moves the in-memory link and
  rewrites the `Row`'s `name`.

**Ordering, and it is easy to get backwards:** migrate only *after*
`Path.rename` returns. A failed rename that has already moved keys leaves
four stores describing a file that does not exist. On failure, nothing is
touched.

**Thread safety. [r2]** `Watcher` has no lock. Today `forget()` races
`poll_once()` on one `pop`; rename adds a `pop`+insert *and* a `_save()`
whose payload is a dict comprehension over `self.seen` (`watcher.py:146`),
which can raise `RuntimeError: dictionary changed size during iteration`
against a concurrent write. The rename therefore runs **on the bridge
thread**, not a worker — it is a metadata operation measured in
milliseconds, there is no dialog to park on (the prompt has already been
answered by the time Python is called), and the bridge thread is the one
thread that cannot be running `poll_once`. The same reasoning covers
`self._cache`, written by the probe drain on the Scheduler thread.

### Repaint, do not rebuild — **[r2]**

Revision 1 called `list_rows()` and dismissed the cost as "selection is
dropped by that rebuild, as it is for any refresh". That understates it:
the only other refresh that drops a selection is Delete, which *consumed*
that selection, and `poll_tick` goes out of its way to defer refreshes
mid-upload precisely to avoid this (`__main__.py:286-292`). A rename is an
incidental action and must not silently clear a multi-row selection the
user has assembled, or the focus ring, or the sort position.

`list.js` already has the machinery: `repaint(id)`, which exists "so a
landing ffprobe result or a new link does not scroll the list or drop the
focus ring". So: `_push("onRowRenamed", {"id": row_id, "name": new_name})`,
and the page updates that row's `name` and repaints it. Ids are unchanged,
so selection, focus and sort survive.


## Bridge surface

Three new methods and one new handler. The handler name is a **three-way**
contract (`WM.HANDLERS`, the `_push`, the single `WM.handle` owner), and a
`WM.handle` of an unlisted name throws at registration and silently kills
every handler below it in that module.

| direction | name | owner |
|---|---|---|
| page → Python | `post_recent_logs()` | panel.js |
| page → Python | `play_recording(row_id)` | list.js |
| page → Python | `rename_recording(row_id, stem)` → `{ok, error}` | list.js |
| Python → page | `onLogPostRunning {running}` | panel.js |
| Python → page | `onRowRenamed {id, name}` | list.js |

**`dev.js` must double all three page→Python methods. [r2]**
`tests/test_dev_harness.py:85` compares the missing set against
`known_gaps` by **exact equality**, so an undoubled method fails the suite
and an entry left behind after doubling fails it too. Doubling is
preferred to a gap entry: `?dev=1` is the only way any of this is seen
outside Windows.


## Deliberately not in scope

- Trimming logs to the hour **[agreed]**.
- Any change to double-click, or a keyboard route to the context menu.
- Multi-row rename, or rename from the footer. The row is the object.
- A configurable window length. One hour was asked for.
- `INERT_NOTES["no_webhook"]` says "Settings › Discord"; round 5's E1
  renamed that section to `Uploading`. Real, user-visible, and **out of
  lane** — it is one word in a shared string with its own tests.
- `docs/smoke-checklist.md:1000-1002` claims the no-webhook note clears
  "with no restart", which no code path appears to deliver. Maintainer's
  call: not this change.
- Sweeping kept combat-log archives from `paths.tmp_dir()`. A repeatable
  button makes this a slow leak (only `stitch.sweep_orphans` sweeps that
  directory, and it does not know about these zips). Named as a known
  consequence, not fixed here.


## Tests

Nothing in the suite renders the page, so JS is covered lexically and the
real verification is the smoke pass.

**Python, behavioural**

- the window is `now-1h .. now`, tz-aware UTC, asserted on the *values*
  (`_require_utc` would reject naive input, so "it did not raise" proves
  little)
- each precondition failure produces its own sentence: no webhook,
  unparseable webhook, no gamelogs folder, no logs in the window
- `_log_target` is the single source of those three answers, used by both
  callers
- `_combat_log_worker` with `summary=None` emits standalone terminal lines
  and does not print "None"
- the post is refused while an upload runs, and an upload is refused while
  a post runs, **each with its own sentence**
- `_logs_busy()` is true before the worker starts, i.e. the thread handle
  is assigned before `.start()`
- the running flag is disarmed in a `finally` on every exit including a
  raised exception
- rename: every row of the refusal table; the collision case leaves the
  **target file byte-identical**; a case-only rename is accepted by the
  validator (the filesystem half is a smoke item)
- rename refused while an upload runs — asserted against a *stitched* job,
  which is the case that actually loses data
- rename migrates all four stores, and — the regression that matters —
  a renamed recording is **not** announced by the next `poll_once()`
- a failed rename leaves all four stores untouched
- rename pushes `onRowRenamed` and does **not** call `list_rows`
- `play_recording` resolves a row to its path, is a no-op off Windows, and
  reports the missing-file and `OSError` cases distinctly

**Lexical**

- `onLogPostRunning` and `onRowRenamed` are in `WM.HANDLERS`, pushed from
  `api.py`, and registered by exactly one module each
  (`test_bridge_contract.py`, `test_page_conventions.py`)
- the three new `WM.send` names exist on `Api` with matching arity, the
  way `test_start_upload_is_called_with_what_it_now_accepts` does
- `dev.js` doubles all three; `known_gaps` is unchanged
- the amended `test_the_upload_button_is_in_the_card_that_names_the_upload`
  carries the reasoning above in its docstring
- the new card's note still reads `INERT_NOTES["no_webhook"]` off the
  payload rather than a literal

**`docs/smoke-checklist.md`**

- post with a webhook, without one, and with a broken one
- post while an upload runs, and start an upload while a post runs
- play a real recording; play one deleted behind the app's back; play one
  still being written (expected to work, and to defer that recording's
  *announcement* by a poll or two, because a player's handle makes
  `watcher.file_is_closed` answer False)
- rename to a new name; to an existing name; **to a case-only variant**;
  during a stitched upload
- rename with a multi-row selection assembled, confirming the selection,
  focus ring and sort order survive
- the panel at 840×625 and at 200% scaling, confirming `Upload` is fully
  visible with the second card present


## Risks

1. **The watcher migration is the sharp edge.** Getting it wrong fails
   quietly and days later.
2. **The case-only rename is unverified** and is the most likely rename a
   user will attempt.
3. **A lost `onLogPostRunning` disarm** leaves a dead button; mitigated by
   the `finally` *and* the re-push on every call, not by either alone.
4. **A second card at the floor.** Bounded by placing it last, but the
   measurement is a smoke item, not arithmetic.
5. **Kept archives accumulate** in `tmp_dir()` on repeated failures.


## Corrections found during implementation

The design above is left as written. Four of its claims turned out to be
false or overstated once the code was in front of the review, and the
implementation follows this section where the two disagree.

1. **The bridge thread is not exclusive with the watcher poll.**
   `__main__.poll_tick` runs on the Scheduler's own thread, so a rename on
   the bridge thread CAN interleave with `Watcher.poll_once`. The design
   used that false exclusivity as the reason no lock was needed. The
   conclusion survives with a different argument: each mutation is a single
   dict operation, and `Watcher._save` now copies the map before walking it
   — without that copy, `save_seen`'s comprehension could raise
   `RuntimeError` and, uniquely on the rename path, escape across the
   bridge *after* the file had been renamed. The residual race is the one
   `Watcher.forget` has always had: at worst one extra announcement.

2. **A stitched rename would not have lost the link.** The design refused
   renames during uploads because `_link()` would persist against a path
   captured before dispatch. It would not: `UploadJob.items` holds the same
   mutable `VideoInfo` objects `RowSnapshot.rename` updates, so `_link`
   would read the new path. The refusal stays, for the real reason — the
   uploader reads a source path when it opens it, and on the plain path an
   open read handle turns the rename into a sharing violation the user
   reads as a Wingman failure — but the stated mechanism was wrong.

3. **`get_settings` is not fetched only at page load.** `web/list.js`
   re-fetches it whenever a rebuild returns an empty list. The reason not
   to gate the button on the webhook is unchanged and only slightly
   narrower: nothing *pushes* settings, and the refresh that exists never
   fires for a user who configures a webhook with recordings on screen.

4. **A re-push on every call cannot repair a lost disarm.** A button the
   page has drawn as `disabled` takes neither a click nor a keypress, so it
   cannot ask for its own repair — risk 3 above was only half-mitigated.
   `list_rows` therefore re-states the flag on every rebuild, which is what
   arrives without the user's help. `post_recent_logs` also releases its
   claim if the worker fails to start, which would otherwise latch the
   button for the life of the process.

One defect of the same kind was found in the validator: `rename_problem`
compared the whole stem against the reserved device names, so `CON.foo`
passed and was then refused by Windows with a message about a path that
cannot be found. It now checks the portion before the first dot.
