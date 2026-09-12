# Tray menu positioning design

## Status

Implemented; root cause and corrected placement were confirmed with a live
Windows probe. The full installed-release smoke matrix remains a release gate.

## Problem

Right-clicking Wingman's notification-area icon should open the native **Open
Wingman / Quit** menu beside that icon. Today, moving the Fleet Bar to another
monitor can cause the tray menu to appear around the middle of a screen instead.
The monitor containing the Fleet Bar must have no bearing on tray-menu
placement.

## Intended outcome

The tray menu opens beside the notification icon that received the click,
regardless of:

- the Fleet Bar's monitor or position;
- which Wingman window was most recently active;
- whether the main Wingman window is visible;
- monitor arrangement or display scaling.

Failure to obtain better placement information must not break the tray menu.

## Confirmed behavior and constraints

`wingman.__main__.build_tray()` delegates tray creation and menu handling to
`pystray.Icon`. Wingman resolves pystray 0.19.5 in `uv.lock`, and
`packaging/uploader.spec` explicitly collects `pystray._win32`.

On Windows, pystray 0.19.5's right-click handler:

1. calls `SetForegroundWindow(self._hwnd)` without checking its result;
2. reads screen coordinates with `GetCursorPos()`;
3. calls `TrackPopupMenuEx(...)` with `self._menu_hwnd` as the owner.

A live probe against the running installed app established the failing
boundary. With Wingman system-DPI-aware and its notification area on the 200%
primary display, Windows reported the icon rectangle in physical coordinates as
`(3434, 2064)–(3498, 2160)`. Triggering pystray's real right-click handler with
the physical cursor at `(3466, 2112)` produced a popup at
`(1563, 1009)–(1733, 1056)`: approximately half-scale and near the middle of the
logical desktop. The same probe using `GetPhysicalCursorPos` produced the popup
at `(3247, 2062)–(3466, 2112)`, adjacent to the cursor and icon.

The root cause is therefore pystray's DPI-virtualized `GetCursorPos` result being
passed to `TrackPopupMenuEx`, which consumes physical screen coordinates in this
process. The Fleet Bar's location exposes the problem but does not provide any
input to the correct placement. The split hidden-window ownership remains
unusual but was not implicated by the probe and will not be changed.

Wingman deliberately uses process-wide `PROCESS_SYSTEM_DPI_AWARE` behavior.
Changing that policy would require auditing every pywebview and native preview
window for per-monitor DPI changes and is outside this fix.

## Design

### Coordinate correction

Override only pystray's Windows right-click path and replace `GetCursorPos` with
`GetPhysicalCursorPos`. Preserve the existing foreground window, popup owner,
alignment flags, menu lifecycle, and descriptor dispatch—including pystray's
logged-error path for an invalid positive command ID. The right-click itself
already proves the cursor is at the notification icon, so physical cursor
coordinates provide the smallest direct correction without adding icon identity
or taskbar-edge policy.

If `GetPhysicalCursorPos` is unavailable or fails, fall back to pystray's current
`GetCursorPos` path. The fallback may retain incorrect placement under scaling,
but keeps the menu usable on an older or degraded Windows API surface.

### Integration boundary

A small Windows-only tray adapter will live in `wingman/ui/tray.py`. It will
retain pystray's icon lifecycle, menu construction, notifications, and callback
dispatch while overriding only right-click menu presentation. Left-click/default
activation must delegate unchanged.

`wingman.__main__.build_tray()` continues to own image loading and the **Open
Wingman / Quit** command wiring. The Windows DLL lookup and private pystray
backend import remain lazy so Linux test collection stays safe; the
platform-neutral `ctypes` structures are safe to import normally.

The adapter necessarily relies on private pystray details: `_hwnd`,
`_menu_hwnd`, `_menu_handle`, descriptor indexing, and the private Win32
wrapper. Pin `pystray==0.19.5` in `pyproject.toml` and retain the lock. Unit
tests cover Wingman's behavior through an injected backend; a Windows-only
contract test exercises the installed private backend, and any pystray upgrade
requires a Windows smoke pass.

### Failure behavior

Failure to obtain physical cursor coordinates degrades to pystray's existing
logical cursor lookup. A zero `TrackPopupMenuEx` result is cancellation or no
selection and invokes no callback, matching pystray. An out-of-range positive
command ID retains pystray's exception path so its dispatcher logs the backend
contract violation. Unexpected popup exceptions must not stop pystray's message
loop or Wingman.

No Fleet Bar code participates in placement. The Fleet Bar is a reproducing
condition, not an input to the solution.

## Alternatives considered

### Use a consistent popup owner

Rejected after diagnosis. It was a plausible initial hypothesis, but the live
probe isolated virtualized cursor coordinates and proved the physical-coordinate
substitution without changing ownership.

### Query the notification icon rectangle

Rejected for the current fix. `Shell_NotifyIconGetRect` would introduce icon-ID,
taskbar-edge, alignment, and overflow behavior that the direct physical-cursor
correction does not need.

### Adjust for the Fleet Bar's monitor or DPI

Rejected. It would preserve the incorrect coupling and fail when another
Wingman window becomes foreground.

### Change process DPI awareness

Rejected. Per-monitor DPI awareness is a cross-cutting change requiring
`WM_DPICHANGED` handling throughout pywebview and the native preview subsystem.

### Patch site-packages

Rejected. The patch would disappear on dependency installation and would not
reliably enter packaged releases.

### Upgrade or replace pystray

Not selected without evidence that another release fixes this behavior.
Replacing the tray implementation would broaden lifecycle and packaging risk.

## Implementation plan

1. Capture the native failure against the running Windows app and compare it to
   a physical-cursor variant.
2. Add regression tests for a narrow tray adapter:
   - right-click uses physical cursor coordinates;
   - native lookup failure falls back to pystray's logical cursor lookup;
   - left click delegates unchanged;
   - selection and cancellation preserve descriptor dispatch.
3. Implement the physical-coordinate override in `wingman/ui/tray.py` and wire
   it through `build_tray()` only on Windows.
4. Pin `pystray==0.19.5`, retain the existing frozen hidden import, and verify
   source and packaged imports.
5. Add a manual regression section to `docs/smoke-checklist.md` covering:
   - the original machine and exact reproduction sequence;
   - single-monitor control;
   - notification area on primary and secondary monitors;
   - supported bottom/top/left/right and auto-hidden taskbars;
   - equal and mixed scaling, including negative/staggered coordinates;
   - normal and overflow notification icon locations;
   - Fleet Bar interaction immediately before right-click;
   - main window hidden and visible;
   - menu dismissal, Open Wingman, Quit, and left-click/default activation;
   - Explorer restart followed by another right-click;
   - cursor fallback in an instrumented build if icon anchoring is required.
6. Run focused tests, Ruff lint and format checks, the executable JS smoke gate,
   and the full pytest suite with the repository's native settings codec
   prerequisite installed. Inspect skips rather than accepting Node/native
   skips as full coverage. Build and exercise the frozen Windows executable.

Automated tests prove argument selection, fallback, callback dispatch, and
integration contracts; they do not prove where Explorer renders a native menu.
The Windows acceptance pass is the regression proof.

## Adaptation point

If installed/frozen Windows validation shows that physical cursor coordinates do
not remain adjacent to the notification icon in a supported taskbar layout, stop
and revisit explicit `Shell_NotifyIconGetRect` anchoring. Do not add Fleet Bar or
main-window monitor state to the calculation.

## Explicit exclusions

- Fleet Bar placement, activation, or persistence changes.
- Application-wide DPI-awareness changes.
- A custom-rendered tray menu.
- Replacing pystray.
- Unrelated main-window or preview positioning changes.
