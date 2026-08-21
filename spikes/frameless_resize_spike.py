"""Spike: can a frameless pywebview window get native resize back?

WHY THIS EXISTS
---------------
ui/window.py creates the main window with `frameless=True`. On the
edgechromium/WinForms backend that sets `FormBorderStyle.None`
(pywebview 6.2.1, platforms/winforms.py:269), which removes the entire
non-client frame -- so Windows has nothing to hit-test and the window
cannot be resized. `resizable` is still True; it is not the cause.

This spike tests ONE proposed fix, end to end, on real Windows:

    subclass the HWND's WndProc from Python (ctypes) and answer
    WM_NCHITTEST with HTLEFT/HTBOTTOMRIGHT/etc. inside a synthetic
    border, chaining every other message to the original proc.

It deliberately does NOT touch GWL_STYLE. Adding WS_THICKFRAME is the
other candidate, but with FormBorderStyle.None and no WM_NCCALCSIZE
handling it typically leaves an unpainted non-client border, and
`toggle_fullscreen` reassigns FormBorderStyle (winforms.py:558,577)
which can recreate the handle and silently drop the style bit.

It also tests the WM_GETMINMAXINFO half, because a borderless WinForms
form maximizes over the taskbar: pywebview sets MinimumSize
(winforms.py:210) but never MaximumSize and never handles
WM_GETMINMAXINFO. Clamping max size in the same subclass is strictly
better than setting Form.MaximumSize, which would also cap the window
on a larger second monitor.

THE QUESTION THAT DECIDES THE APPROACH
--------------------------------------
WM_NCHITTEST goes to the window UNDER THE CURSOR. pywebview docks the
WebView2 control with DockStyle.Fill and calls BringToFront
(platforms/edgechromium.py:95-100), and `frameless` means the client
area IS the whole window -- so the WebView2 child HWND covers every
pixel where the synthetic border lives, right out to the edges.

If Windows therefore routes those hit-tests to the Chromium child
window, the parent subclass never sees them and this whole approach is
dead on arrival. That is question 0 below, and it is the one to answer
first; everything else is moot if it fails.

Note this is exactly the failure a bare WinForms test would MISS: a form
with no child control hit-tests perfectly and reports a false green. The
test has to run against a real WebView2 window.

`--pad N` exists for that case. DockStyle.Fill honours the parent's
Padding, so insetting the form by N pixels leaves a band of Form surface
around the page that the parent DOES own. It costs a visible N-pixel
frame in the app's background colour, which is a design change rather
than a pure bugfix -- worth knowing whether it is the price of resizing.

RUN IT (Windows, with WebView2 present)
---------------------------------------
    uv run python spikes/frameless_resize_spike.py

    --no-hittest    skip WM_NCHITTEST     -> reproduces today's stuck window
    --no-maxinfo    skip WM_GETMINMAXINFO -> shows the taskbar-covering maximize
    --pad N         inset the WebView2 by N px so the form owns a border band

WHAT TO WRITE DOWN
------------------
 0. FIRST: does the parent window receive WM_NCHITTEST at all? Move the
    mouse slowly onto each edge and watch the console. The spike prints
    "[spike] first WM_NCHITTEST reached the form" once, and prints the
    running total on quit. If that line never appears while the pointer
    is over the window, the WebView2 child is swallowing the message and
    the plain subclass cannot work -- re-run with `--pad 6` and see
    whether the band changes the answer. Everything below assumes this
    passed.
 1. Do all eight edges/corners resize, and does the cursor change to the
    sizing arrows before the drag?
 2. Does MinimumSize still hold? Drag smaller than 880x560; WinForms
    enforces it via its own WM_GETMINMAXINFO handling, which only works
    because we chain to the original proc FIRST. If the window goes
    smaller, the chaining order is wrong.
 3. Does the top border steal the title-bar drag? The synthetic border
    overlaps the top 6px of the drag region by design; confirm dragging
    still feels normal below it.
 4. Does Aero Snap work -- drag to the screen edge, and Win+Left/Right?
    Snap normally wants WS_THICKFRAME, so this may well be NO. That is a
    finding, not a failure.
 5. Does double-clicking an edge maximize (also usually WS_THICKFRAME)?
 6. Press "Fullscreen" twice. Does resize still work afterwards? If not,
    toggle_fullscreen recreated the handle and the subclass was dropped
    -- the spike prints the HWND on shown and on restore, so a changed
    value is visible in the console.
 7. Press "Maximize". Is the taskbar still visible, and is the window on
    the working area only? Re-run with --no-maxinfo to see the contrast.
 8. Anything crash? A GC'd WNDPROC callback or an exception crossing the
    native boundary kills the process outright, so "it survived five
    minutes of poking" is itself a result worth recording.
 9. Repeat 1 and 2 on a display at 150% or 175% scaling. The spike sets
    PROCESS_SYSTEM_DPI_AWARE to match the app, so the border should stay
    grabbable at the same apparent thickness. If it turns razor-thin or
    unhittable, the scale factor is being applied wrongly and every
    number in _hit() needs revisiting.
10. Drag the window to a second monitor at a DIFFERENT scale and resize
    there. System-DPI-aware means the app is already knowingly wrong in
    that situation; the question is only whether resize degrades
    gracefully or becomes unusable.

This is throwaway. Nothing here is imported by the app; the flags below
are duplicated from ui/window.py on purpose so the spike keeps working
if the app changes.
"""
from __future__ import annotations

import ctypes
import sys
import traceback
from ctypes import wintypes

import webview

# Guard here, not in main(): ctypes.WINFUNCTYPE and most of ctypes.wintypes
# exist only on Windows, and this module builds a WNDPROC type at import
# time. A check inside main() never runs -- the import raises first.
if sys.platform != "win32":
    print("This spike only means anything on Windows.", file=sys.stderr)
    raise SystemExit(2)

# Mirrors ui/window.py. Duplicated, not imported -- see the docstring.
TITLE = "Frameless resize spike"
WIDTH, HEIGHT = 1040, 680
MIN_WIDTH, MIN_HEIGHT = 880, 560
BACKGROUND = "#0c0d10"
GUI_BACKEND = "edgechromium"

# Width of the synthetic resize border, in LOGICAL pixels, scaled per
# window DPI at hit-test time. 6 is about what a real Windows 11 frame
# offers; much less and the edge is unhittable on a high-DPI display.
BORDER = 6
CORNER = 14

WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024
GWLP_WNDPROC = -4

HTLEFT, HTRIGHT = 10, 11
HTTOP, HTTOPLEFT, HTTOPRIGHT = 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

MONITOR_DEFAULTTONEAREST = 2

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", wintypes.POINT),
        ("ptMaxSize", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("ptMinTrackSize", wintypes.POINT),
        ("ptMaxTrackSize", wintypes.POINT),
    ]


# THE global that keeps the callback alive. A ctypes callback collected
# while Windows still holds its address takes the whole process down at
# the next message, and the crash points nowhere near here. Every
# attached proc is appended and never removed.
_KEEPALIVE: list = []

# Whether the parent form ever saw a WM_NCHITTEST, and how many. This is
# the spike's primary result: if the WebView2 child swallows the message
# the count stays at zero no matter how carefully anyone drags an edge,
# and a zero here is a far more trustworthy answer than "it felt stuck".
_HITS = {"count": 0, "announced": False}


def _match_app_dpi_awareness() -> None:
    """Replicate __main__.set_dpi_awareness() -- PROCESS_SYSTEM_DPI_AWARE.

    This is not boilerplate, it decides whether the spike measures
    anything real. A DPI-unaware process gets virtualized coordinates:
    GetWindowRect reports scaled-down values and GetDpiForWindow reports
    96 on a 150% display, so the border math below would be exercised in
    a coordinate space the shipped app never runs in, and a passing spike
    would prove nothing.

    It must be awareness level 1 specifically, matching __main__.py:112.
    Per-Monitor V2 would put the window in a different coordinate regime
    AND introduce WM_DPICHANGED, which the app deliberately does not
    handle -- so testing under it would answer a question nobody asked.

    Nothing in packaging/uploader.spec declares DPI awareness in a
    manifest, so this runtime call is the only source of it in the real
    app too. That is what makes a source run and a frozen run equivalent
    here.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        # shcore.dll predates Windows 8.1. Same swallow as the app.
        pass


def _user32():
    """Load user32 with explicit signatures.

    The argtypes/restype are not decoration. SetWindowLongPtr returns a
    pointer-sized value; leaving restype as the default c_int truncates
    the original WndProc address on 64-bit, and chaining to a truncated
    pointer is an immediate access violation.
    """
    user32 = ctypes.windll.user32

    set_ptr = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    set_ptr.restype = ctypes.c_void_p
    set_ptr.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]

    user32.CallWindowProcW.restype = LRESULT
    user32.CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]

    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]

    return user32, set_ptr


def _scale_for(user32, hwnd: int) -> float:
    """Window DPI scale, matching the app's system-DPI-aware model.

    Under PROCESS_SYSTEM_DPI_AWARE, GetDpiForWindow reports the SYSTEM
    DPI rather than the DPI of whichever monitor the window is on -- so
    this returns exactly the scale the shipped app sees, including its
    known wrongness after the window is dragged to a differently-scaled
    monitor. That mismatch is the app's deliberate tradeoff
    (__main__.set_dpi_awareness), so the spike must inherit it rather
    than quietly improve on it.

    GetDpiForWindow is Windows 10 1607+; older hosts fall back to 1.0.
    """
    get_dpi = getattr(user32, "GetDpiForWindow", None)
    if get_dpi is None:
        return 1.0
    try:
        dpi = get_dpi(wintypes.HWND(hwnd))
        return (dpi / 96.0) if dpi else 1.0
    except OSError:
        return 1.0


def _hit(user32, hwnd: int, lparam: int) -> int | None:
    """Map a screen point to an HT* border code, or None for 'not mine'.

    The coordinates in lParam are SIGNED 16-bit halves. A monitor left of
    the primary gives negative x, and masking without sign-extending puts
    the cursor at x=65000 -- every hit-test on that monitor would miss.
    """
    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value

    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None

    scale = _scale_for(user32, hwnd)
    border = max(1, int(BORDER * scale))
    corner = max(border, int(CORNER * scale))

    left = x < rect.left + border
    right = x >= rect.right - border
    top = y < rect.top + border
    bottom = y >= rect.bottom - border

    # Corners get a longer reach than the edges, so the diagonal grab is
    # not a 6px square nobody can hit.
    near_left = x < rect.left + corner
    near_right = x >= rect.right - corner
    near_top = y < rect.top + corner
    near_bottom = y >= rect.bottom - corner

    if (top and near_left) or (left and near_top):
        return HTTOPLEFT
    if (top and near_right) or (right and near_top):
        return HTTOPRIGHT
    if (bottom and near_left) or (left and near_bottom):
        return HTBOTTOMLEFT
    if (bottom and near_right) or (right and near_bottom):
        return HTBOTTOMRIGHT
    if left:
        return HTLEFT
    if right:
        return HTRIGHT
    if top:
        return HTTOP
    if bottom:
        return HTBOTTOM
    return None


def _clamp_to_working_area(user32, hwnd: int, lparam: int) -> None:
    """Stop a borderless maximize from swallowing the taskbar.

    Done here rather than via Form.MaximumSize because MaximumSize is a
    single global cap: it would also stop the user growing the window on
    a larger second monitor. WM_GETMINMAXINFO is per-monitor and is
    evaluated at the moment of maximizing.
    """
    monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return

    work, full = info.rcWork, info.rcMonitor
    mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
    mmi.ptMaxSize.x = work.right - work.left
    mmi.ptMaxSize.y = work.bottom - work.top
    # ptMaxPosition is relative to the monitor, not to the desktop.
    mmi.ptMaxPosition.x = work.left - full.left
    mmi.ptMaxPosition.y = work.top - full.top


def attach(hwnd: int, *, hittest: bool = True, maxinfo: bool = True) -> None:
    """Subclass *hwnd* so it hit-tests a synthetic resize border."""
    user32, set_ptr = _user32()
    old_holder: list = []

    def proc(handle, msg, wparam, lparam):
        old = old_holder[0]
        try:
            if hittest and msg == WM_NCHITTEST:
                _HITS["count"] += 1
                if not _HITS["announced"]:
                    _HITS["announced"] = True
                    # Printed once, not per message: WM_NCHITTEST arrives
                    # on every mouse move and would bury everything else.
                    print("[spike] first WM_NCHITTEST reached the form")

                code = _hit(user32, hwnd, lparam)
                if code is not None:
                    return code
                # Fall through: the client area must keep behaving
                # normally or the page stops receiving the mouse.

            if maxinfo and msg == WM_GETMINMAXINFO:
                # Chain FIRST so WinForms fills ptMinTrackSize in from
                # MinimumSize, THEN override only the max fields. The
                # other order throws min_size away and the window can be
                # dragged down to nothing.
                result = user32.CallWindowProcW(old, handle, msg, wparam, lparam)
                _clamp_to_working_area(user32, hwnd, lparam)
                return result
        except Exception:
            # An exception here would unwind through the native message
            # pump. Swallow it, print it, and let the original proc
            # answer -- a spike that dies silently teaches nothing.
            traceback.print_exc()

        return user32.CallWindowProcW(old, handle, msg, wparam, lparam)

    callback = WNDPROC(proc)
    _KEEPALIVE.append(callback)

    previous = set_ptr(wintypes.HWND(hwnd), GWLP_WNDPROC, callback)
    if not previous:
        raise OSError(ctypes.get_last_error() or 0, "SetWindowLongPtr(GWLP_WNDPROC) failed")

    old_holder.append(ctypes.cast(previous, WNDPROC))
    print(f"[spike] subclassed hwnd=0x{hwnd:x} hittest={hittest} maxinfo={maxinfo}")


PAGE = """
<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;height:100%%;font:13px/1.5 "Segoe UI",sans-serif;
            color:#e6e8ee;background:%(bg)s;overflow:hidden;
            display:flex;flex-direction:column;}
  .bar{height:38px;display:flex;align-items:center;gap:8px;padding:0 8px;
       background:#12141a;border-bottom:1px solid #23262f;flex:none;}
  .drag{flex:1;height:100%%;display:flex;align-items:center;font-weight:600;
        letter-spacing:.08em;}
  button{background:#1c1f27;color:#e6e8ee;border:1px solid #2c3038;
         border-radius:6px;padding:5px 10px;font:inherit;cursor:pointer;}
  main{flex:1;display:flex;align-items:center;justify-content:center;}
  .size{font-size:34px;font-variant-numeric:tabular-nums;}
  .hint{padding:0 0 10px;text-align:center;color:#7d8494;font-size:12px;}
</style></head><body>
  <div class="bar">
    <div class="drag pywebview-drag-region">SPIKE &mdash; drag me</div>
    <button onclick="pywebview.api.maximize()">Maximize</button>
    <button onclick="pywebview.api.restore()">Restore</button>
    <button onclick="pywebview.api.fullscreen()">Fullscreen</button>
    <button onclick="pywebview.api.quit()">Quit</button>
  </div>
  <main><div class="size" id="size">-</div></main>
  <div class="hint">min is %(minw)d x %(minh)d &mdash; try to drag smaller</div>
<script>
  function paint(){
    document.getElementById('size').textContent =
      window.innerWidth + ' x ' + window.innerHeight;
  }
  window.addEventListener('resize', paint); paint();
</script></body></html>
""" % {"bg": BACKGROUND, "minw": MIN_WIDTH, "minh": MIN_HEIGHT}


class Api:
    """Buttons only.

    `_window` is underscored for the same reason the real Api underscores
    it: pywebview builds its JS proxy by walking PUBLIC attributes, and a
    public webview.Window sends that walk into WinForms until
    RecursionError kills the process about eight seconds after launch.
    """

    def __init__(self) -> None:
        self._window = None

    def maximize(self) -> None:
        self._window.maximize()

    def restore(self) -> None:
        self._window.restore()

    def fullscreen(self) -> None:
        self._window.toggle_fullscreen()

    def quit(self) -> None:
        # The count is the headline result, so report it before the
        # window goes away rather than leaving it to be scrolled for.
        print(f"[spike] WM_NCHITTEST reached the form {_HITS['count']} time(s)")
        if not _HITS["count"]:
            print("[spike] ZERO -- the WebView2 child swallowed every "
                  "hit-test. Re-run with --pad 6.")
        self._window.destroy()


def main(argv: list[str]) -> int:
    # FIRST, before any window exists. Awareness is a process-wide setting
    # that Windows latches once a window has been created, so calling it
    # later would silently do nothing.
    _match_app_dpi_awareness()

    hittest = "--no-hittest" not in argv
    maxinfo = "--no-maxinfo" not in argv
    pad = 0
    if "--pad" in argv:
        try:
            pad = int(argv[argv.index("--pad") + 1])
        except (IndexError, ValueError):
            print("--pad needs an integer, e.g. --pad 6", file=sys.stderr)
            return 2

    api = Api()
    window = webview.create_window(
        TITLE,
        html=PAGE,
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        frameless=True,
        easy_drag=False,
        background_color=BACKGROUND,
    )
    api._window = window

    def on_shown() -> None:
        # window.native is the WinForms Form (winforms.py:195). Handle is
        # an IntPtr; ToInt64 keeps it whole on 64-bit, which ToInt32 does
        # not guarantee.
        if pad:
            # DockStyle.Fill measures against the parent's DisplayRectangle,
            # which Padding shrinks -- so this insets the WebView2 without
            # touching pywebview's Dock assignment. Applied AFTER the
            # control exists, or Fill would just re-expand over it.
            from System.Windows.Forms import Padding

            window.native.Padding = Padding(pad)
            print(f"[spike] form padded by {pad}px; the band is form surface")

        attach(window.native.Handle.ToInt64(), hittest=hittest, maxinfo=maxinfo)

    def on_restored() -> None:
        # Printed so a handle recreated by toggle_fullscreen is visible: a
        # changed value here means the subclass was silently dropped.
        print(f"[spike] restored, hwnd=0x{window.native.Handle.ToInt64():x}")

    window.events.shown += on_shown
    window.events.restored += on_restored

    webview.start(gui=GUI_BACKEND)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
