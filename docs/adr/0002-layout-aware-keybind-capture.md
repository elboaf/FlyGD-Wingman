# Layout-aware keybind capture: resolve the produced character on the Python side

Keybind capture on a non-QWERTY Windows layout stored the wrong letter: the
page sends `event.code` (a hardware-position code, so Dvorak Ctrl+I arrives as
`KeyG`), and both capture paths translated position straight into the stored
key. AHK resolves character keys in a hotkey against the active layout at
registration time, so the stored `^+s`-style string already means "the key
that produces this letter" — the defect was only that capture wrote the wrong
letter into it. We therefore resolve the physical key to the character the
user's active layout produces **on the Python side of the bridge**, in one
shared resolver (Win32 `ToUnicodeEx` with the layout of the thread that
receives the keys) called by both capture paths, and keep the stored format
and registration machinery untouched.

## Decisions

- **Direction:** layout-aware capture (issue #305 direction 1). Press = label
  = key that fires, on any layout. A warning-only fix and a page-side
  `event.key`/Keyboard-Map fix were rejected: the former leaves Dvorak users
  on manual entry, the latter only covers bookmarks and re-opens the
  Shift+Comma trade-off the original design made.
- **One seam, both paths:** the resolver is a single Python seam (Win32
  through an injected seam, unit-testable off-Windows like the other seams).
  `capture_bind` and the preview capture both consume it, so they cannot
  disagree about what a key produces. Each capture function keeps its own
  position table, narrowed to a fallback role: degraded captures still need
  per-consumer position tokens (the two consumers keep different case
  conventions), and hand-typed entry validates through those same tables.
- **Layout consulted:** the foreground thread's — the one actually
  receiving the user's keys — resolved once per layout and cached, since a
  capture happens per keystroke.
- **Representation and migration:** the stored format does not change. Binds
  stay `^+s`-style AHK notation; preview hotkeys keep storing what they store
  today. No settings migration and no engine change: existing binds were
  already self-consistent ("the key that produces this letter"), and a bind
  captured wrong under a non-QWERTY layout is fixed by re-capturing it, not
  migrated.
- **Layout switches:** resolution happens at capture time and at registration
  time — never re-resolved live. This deliberately matches AHK's own
  documented semantics; a mid-session layout switch takes effect on the next
  engine reload. No `WM_INPUTLANGCHANGE` machinery.
- **Degradation:** a key with no single produced character (dead keys,
  multi-character or surrogate results, unbound keys) captures with the
  position-derived key and surfaces a visible one-line warning. Capture is
  never blocked on an edge case.

## Consequences

- The US-layout-assumption comments and trade-off notes in `bookmarks.py` and
  `preview/gestures.py` are obsolete once the shared resolver lands; the
  documented trade-off moves into this ADR.
- A bind's meaning depends on the layout active when the engine registered
  it, same as AHK itself; the "Edit…" manual entry remains the escape hatch
  for anything capture cannot map.
- `GetKeyboardLayout`/`ToUnicodeEx` need the layout of the thread that
  receives the keys (the WebView2 window's thread), not the caller's.
