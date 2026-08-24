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
application already owns it — is reported to the page and shown against the
binding that failed. The parent design requires this explicitly: an unregistered
hotkey is a user-actionable condition, not a bug, and would otherwise be
experienced as "the feature silently does nothing".

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
   window.** `RegisterHotKey` is thread-affine and `UnregisterHotKey` must come
   from the same thread, so this is the invariant the module already enforces
   for HWNDs, not a new one. Registering against `self._hwnd` puts `WM_HOTKEY`
   in the existing pump, dispatched in `_host_proc` next to `WM_TIMER` and
   `WM_APP_SWEEP_NOW`. That window exists because it outlives every preview
   (`_create_host_window`'s docstring), which is exactly what a registration
   needs — chords must work when zero clients are running.
2. **`WM_HOTKEY` dispatch**: map the id to an action, resolve the target
   (per-character directly; cycle through `cycle.py` against the live client
   set), call `activate`. Registration ids stay inside the 0x0000-0xBFFF range
   Windows reserves for applications.
3. **Rebinding is wholesale.** `PostMessage` cannot carry a dict, so a settings
   change follows the pattern `_saved` already uses: the caller writes the
   desired table into a lock-protected field, then posts `WM_APP_REBIND`; the
   thread reads it and does unregister-all-then-register-all. Diffing
   registration state against a dozen entries is a bug farm for no measurable
   gain.
4. **Teardown gains its missing first step.** The parent design's Lifecycle
   section lists "unregister hotkeys" as step 1 and notes `_teardown` has no
   such step — harmless today because nothing registers one. It stops being
   harmless here: chords must be released before the window they are registered
   against is destroyed. The existing layout flush stays where it is, since it
   touches no HWND; the release goes ahead of the WinEvent unhook.

Registration failures are collected per bind and handed out through a callback
into `ui/api.py`, which pushes them to the page the same way auth state is
pushed today (`ui/api.py:_push_auth`).

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

The roster is appended on discovery of a character not already in it, and
written through `preview/store.py` — which gains a second recorded kind
alongside layouts, on the same debounce and the same merge discipline, rather
than a second writer being introduced. That module's two rules are load-bearing
here and are not restated in a second place: merge per key, and read the
settings document at write time rather than from a snapshot, because
`settings.save()` projects the complete document from `DEFAULTS` and the file
already has three writer threads.

**Only real character names enter the roster.** A client sitting at
character-select has no stable identity — `discovery.py` falls its `stable_key`
back to `hwnd:0x…` — and the parent design is explicit that such a client must
never have state persisted against it. A roster full of dead HWND keys would
also fill the bind list with rows naming nothing.

The cap exists so a corp that has flown fifty alts through one install does not
grow the settings file without bound. Eviction takes from the stale end of the
list, and a character that still holds a binding is never evicted.

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

Three bridge methods mirroring the bookmark ones: `capture_preview_bind`,
`parse_preview_bind`, `set_preview_binds`.

## Testing

The pure half carries the weight, on Linux, in CI — where the real bugs are.

- **`gestures`**: parse/display round-trip, `VK_` and hex forms, rejection of
  modifier-less chords, `MOD_NOREPEAT` present in every result, capture-event
  mapping, unknown `event.code`.
- **`cycle`**: wrap in both directions, missing anchor, empty set, single
  client, order stability as the client set churns.
- **`host`**: in the style `tests/test_preview_host.py` already uses — pure
  functions directly, lifecycle against fakes. Two behaviours pinned: rebind is
  unregister-all-then-register-all, and teardown releases chords before
  destroying the host window.
- **Settings validation** and the three bridge methods, alongside the existing
  `test_preview_*` and `test_api_settings.py`.

### What CI cannot tell us

New items for `docs/smoke-checklist.md`:

- A chord actually switches clients.
- A chord another application owns reports as a visible conflict rather than
  doing nothing.
- Holding a chord fires once, not at the repeat rate.
- Disabling previews releases the chords; re-enabling reclaims them.
- A binding survives a restart for a character that was offline at the time.

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

## Not in this slice

Named cycle groups, per-group chords, label customisation, alerts, switching
behaviour, client window layout save/restore, profiles, EVE-O import. Items 8
through 13 of the parent design, unchanged.
