# Tray menu DPI verification

## Regression and scope

PR #219's physical-cursor adapter is present and active in the affected installed
5.6.3 build. A live inspection of its `show_windows_menu` frame found
`x=3466, y=2112`, with no logical-cursor fallback. An independent per-monitor-aware
observer measured the resulting native menu at `(1563,1009)–(1733,1056)`, while
`Shell_NotifyIconGetRect` placed the notification icon at
`(3434,2064)–(3498,2160)`. Both hidden tray windows remained system-aware.
These installed-app measurements are distinct from the reduced-harness samples
below: menu widths (and therefore left edges) differ. The regression is the same
half-scale right/bottom anchor, not a shared left-edge measurement.

A standalone pystray process did **not** reproduce this failure. Adding
pywebview 6.2.1's WinForms startup and a secondary-display window reproduced it.
That missing integration condition explains why a physical-coordinate argument
assertion and a standalone native popup probe were insufficient regression tests.

`ui/tray.py` now temporarily enters `PER_MONITOR_AWARE_V2` **after** foreground
activation, around cursor acquisition and `TrackPopupMenuEx`. It restores the
previous opaque thread context in `finally`, **before** dispatching Open/Quit.
The process DPI policy, hidden-window creation, message loop, menu ownership,
left-click activation and callback wiring are unchanged. Missing/rejected DPI
overrides retain the old usable path and log a warning that placement may be
scaled; a restoration failure is logged as an error.

The relevant Windows contracts are [mixed-mode DPI awareness][mixed] and
[`SetThreadDpiAwarenessContext`][setter]. [`TrackPopupMenuEx`][popup] documents
screen coordinates, not a promise that physical coordinates are interpreted
independently of the caller's DPI context.

[mixed]: https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-improvements-for-desktop-applications
[setter]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext
[popup]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-trackpopupmenuex

## Repeatable native placement check

Run `scripts/tray_menu_smoke.py` from an **interactive Windows desktop**, with the
checkout's dependencies installed. This is deliberately not a headless pytest
case. It creates temporary blank WebView windows and pystray-owned hidden
windows, exercises Wingman's production adapter through native notification
messages, measures the actual popup with a per-monitor-aware observer, and
cancels it. It never starts Wingman's application runtime or loads its settings.
Keep the pointer idle until the check finishes; it is temporarily moved and then
restored. The callbacks are harmless test callbacks, not the app's Open/Quit.

Use physical desktop coordinates for `--anchor`, well inside the chosen display
and with room above/left for a right/bottom-aligned menu. `--secondary` positions
a second blank WebView window using pywebview's window-coordinate convention;
choose a position on the other display in your layout. For the reproducing
3840×2160, 200%-scaled primary with a 100%-scaled display to its left:

```powershell
uv run --no-sync python scripts/tray_menu_smoke.py --anchor 3466 2112 --secondary -600 600
uv run --no-sync python scripts/tray_menu_smoke.py --anchor -500 1600 --secondary -600 600
```

The smoke check must return success for repeated opening and cancellation,
physical popup alignment, unchanged system-aware native owners, and restored
caller context. A passing argument-only unit test does not substitute for this
check. The unit tests separately cover callback dispatch, cancellation, cursor
fallback, exceptions, unsupported DPI overrides, and restoration failures.

## Observed experiment results

All observations below used an independent `PER_MONITOR_AWARE_V2` observer and
real `TrackPopupMenuEx`, with WinForms/WebView startup:

| Hidden owners | Context at menu display | Physical anchor | Observed popup rectangle |
| --- | --- | --- | --- |
| System-aware | System-aware (before correction) | `(3466,2112)` | `(1568,1009)–(1733,1056)` |
| System-aware | Temporary per-monitor V2 | `(3466,2112)` | `(3136,2018)–(3466,2112)` |
| Per-monitor V2 | Per-monitor V2 (comparison only) | `(3466,2112)` | `(3136,2018)–(3466,2112)` |
| System-aware | Temporary per-monitor V2 | `(-500,1600)` | `(-682,1550)–(-500,1600)` |

The system-aware-owner comparison established that changing the hidden windows
is unnecessary. The shipped adapter was then exercised with its caller still
system-aware and reproduced the corrected rectangles on both displays.

## Frozen harness check

The same script was built with the repository-pinned PyInstaller and run as an
executable, using the production adapter collected into its archive:

```powershell
uv sync --locked --extra dev --group build
uv run --no-sync python -m PyInstaller --noconfirm --clean --onedir --paths . --hidden-import pystray._win32 --hidden-import webview.platforms.edgechromium --exclude-module tkinter --specpath build/tray-smoke-spec --workpath build/tray-smoke --distpath dist/tray-smoke scripts/tray_menu_smoke.py
.\dist\tray-smoke\tray_menu_smoke\tray_menu_smoke.exe --anchor 3466 2112 --secondary -600 600
.\dist\tray-smoke\tray_menu_smoke\tray_menu_smoke.exe --anchor -500 1600 --secondary -600 600
```

Both source and frozen runs passed twice per anchor, with the corrected
rectangles above, system-aware owners and restored caller context. A negative
control running this same script against the unchanged #219 adapter failed the
physical-anchor assertion and exited nonzero. This validates the **reduced frozen
WinForms harness**, not an installation of the full Wingman application.

## Remaining release acceptance

The native smoke harness does not replace the [installed-release checklist][smoke].
Before release, exercise the actual frozen app with its notification icon visible
and in overflow, main window hidden/visible, Fleet Bar interactions, outside-click
and Escape dismissal, Open/Quit and left-click activation, Explorer restart,
auto-hide and supported taskbar edges. Do not mark that matrix complete from a
standalone pystray test or this reduced WinForms harness.

[smoke]: ../smoke-checklist.md#notification-area-menu-placement
