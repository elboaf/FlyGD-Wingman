# Windows dependency inventory

Input to the Linux-port feasibility question answered in
[cross-platform-feasibility-research.md](cross-platform-feasibility-research.md).
This file is the code-level half: every Windows-specific coupling in the
tree, what it does for the app, and whether a Linux equivalent exists.
Platform-level research (Wayland, portals, EVE-on-Wine, packaging) lives in
the companion file; this file stays at the source level. Snapshot: commit
f032e45, October 2026.

Method: grep of `wingman/`, `packaging/`, `engine/` datas and `tests/` for
`ctypes.windll` (user32/kernel32/gdi32/dwmapi/shell32/crypt32),
`RegisterHotKey`/`SetWinEventHook`/`GetMessage`/`PrintWindow`/`BitBlt`,
`winreg`/`LOCALAPPDATA`, pywin32, pystray/webview backend selection,
`winsound`/`msvcrt`/`os.startfile`, AHK supervision, installer and CI
configuration, plus read-through of the modules named below. Notable
negative result: **no pywin32 anywhere** — the entire Win32 surface is raw
ctypes, lazily bound, which is why the suite already runs on Linux.


## Verdict

- **Portable today** (pure Python or already seamed): upload/OBS→YouTube,
  stitching, fleet sharing, telemetry parsing and alert rules, skills and
  fittings logic, settings store, bookmark notation. Only
  `os.startfile`/`webbrowser`/`winsound`/ffmpeg-suffix touchups needed.
- **Trivial-to-moderate ports** (degrade or injectable on Linux already):
  tray, autostart, single-instance + raise, preflight, state paths, DPAPI.
- **The real port**: previews/overlay + fleet bars + frameless chrome —
  DWM thumbnails, layered windows, `RegisterHotKey`, WinEventHook,
  message-pump host and WndProc chrome have no cross-platform equivalent,
  and several are impossible by design on Wayland.
- **Blocked as shipped**: the AutoHotkey bookmark engine — but the seam
  (INI in, `eve_status.json` out) is clean, so a Linux automation engine
  can be slotted in without touching `hotkeys.py`' public interface.
- **Does not port**: the distribution chain (Inno Setup + WebView2
  bootstrapper + Windows PyInstaller bundle). Running from source or a new
  Linux bundle format is the path.


## Entry point / process

| Location | Mechanism | Purpose | Linux equivalent | Difficulty |
| --- | --- | --- | --- | --- |
| `wingman/__main__.py:124` | `CreateMutexW` + `GetLastError==183` | single instance (new + legacy 3.x names) | lockfile / D-Bus name | moderate — seamed (`_create_mutex`, off-Windows returns `object()` at :155) |
| `wingman/__main__.py:187` | `SetProcessDpiAwareness(1)` | system-DPI-aware process contract | no direct; toolkit/Wayland scaling | moderate — whole geometry model assumes it (`ui/window.py:147`, `ui/sigbar.py:52`) |
| `wingman/__main__.py:243` | `pystray._win32.Icon` adapter | tray icon + DPI-correct menu | pystray appindicator/GTK | trivial — attached only `if sys.platform == "win32"` |
| `wingman/__main__.py:395, 694` | platform gates | preview host / telemetry build return None off-Windows | n/a (the gates) | trivial — but note: telemetry `None` orphans Fleet/alerts surfaces on Linux |
| `wingman/__main__.py:1017` | `HotkeyEngine(paths.engine_exe(), …)` | spawns AHK, state_dir as cwd | no (see hotkeys) | blocker for the feature |


## Previews / overlay (largest coupling)

`wingman/preview/win32.py:1` is the seam: the ctypes declaration surface
for user32/gdi32/dwmapi/kernel32, lazily bound so the package imports on
Linux (asserted by `tests/test_preview_win32.py`).

| Location | Mechanism | Purpose | Linux equivalent | Difficulty |
| --- | --- | --- | --- | --- |
| `preview/thumbnail.py:29` | `DwmRegisterThumbnail`/`Update`/unregister | live DWM thumbnail of each EVE client | no direct (X11 XComposite hacks; none on Wayland) | blocker |
| `preview/host.py:2964, 3154, 3297` | own thread, `GetMessageW` pump, message-only `CreateWindowExW`, `SetWinEventHook` | hotkeys, timers, EVE window tracking | GLib/X11 event loop re-architecture | hard→blocker |
| `preview/host.py:4023, 3981` + `preview/gestures.py:16` | `RegisterHotKey`/`UnregisterHotKey` | global preview hotkeys | X11 XGrabKey; Wayland portal-only | hard |
| `preview/host.py:2919` | `SetThreadDpiAwarenessContext(V2)` | per-thread DPI isolation | no | moderate (drops with DPI model) |
| `preview/host.py:4331, 4426` | `ShowWindowAsync(SW_SHOWMINNOACTIVE)`, `IsIconic` | opt-in minimize of live clients | X11 yes; not on Wayland | hard |
| `preview/layered.py:39` + `alertframes.py:122` | `UpdateLayeredWindow` + GDI DIB composition | per-pixel-alpha chrome + alert flash frames | Cairo/ARGB rewrite (`alertframes.py:6` already says "prefer GDI+ path rather than porting") | hard |
| `preview/window.py:1092` + `cropwindow.py`, `companionwindow.py`, `regionpicker.py` | raw HWNDs: `RegisterClassW`, `SetCapture`, `TrackPopupMenuEx`, `WM_DPICHANGED` | preview/crop/region/companion windows — the product surface | GTK/Qt reimplementation | blocker |
| `preview/discovery.py:153` | `GetWindowThreadProcessId`, `OpenProcess`, `QueryFullProcessImageNameW`, `exefile.exe` match | enumerate EVE client windows | X11 `_NET_WM_PID` + /proc; not on Wayland | moderate |
| `preview/sources.py:59, 95, 111, 159` | image-name query, `DwmGetWindowAttribute` cloak check, `EnumWindows` | client catalog / sweep | same as above | moderate |
| `preview/companionfamily.py:79, 846, 872` | `GetCurrentProcessId`, `GetForegroundWindow` | focus probe for alerts/selection | `_NET_ACTIVE_WINDOW`; not on Wayland | moderate |
| `preview/host.py:3862, 4700, 4735` | `DwmGetWindowAttribute`, `GetSystemMetrics`, `EnumDisplayMonitors` | desktop geometry, monitor enumeration | Xinerama/Randr; Wayland portal | moderate |
| `preview/host.py:814, 4286, 4666` | `SetTimer`/`KillTimer` on pump HWND | scheduler inside preview thread | `threading.Timer` (ui/scheduler.py pattern) | trivial |


## UI shell / platform services

| Location | Mechanism | Purpose | Linux equivalent | Difficulty |
| --- | --- | --- | --- | --- |
| `ui/chrome.py:23, 243, 628` | `SetWindowLongPtrW` WndProc subclass, `WM_NCHITTEST` | resize border + taskbar minimize for the frameless window | GTK server-side decorations differ | hard |
| `ui/window.py:89, 112, 222, 279` | `GUI_BACKEND="edgechromium"` pinned; `GetSystemMetrics`/`GetDpiForSystem` | WebView2 backend + placement/DPI math | pywebview GTK/Qt; frameless+DPI behavior differs | hard |
| `ui/window.py:6` | pywebview imported lazily | stub-webview tests on Linux | n/a (seam) | — |
| `ui/fleetbar.py:45, 208` + `ui/sigbar.py:145, 183` | `Get/SetWindowLongW` EX_STYLE | always-on-top/tool-window floating bars | X11 hints; not Wayland | moderate |
| `ui/preflight.py:27, 79, 107` | winreg EdgeUpdate `pv` probe; `MessageBoxW` | WebView2 detection (mirrors installer); error dialog | package dep instead; `reader=` injectable, no-op off-Windows | trivial |
| `ui/tray.py:11` | `SetThreadDpiAwarenessContext`, `GetPhysicalCursorPos`, `TrackPopupMenuEx` | DPI-correct tray menu | pystray backend owns menus | trivial — module is the Windows-only adapter |
| `autostart.py:43, 92, 195` | HKCU Run key + legacy `.lnk` cleanup | start-on-login + migration | XDG `~/.config/autostart/*.desktop` | trivial-moderate (`_winreg()` seam; `enable()` raises OSError off-Windows by design) |
| `eveskills/controller.py:296` + `upload/controller.py:727, 943` | `os.startfile` | open file/folder | `xdg-open` | trivial |
| `alerts/service.py:243` + `alerts/sound.py:1` | `winsound.PlaySound` | alert audio | PulseAudio/paplay | trivial — sink already isolated for stubbing |
| `clipserve.py:42` | `msvcrt` + `CreateFileW(SHARE_READWRITE_DELETE)` | delete-while-open of served recordings | POSIX unlink semantics free | trivial — `os.name` guard, `_open_shared` falls back |
| `raiseipc.py:33, 40` | named kernel event `Global\FlyGDWingmanRaiseWindow` | second launch raises first window | abstract socket | trivial-moderate — no-ops off-Windows; `_wait_for_signal` is the test seam |


## Hotkey engine (bookmarks)

| Location | Mechanism | Purpose | Linux equivalent | Difficulty |
| --- | --- | --- | --- | --- |
| `hotkeys.py:39` | `CREATE_NO_WINDOW` (conditional) | hide engine console | n/a | trivial |
| `hotkeys.py:57, 284` | kernel Job Object via ctypes | bind engine lifetime to Wingman | `prctl(PR_SET_PDEATHSIG)` | trivial at the seam |
| `hotkeys.py:154` + `wingman/engine/eve_bookmarks.ahk` (bundled by `packaging/uploader.spec:74`) | AutoHotkeyU64.exe | keyboard automation of EVE bookmarks | no — AHK v1 has no Linux runtime | blocker; **seam is clean**: AHK appears nowhere in hotkeys' public interface; contract = INI in (`paths.engine_ini_file`) + `eve_status.json` out (`paths.engine_status_file`) + PID file, applied via `ui/api.py:7631` |
| `keylayout.py:14, 176` | `GetKeyboardLayout`/`MapVirtualKeyExW`/`ToUnicodeEx` (lazy, pinned sigs) | physical-key → produced-character for capture | xkbcommon; no per-window query on Wayland | moderate — `resolve(view,…)`/`win32_available(user32)` seams |


## Secrets, EVE data, state

| Location | Mechanism | Purpose | Linux equivalent | Difficulty |
| --- | --- | --- | --- | --- |
| `eveauth/dpapi.py:42` + `eveskills/dpapi.py:7` | `CryptProtectData`/`Unprotect` (crypt32) | user-scoped encryption of SSO tokens, skills doc | libsecret/kwallet via `keyring`, or libsodium+keyfile | moderate — clean seam: `available()`→False off-Windows; callers already tolerate DPAPI failure (`eveauth/controller.py:182, 409`) |
| `combatlog.py:85` | `~/Documents` + `~/OneDrive/Documents` + `EVE/logs/Gamelogs` | gamelog discovery | path exists, but EVE runs under Wine/Proton → logs inside a prefix | trivial mechanically, moderate semantically |
| `evesettings/tree.py:98, 192` | `%LOCALAPPDATA%\CCP\EVE` default; `normcase` matching | settings profile tree | `~/.local/share` fallback already exists; case-sensitivity trivial; same Wine-prefix caveat | trivial |
| `obsconfig.py:16` | `%APPDATA%\obs-studio` | auto-detect OBS recording dir | `$XDG_CONFIG_HOME/obs-studio` (OBS is native on Linux) | trivial — `appdata=` injectable |
| `telemetry/clients.py:62, 77, 161` | defaults to `preview.discovery.enumerate_clients` | fleet client discovery | seam proven (`tests/fixtures/fleet_current_client.py:135`) | moderate — default impl is the Windows part above |
| `paths.py:25, 42, 187, 301` | `LOCALAPPDATA` read + `~/.local/share` fallback; `.exe` suffixes; 3.x migration | state dir, binary lookup, codec exe | fallback already correct; `.exe` only applied on win32; migration is plain `os.replace` | trivial — needs Linux ffmpeg builds (`packaging/fetch_ffmpeg.py`) |


## Packaging / distribution

| Location | Mechanism | Purpose | Linux equivalent | Difficulty |
| --- | --- | --- | --- | --- |
| `packaging/installer.iss:28, 99, 180, 285` | Inno Setup: AppId, `.lnk`, HKCU Run, `OpenMutexW` wait, WebView2 Evergreen bootstrapper | Windows installer, upgrades, runtime install | full replacement (AppImage/deb/Flatpak + WebKitGTK dep) | blocker for shipping, not for running from source |
| `packaging/uploader.spec:16, 74, 140` | PyInstaller bundles ffmpeg/AHK/codec exes + engine datas, `console=False` | frozen Windows app | PyInstaller onefile on Linux | moderate — binary swaps |
| `packaging/settings-codec/Cargo.toml` | pure Rust (blue-marshal + serde_json) | settings codec sidecar | `cargo build --target x86_64-unknown-linux-gnu` — CI already builds an ELF binary on ubuntu | trivial |


## Blockers vs seams

Top-level hard blockers, 4:

1. Previews/overlay subsystem — DWM thumbnails, layered windows,
   WinEventHook/`RegisterHotKey`, message-pump host, native
   crop/region/companion windows.
2. AHK v1 bookmark engine (runtime; the file contract seam is clean).
3. Pinned `edgechromium`/WebView2 backend with WinForms-specific frameless
   chrome and DPI assumptions.
4. Windows-only distribution chain (Inno + WebView2 bootstrapper + Windows
   PyInstaller bundle).

Seams already in place, verified (~20): `_create_mutex` platform
early-return; `paths.state_dir` env + fallback; `autostart._winreg()`;
`raiseipc` no-ops + `_wait_for_signal`; `hotkeys` spawner/job seams + engine
file contract; DPAPI `available()`/`_require_windows` (+ eveskills
prefetch injectables); `alerts/sound.py` sink isolate; `keylayout.resolve(view)`/
`win32_available`; telemetry `_enumerate_clients`; codec `runner=`/`exe=` +
win32-only `.exe` suffix; `clipserve._open_shared` os.name guard;
`chrome.hit_code` pure + lazy ctypes; `tray.windows_icon_class` win32-only
attach; `preflight` `reader=`/no-op dialog; `gestures.py` pure;
`combatlog.find_gamelogs_dir(home=)`; `obsconfig(appdata=)`;
`tree.default_root` env fallback; `webbrowser.open`; `preview/win32.py`
importing cleanly on Linux.


## Test-suite Linux readiness

The suite runs fully on Linux today — recorded ubuntu runs show
**8,254 passed / 11 skipped**
([overview-layout-sharing-verification.md](overview-layout-sharing-verification.md)).
No pywin32 anywhere; subsystems (alerts, telemetry, settings,
hotkeys-contract) are exercised headlessly via constructor injection.

The 11 platform skips on Linux are all deliberate, and they are the only
tests that touch real Windows:

- Windows junctions: 5 (`test_evesettings_profilecopy.py:279,318,650`,
  `test_ui_setup_profile.py:458` ×2)
- real DPAPI/WinDLL: 2 (`test_eveskills_dpapi.py:45,52`)
- real message pump/window station: 1 (`test_preview_host.py:1361`)
- user32/gdi32/dwmapi binding assertions: 3 (`test_preview_win32.py:147,162,186`)

Environment-conditional skips (Node, codec-not-built) are satisfied by CI
itself; symmetric POSIX guards skip *on Windows*, so a Linux port inherits
extra coverage, not holes.
