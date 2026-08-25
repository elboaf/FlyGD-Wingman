# S3 handoffs — what wave 2 picks up

S3 (`ui/s3-backend`) touched no file under `web/`. Every user-visible
consequence of the lane is therefore waiting for a screen lane to render
it. This is the list, one section per lane, plus two questions for the
maintainer that S3 could not answer from inside its own boundary.

Findings owned by S3: M1, M2 (source half), M3, Profiles 3, Profiles 4
(bridge half), Uploader 8 (payload half), Uploader 12, Settings 1,
Settings 13, Settings 14 (guard half), Skills 8.

---

## R1 — Uploader (`list.js`, `panel.js:1-101`, `index.html #route-main`)

**Uploader 8 — remove the combat-log checkbox.** `start_upload` still
accepts its fifth argument and ignores it, so the page keeps working
either way and there is no ordering requirement between us. Delete the
control and stop sending the argument; `del logs` and the parameter come
out in the same commit that removes the caller, not before.

The sentence has to outlive the control. `Api._post_combat_logs` now
distinguishes never-configured (silent) from configured-and-broken (a
WARNING strip), because with no checkbox a "combat logs skipped" strip on
a webhook-less install would fire on every upload forever — the recurring
-failure strip `format_upload_confirm`'s docstring already records as a
past bug. **The no-webhook case is a fact about the install and belongs on
the panel**, where it is true all the time. `webhook_status` is already on
the settings payload; `INERT_NOTES["no_webhook"]` is the sentence, in the
same voice as the Previews one.

**Uploader 12 — confirmed, and it is yours to fix.** The cause is
`Api.set_folder`: it persists, rebinds the watcher and calls `list_rows`,
but never re-delivers the settings payload. `list.js:180`'s cached
`recordingDir` therefore keeps naming the *previous* folder while the scan
is of the new one, which is exactly the reported symptom — the named
folder is the one with the recordings, the configured one is empty.

S3 deliberately did **not** fix this by pushing `onSettings`. Python has
never pushed that handler; `app.js` invokes it off the *return value* of
the `get_settings` read, and `get_settings`' own docstring argues against
ever pushing the whole settings dict ("the same reason `detect_folder`
returns rather than pushes" — it discards unsaved edits in an open
Settings form). The cheap correct fix is on your side: **re-read
`get_settings()` when rows change**, or on route enter. One round trip, no
new bridge surface, no risk to the Settings form.

---

## R2 — Settings (`settings.js`, `bookmarks.js`, `previews.js`, `index.html #route-settings`)

**Settings 14 — disable `Show` and `Remove` on an unconfigured webhook.**
Entirely yours. S3 checked and the backend is already safe: `Show` is
purely client-side (`settings.js` toggles `input.type`, Python never sees
it) and `clear_discord_webhook` is already a no-op through
`_write_setting`'s guard. **No backend change was made, on purpose** — an
explicit refusal would be unreachable once you disable the buttons, and
strictly worse than the silent success it replaced. Use `WM.setEnabled`.

**Settings 1 — render the note from the payload, not from markup.**
`_settings_payload` now carries `inert_notes`, a dict from
`copy_mod.INERT_NOTES`. `index.html` currently hard-codes the Previews
sentence at the `#preview-binds-off` hint; swap it for
`payload.inert_notes.previews_off`. The whole table ships, not the one
entry that applies — which notes are showing is a render decision you make
from state you already have, and re-deriving that in Python would put the
predicate in two places.

Note the division with S1: `WM.setEnabled` settled *when a control is
disabled*; `INERT_NOTES` is *what the app says*. They are separate because
the Previews keybinds stay **live** under S1's rule (recording a keybind
for later is an action that can be carried out) while still needing to say
that nothing is registered yet.

**Settings 13 — no `<select>`.** The maintainer decided free string.
`set_category` is unchanged and still validates digits-only. The finding
collapses into your copy; nothing is waiting on S3.

**M2 / M3 — the `General` section.** Two payload keys are ready and have
no renderer:

- `payload.version` — the string from `__version__`. **S1 has already put
  this in the titlebar**, so read the open question below before building
  a second surface for it.
- `payload.start_on_login` — a bool, read live from the registry on every
  render. Commit through `set_start_on_login(bool)`, which returns the
  usual `{applied, persisted, error}`.

`set_start_on_login` has only two reachable outcomes and the docstring
says why: the registry entry is the whole state, so there is no in-memory
half that could apply while the write fails. You will get
`applied+persisted` or `applied False` with a reason — never
`applied True, persisted False`. **Do not add a branch for it.**

Refusals are real (a managed machine can deny the Run key by policy), so
render the error rather than assuming success. **Default is opt-in**: an
install that was never asked shows an unticked box, which is what reading
the registry gives you for free.

---

## R3 — Profiles (`evesettings.js`, `index.html #route-evesettings`)

**Profiles 4 — add the `Detect` button.** `eve_settings_detect_root()`
takes no arguments and returns the detected path, or `""` when it found
nothing or when the answer already matches what is set (it raises its own
`_alert` in both of those cases, so you render nothing extra).

It **commits**, unlike `detect_folder` on the Folders section. That is
deliberate: its neighbour `Choose folder…` writes the moment the dialog
closes, and a Detect that merely suggested beside a Choose that commits
would be two behaviours for one question on one screen. Treat its return
exactly like `eve_settings_pick_root`'s — same lock, same selection reset,
same shape.

**Profiles 3 — the count beside the button is yours; the copy half is
already done.** Round 1 replaced the `"3 other file(s)"` string;
`format_eve_copy_confirm` counts characters/accounts via `_copy_noun`.
What the finding still wants is a selection count *on the screen*, before
the modal. No bridge change needed — selection is client state and must
stay client state.

---

## R4 — Skills (`skills.js`, `index.html #route-skills`)

**Skills 8 — render `ch.fetched_label` and delete `formatFetched`.** Every
entry in `payload.characters` now carries a rendered label
("Last fetched 5h ago", or "Never fetched"), formatted through the same
`library.format_date` the Uploader's age column uses. `skills.js:400`'s
`toLocaleString()` goes.

`fetched_utc` is untouched beside it — you still need the raw value for
the staleness badge, so this is an addition, not a replacement.

---

## R5 — First run (`firstrun.js`, `index.html #route-firstrun`)

Nothing from S3.

---

## Two questions S3 could not answer from inside its boundary

**1. Where does the version actually live — and does the `ABOUT` card
still exist?** The walkthrough records M2 as decided: *"Version and licence
go in `General` as a second card headed `ABOUT`, alongside start-on-login;
version rendered as selectable text."* S1 shipped it in the **titlebar**
instead (#53, dimmed after the wordmark). Both are reasonable and the
payload serves either, but they are different decisions and only one of
them was written down.

This matters beyond the version: the recorded decision also gave `ABOUT` a
home for the licence (`THIRD-PARTY-NOTICES.md` still has no UI surface at
all, and GPL-3.0 attribution usually wants one) and for start-on-login.
The titlebar can hold none of that. **If the `ABOUT` card is still wanted,
R2 builds it and the version is deliberately in two places; if it is not,
start-on-login needs a home in `General` anyway and the licence question
goes back on the shelf.** Needs the maintainer, not a lane.

**2. `packaging/installer.iss` is the last hand-typed version, and it is
unowned.** `pyproject.toml` now derives from `__init__.py`; `uv.lock`
turned out to be carrying a fourth copy and now records none. Inno Pascal
cannot import Python, so `installer.iss` cannot be derived. It is guarded
twice — `ci.yml`'s check and a pytest — but no lane owns the file, so a
future version bump has no obvious owner for that edit.
