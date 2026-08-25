# Preview hotkeys

Design. Base: `main` (b2bac93), 2026-08-24. Implements deferred item 7 of
`eve-preview-design.md`.

## Outcome

A chord focuses a named EVE character. Two more chords cycle forward and
backward through the running clients. Bindings are set from the Previews tab,
survive a restart, and say so plainly when Windows refuses to register them.

This is what the parent design meant by "what makes previews fast to multibox
with rather than just pleasant to look at". Everything the feature needs at the
Win32 layer already exists: `win32.bind()` declares `RegisterHotKey` and
`UnregisterHotKey` (`preview/win32.py:235-236`), `WM_HOTKEY` is already defined
(`:46`), and the preview thread owns a real `GetMessage` pump — which the parent
design notes is the reason that thread has a pump at all.

## Decisions taken before designing

Four questions were settled first, because each one changes the shape of the
rest.

**Hotkeys are global, not scoped to EVE.** `RegisterHotKey` has no scoping: it
claims a chord desktop-wide. The alternative was to register on
`EVENT_SYSTEM_FOREGROUND` when a client takes focus and unregister when it
loses it — the hook is already installed (`preview/host.py:_install_hook`).
That was rejected. Commit `d57b96f` scoped every *bookmark* bind to EVE, but
that decision was about a system-wide keyboard hook injecting keystrokes into
a game; this is a handful of user-chosen chords that raise a window. Scoping
would also break the main case: switching *to* a client from a browser, which
is most of why a multiboxer wants the chord.

**One implicit cycle over all running clients**, not TriffView's named groups.
Two chords total, no group editor. The schema below is shaped so named groups
are additive later — today's two chords become the default group's — which is
the same trick the parent design used to defer profiles without a migration.
Per-character chords already cover "jump to a specific character", which is
what groups are usually a workaround for.

**Preview binds get their own gesture format** (`Ctrl+Alt+F1`), not AutoHotkey
strings. The two consumers are unrelated: bookmark binds are AHK strings
because an AHK engine consumes them literally, while these parse to
`(MOD_* flags, virtual-key)` for `RegisterHotKey`. Reusing AHK syntax would
import constraints that have nothing to do with previews — `preview/discovery.py`
already documents one such leak, where bookmarks reject `=` purely because
their INI cannot carry it. Translation is also lossy both ways: AHK expresses
chords `RegisterHotKey` cannot, and vice versa.

**Characters are bound from a persisted roster.** A character can only be named
while it is running, so binding an alt that flies on weekends would otherwise
require logging it in. `preview.layouts` is keyed by character but is written
only on a rect change, so a preview that was never dragged has no key — it is
not a roster. A free-text field was rejected: a typo yields a chord that
silently does nothing forever, which is exactly the failure mode the parent
design says to surface rather than allow.

## Behaviour

**Focus.** A per-character chord activates that client through
`preview/window.py:activate` — the `AttachThreadInput` sequence with strictly
balanced detach, already implemented and verified against real clients. Hotkeys
simply give it a second caller alongside the mouse click. A chord whose
character is not running does nothing, and that is correct: there is no window
to raise.

**Cycle.** `cycle.py` is pure — `(ordered_keys, anchor) -> key`. Order is
characters sorted by name, deliberately *not* discovery order, which reshuffles
as clients come and go and would make "next" mean something different between
two presses.

The anchor is the currently-foreground EVE client when there is one. That makes
the common case self-correcting and stores no state at all. The host keeps a
last-cycled key only for when focus is elsewhere — a browser, Wingman itself —
and falls back to the first key when that character has logged off.

No index is ever stored. An index is the obvious implementation and it is
wrong: the client set changes every 700ms, so a stored index silently points at
a different character the moment anyone logs in.

**Degraded state.** A chord Windows refuses — almost always because another
application already owns it — is shown against the binding that failed. The
parent design requires this explicitly: an unregistered hotkey is a
user-actionable condition, not a bug, and would otherwise be experienced as
"the feature silently does nothing".

**Reporting it by push alone would lose it.** `api.start_previews_if_enabled()`
runs at `__main__.py:409`, two lines *before* `window = window_mod.create(api)`
— deliberately, because `window_mod.run()` blocks. So the first registration
happens before `self._window` exists, and `_push` swallows that failure at
debug level (`ui/api.py:250-255`). `_push_first_run_when_ready` documents this
exact trap for its own case.

Registration status is therefore **state, not an event**: the host holds the
outcome of the most recent registration pass, a fourth bridge method returns it
on demand, and the page reads it as part of the settings payload it already
requests once at load (`web/app.js:146-147`). Pushes stay, for changes that
happen while the page is up — but nothing depends on one arriving. Failures are
also logged, as the parent design's observability list requires.

**Disabling previews releases every chord.** The subsystem starts lazily, so
there is no thread, no pump, and no registration until the feature is enabled.
This is correct — the chords act on preview targets — but it means "my hotkeys
stopped working" has "previews are off" as its first answer, and the UI must
make that legible rather than showing a bind list that looks live.

## The cross-feature hazard

Preview chords are global; bookmark chords are AHK hotkeys scoped with
`#HotIf WinActive` to EVE. If the two share a chord, **the preview bind wins
while EVE is focused** — silently taking a key away from the bookmarks feature
in precisely the situation that bind was written for.

Windows will not report this: `RegisterHotKey` succeeds, because AHK's scoped
hotkey is not a `RegisterHotKey` registration it collides with. Only Wingman
can catch it, and only by looking at both sections of its own settings.

The bind UI therefore checks a proposed chord against other preview binds *and*
against `eve_bookmarks.keybinds`, and flags the clash. Neither feature does a
cross-tab check today.

**The check is conditional, or it cries wolf.** Bookmark binds are registered
only against window titles the user enabled, and only when the feature itself
is on (`engine/eve_bookmarks.ahk:591-627`, `settings.py:105-133`). Treating
every configured bookmark chord as an active collision would warn about chords
that are not registered anywhere. So the warning fires when `eve_bookmarks` is
enabled *and* its enabled-window set is non-empty.

The collision does not stop existing when those conditions are false — it goes
latent, and enabling bookmarks later resurrects it with nothing on screen to
explain why that bind stopped working. The bind list therefore still marks a
shadowed chord when bookmarks are off, distinctly from an active clash and
without the warning styling.

## Architecture

Two new pure modules; inside `preview/`, only `host.py` and `store.py` change.
`window.py` and `chrome.py` are untouched, which is what keeps this slice clear
of the files the other deferred items want. Outside the package, the change
reaches `settings.py`, `ui/api.py`, and the Previews tab.

### `preview/gestures.py` — pure, Linux-testable

`Gesture(mods, vk)` plus three functions:

| Function | Purpose |
|---|---|
| `parse("Ctrl+Alt+F1")` | Typed entry; also accepts `VK_F1` and hex forms |
| `display(g)` | Back to the canonical string, for the UI |
| `from_capture({ctrl, alt, shift, meta, code})` | The browser capture path; owns the `event.code` -> virtual-key table |

Two validation rules, both guards rather than preferences:

- **At least one modifier is required.** `RegisterHotKey` will accept a bare
  `F1` and claim it desktop-wide, in every application, until the process
  exits. That is a footgun, not a feature.
- **`MOD_NOREPEAT` (0x4000) is always set.** Without it, holding a chord posts
  `WM_HOTKEY` at the keyboard repeat rate and each one runs a full
  foreground-switch sequence. Invisible when testing with a tap; awful in a
  fight.

`settings.py` imports this module for validation, exactly as it already imports
`preview.layout`. It must therefore stay import-safe off Windows — it is pure,
so this is a constraint to preserve, not work to do.

### `preview/cycle.py` — pure, Linux-testable

Ordering, wrap-around in both directions, anchor resolution. Around thirty
lines, and most of the test weight of this slice.

### `preview/host.py` — the modified Win32 module

1. **Registration happens on the preview thread, against the message-only host
   window.** Presented as an ownership invariant rather than a Win32 rule:
   `RegisterHotKey` identifies a registration by `(hWnd, id)` and does not
   document a same-thread requirement, so this is the module's own discipline —
   every Win32 touch on one thread — not something Windows compels. Keeping it
   makes lifetime obvious and matches the rule the parent design already sets
   for HWNDs. Registering against `self._hwnd` puts `WM_HOTKEY` in the existing
   pump, dispatched in `_host_proc` next to `WM_TIMER` and `WM_APP_SWEEP_NOW`.
   That window exists because it outlives every preview
   (`_create_host_window`'s docstring), which is exactly what a registration
   needs — chords must work when zero clients are running.
2. **A retained client registry.** `_sweep` builds its `clients` map and
   discards it, keeping only `_windows` — and `_windows` holds only clients
   whose window creation *succeeded* (`host.py:195-221`, the `if win is not
   None` guard). Resolving a hotkey against `_windows` would therefore silently
   fail for a client that is running and discovered but whose preview could not
   be created, which is the case where a keyboard shortcut is most useful.
   The sweep instead keeps the discovered set, refreshed every pass, and
   hotkeys resolve against that.

   Refreshing wholesale each sweep also fixes a latent staleness: `reconcile`
   compares stable keys only, so a character that reappears on a **new HWND**
   between two sweeps counts as "kept" and its retained record would point at a
   dead window. Keys survive; HWNDs are re-read.
3. **`WM_HOTKEY` dispatch**: map the id to an action, resolve the target
   (per-character directly; cycle through `cycle.py` against the client
   registry), call `activate`. Registration ids stay inside the 0x0000-0xBFFF
   range Windows reserves for applications.
4. **Rebinding is wholesale.** `PostMessage` cannot carry a dict, so a settings
   change follows the pattern `_saved` already uses: the caller writes the
   desired table into a lock-protected field, then posts `WM_APP_REBIND`; the
   thread reads it and does unregister-all-then-register-all. Diffing
   registration state against a dozen entries is a bug farm for no measurable
   gain.
5. **Teardown gains its missing first step.** The parent design's Lifecycle
   section lists "unregister hotkeys" as step 1 and notes `_teardown` has no
   such step — harmless today because nothing registers one. It stops being
   harmless here: chords must be released before the window they are registered
   against is destroyed. The existing layout flush stays where it is, since it
   touches no HWND; the release goes ahead of the WinEvent unhook.

Registration outcomes are held on the host as the current status of the last
pass — readable on demand, not only announced — for the startup-ordering reason
given under Degraded state. A callback into `ui/api.py` additionally pushes
changes for a page that is already up.

**The client registry needs a path to the page too.** The bind list orders
running characters first, and nothing carries "who is running" out of the
subsystem today: `_settings_payload` returns persisted settings only
(`ui/api.py:995-1014`), and the page asks for it once at load. The host
therefore reports its discovered character set on change through the same
callback the registration status uses, and the payload the page reads at load
carries a snapshot of it. Ordering degrades to "characters with bindings, then
the roster" when that snapshot is empty, which is exactly the state before
previews are enabled.


## Settings

Under the existing `preview` section, so `validated_preview` keeps ownership of
the whole subtree:

```
"hotkeys": {"characters": {},      # "Scout Alt" -> "Ctrl+Alt+F1"
            "cycle_next": "",
            "cycle_prev": ""},
"seen":     []                     # roster, most-recent-first, capped at 64
```

The two flat cycle chords become the default group's chords when named groups
land — additive, no migration.

`validated_preview()` extends with the posture already established there and in
`preview/layout.py`: a malformed `hotkeys` section falls back whole, a single
unparseable gesture drops alone. A hand-edited settings file should cost one
binding, not the launch.

The roster is a list, **most-recently-seen first**. A character already present
is moved to the front rather than left where it was; a new one is inserted at
the front. Eviction takes from the tail, and a character that still holds a
binding is never evicted. Stating this precisely matters because the earlier
draft said "most-recent-first" while describing an append, which leaves
"evict the stale end" pointing at the newest entry.

The cap exists so a corp that has flown fifty alts through one install does not
grow the settings file without bound.

**Only real character names enter the roster.** A client sitting at
character-select has no stable identity — `discovery.py` falls its `stable_key`
back to `hwnd:0x…` — and the parent design is explicit that such a client must
never have state persisted against it. A roster full of dead HWND keys would
also fill the bind list with rows naming nothing.

### Prerequisite: the stale-snapshot rule is already broken

The roster is written through `preview/store.py`, on its debounce and its merge
discipline. That module's two rules are load-bearing and are not restated in a
second place: merge per key, and read the settings document at write time
rather than from a snapshot.

**But one existing writer does not follow the second rule, and this slice must
not add a third participant until it does.** `ui/api.py:1055` builds
`cfg = dict(self._state.settings)`, mutates it, and saves it — a copy read
before the write, which is precisely what the parent design forbids: *"No
writer may serialize a stale snapshot… it must never rebuild the document from
a copy it read earlier."* `_SAVE_LOCK` (`settings.py:180-189`) does not close
this: it serializes the *write*, not the read-modify-write around it. A save
from the settings pane can therefore land on top of a roster or binding change
that was made after its snapshot was taken, reverting it with no error and no
log line.

This is a pre-existing violation of the parent design, not something this slice
introduces — but this slice makes it reachable from a second direction and much
easier to hit, because the roster writes on discovery rather than only when a
user acts. **Fixing it is step one of the plan**, ahead of any hotkey code:
either extend the lock to span read-modify-write, or make `ui/api.py` mutate the
live dict rather than a copy. The narrower second option matches what
`set_preview_enabled` already does at `ui/api.py:1236`.


## UI

This slice establishes the Previews tab's structure — today it is one checkbox
— and the deferred items that follow fill into it. That makes the tab's shape a
coordination point, not a detail.

Enable stays at the top. Below it, a Hotkeys section: two fixed rows for cycle
next and previous, then one row per character — running characters first, then
known-but-offline, then any binding whose character is in neither list.

Each row reuses the shape at `web/bookmarks.js:140-230`: a capture button that
reads "Press a key…", a **Clear**, and a **Type…** escape hatch. That pattern
is not copied for consistency alone — it already solves the non-US-layout
problem, where `event.code` maps a physical key to the wrong character, and it
routes both entry paths through the same Python validation so capture and
typing cannot disagree.

Four bridge methods: `capture_preview_bind`, `parse_preview_bind` and
`set_preview_binds` mirroring the bookmark ones, plus `get_preview_hotkey_state`
returning the current registration outcomes and the live character set. The
fourth exists because status must be *readable*, not only announced — see
Degraded state.

## Testing

The pure half carries the weight, on Linux, in CI — where the real bugs are.

- **`gestures`**: parse/display round-trip, `VK_` and hex forms, rejection of
  modifier-less chords, `MOD_NOREPEAT` present in every result, capture-event
  mapping, unknown `event.code`.
- **`cycle`**: wrap in both directions, missing anchor, empty set, single
  client, order stability as the client set churns.
- **`host`**: in the style `tests/test_preview_host.py` already uses — pure
  functions directly, lifecycle against fakes. Four behaviours pinned: rebind is
  unregister-all-then-register-all; teardown releases chords before destroying
  the host window; the client registry survives a failed window creation, so a
  chord still resolves for a client with no preview; and registration status is
  readable after a pass that happened before any window existed.
- **Roster**: a re-seen character moves to the front, a bound character is never
  evicted, and `hwnd:0x…` keys never enter.
- **Settings validation** and the four bridge methods, alongside the existing
  `test_preview_*` and `test_api_settings.py`.
- **The prerequisite**: a settings-pane save that races a roster write loses
  neither. This is a regression test for the fix, and it fails on `main` today.

### What CI cannot tell us

New items for `docs/smoke-checklist.md`:

- **LOAD-BEARING: `WM_HOTKEY` actually reaches a message-only window.** See
  risk 4 — if it does not, the whole dispatch path moves.
- A chord actually switches clients.
- A chord another application owns reports as a visible conflict rather than
  doing nothing.
- Holding a chord fires once, not at the repeat rate.
- Disabling previews releases the chords; re-enabling reclaims them.
- A binding survives a restart for a character that was offline at the time.
- **A conflict present at launch is visible on the Previews tab**, not only in
  the log — the startup-ordering case that motivated readable status.

The five smoke items already outstanding from `eve-preview-design.md` — a
client closing mid-session, all clients closing, a client starting, a
never-previewed character getting a free slot, and the frozen build's font —
are **not** in this slice and remain outstanding.

## Risks and open questions

1. **`MOD_WIN` chords.** `RegisterHotKey` accepts them, but Windows itself owns
   a large share of `Win+`key, and the ones it owns cannot be taken. Allowed,
   but the conflict report is the only thing standing between a user and a
   chord that looks bound and never fires.
2. **Registration failure is reported once, at registration.** If another
   application claims a chord *later*, our registration is unaffected — but if
   it claimed one first and then exits, ours does not retroactively succeed.
   Rebinding, or toggling previews, is the recovery. Whether that deserves a
   periodic retry is deliberately left open; it should not be built on
   speculation.
3. **The roster grows from discovery, so it learns a character only while that
   character is logged in.** A fresh install therefore starts with an empty
   bind list, which is correct but worth saying out loud, because the natural
   first action after enabling previews is to look for the bind list.
4. **`WM_HOTKEY` delivery to a message-only window is unverified.** The design
   registers against `self._hwnd`, created with `HWND_MESSAGE`. Message-only
   windows receive posted messages but are excluded from broadcasts, and
   nothing here has been run on Windows — this rests on a documentation
   reading, not a measurement, which is a weaker footing than the rest of the
   parent design's Win32 claims earn. It is first on the smoke list for that
   reason.

   The fallback if it fails costs little: register with `hWnd=NULL`, which
   posts `WM_HOTKEY` to the *calling thread's* queue. That is the preview
   thread, whose pump already dispatches unowned messages — but note the
   dispatch then happens in the pump loop rather than in `_host_proc`, since a
   thread-queue message has no window to route to.

## Not in this slice

Named cycle groups, per-group chords, label customisation, alerts, switching
behaviour, client window layout save/restore, profiles, EVE-O import. Items 8
through 13 of the parent design, unchanged.
