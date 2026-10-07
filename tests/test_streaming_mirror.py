"""The shipping mirror's logic half (issue #316), on injected libs.

Seams under test, all on Mirror's public surface:

1. Lifecycle -- bind_source / on_foreground / on_source_gone: rebind on an
   admitted foreground change, sticky last client on non-EVE focus, routine
   release on source death (thumbnail.py's own failure semantics stay in
   test_preview_thumbnail.py).
2. Window contract -- the wndproc: never activates (MA_NOACTIVATE), never
   minimizes (SC_MINIMIZE swallowed), unknown messages reach DefWindowProcW
   (the messages Windows pumps during CreateWindowExW must survive).
3. Park/cloak -- the field-proven park: on-desktop bottom-left at
   HWND_BOTTOM, cloak-primary parking via DWMWA_CLOAK (probe evidence,
   #312/#315: off-desktop freezes the composed surface, minimize pauses it).

Not under test: the message pump, window-class registration and the exe
entry (native; the supervisor ticket #317 owns process concerns), and
anything Discord-side. The fakes implement only what Mirror calls; a fake
missing a method fails loudly instead of silently passing.
"""

from wingman import bookmarks
from wingman.streaming import mirror

EVE_A = 0x1001
EVE_B = 0x1002
BROWSER = 0x2001
MIRROR = 0x9001

TITLES = {
    MIRROR: "Wingman mirror",
    EVE_A: "EVE - Kuan Dai",
    EVE_B: "EVE - Sigma",
    BROWSER: "Fleet map - Google Chrome",
}


def _mirror_libs(virtual=(0, 0, 1920, 1080)):
    """Fake libs covering Mirror's call surface; window 0x9001 is the
    mirror, others are candidate sources with canned titles/rects. The
    mirror's client rect tracks the last shape-match SetWindowPos (a real
    WS_POPUP window's client area is its whole rect) -- that mapping is
    what makes the destination-rect assertions honest."""

    class FakeUser32:
        def __init__(self):
            self.window_pos = []  # (hwnd, after, x, y, w, h, flags)
            self.shown = []
            self.destroyed = []
            self.ex_styles = []  # CreateWindowExW's exStyle, per call
            self.client = (800, 600)  # CreateWindowExW's initial size
            self.styles = {}  # hwnd -> current GWL_STYLE value
            self.styles[MIRROR] = (
                mirror.WS_POPUP | mirror.WS_MINIMIZEBOX
            )  # what CreateWindowExW left behind

        # --- window lifecycle
        def CreateWindowExW(self, ex, cls, title, style, x, y, w, h, a, b, inst, c):
            self.ex_styles.append(ex)
            return MIRROR

        def DestroyWindow(self, hwnd):
            self.destroyed.append(hwnd)
            return 1

        def SetWindowPos(self, hwnd, after, x, y, w, h, flags):
            if not (flags & mirror.SWP_NOSIZE) and w:
                self.client = (w, h)
            self.window_pos.append(
                (int(hwnd), int(after) if after else 0, x, y, w, h, flags)
            )
            return 1

        def ShowWindow(self, hwnd, cmd):
            self.shown.append((hwnd, cmd))
            return 1

        # --- reads (out is byref(): mutate through ._obj)
        def GetClientRect(self, hwnd, out):
            w, h = self.client
            out._obj.left, out._obj.top, out._obj.right, out._obj.bottom = 0, 0, w, h
            return 1

        def GetWindowRect(self, hwnd, out):
            rect = {EVE_A: (10, 20, 810, 470), EVE_B: (0, 0, 1024, 768)}.get(int(hwnd))
            if rect is None:
                return 0
            out._obj.left, out._obj.top, out._obj.right, out._obj.bottom = rect
            return 1

        def GetWindowTextW(self, hwnd, buf, n):
            buf.value = TITLES.get(hwnd, "")
            return len(buf.value)

        def IsWindowVisible(self, hwnd):
            return 1

        # --- style pin (WS_MINIMIZEBOX strip)
        def GetWindowLongW(self, hwnd, index):
            return self.styles.get(hwnd, 0)

        def SetWindowLongW(self, hwnd, index, value):
            self.styles[hwnd] = value
            return value

        # --- parking
        def GetSystemMetrics(self, index):
            return {
                mirror.SM_XVIRTUALSCREEN: virtual[0],
                mirror.SM_YVIRTUALSCREEN: virtual[1],
                mirror.SM_CXVIRTUALSCREEN: virtual[2],
                mirror.SM_CYVIRTUALSCREEN: virtual[3],
            }[index]

        def DefWindowProcW(self, hwnd, msg, wparam, lparam):
            return 0xDEF

        def PostMessageW(self, hwnd, msg, wparam, lparam):
            return 1

    class FakeDwm:
        def __init__(self):
            self.registered = []  # (dest, src)
            self.unregistered = []  # handles
            self.updates = []  # DWM_THUMBNAIL_PROPERTIES
            self.register_hr = 0
            self.cloak_values = []  # (attr, value)
            self.cloak_hr = 0
            self._next = 0x50

        def DwmRegisterThumbnail(self, dest, src, out):
            if self.register_hr != 0:
                return self.register_hr
            self._next += 1
            self.registered.append((int(dest), int(src)))
            out._obj.value = self._next
            return 0

        def DwmUnregisterThumbnail(self, handle):
            # Real calls pass a HANDLE struct (thumbnail.py stores what
            # register filled in); fakes pass plain ints. Accept both.
            value = getattr(handle, "value", handle)
            self.unregistered.append(int(value) if value else 0)
            return 0

        def DwmUpdateThumbnailProperties(self, handle, props):
            self.updates.append(props._obj)
            return 0

        def DwmSetWindowAttribute(self, hwnd, attr, value, size):
            self.cloak_values.append((attr, value._obj.value))
            return self.cloak_hr

    class FakeKernel32:
        def GetModuleHandleW(self, name):
            return 0x7

    libs = type("Libs", (), {})()
    libs.dwmapi = FakeDwm()
    libs.user32 = FakeUser32()
    libs.kernel32 = FakeKernel32()
    return libs


def _mirror(libs, **kw):
    m = mirror.Mirror(libs, sources=("EVE - ",), **kw)
    m.create_mirror()
    return m


# --- 1. lifecycle ---------------------------------------------------------


def test_the_mirror_is_created_a_tool_window():
    """The shell gives a visible top-level window a taskbar button, and
    DWM cloak hides the pixels but not the button -- the user found the
    mirror's icon sitting in the bar (field, 2026-10-07). TOOLWINDOW:
    no taskbar button, no alt-tab; Discord's pin is per-process and the
    tool window is still its one streamable window."""
    libs = _mirror_libs()
    _mirror(libs)
    assert libs.user32.ex_styles == [mirror.WS_EX_TOOLWINDOW]


def test_rebind_on_admitted_foreground_changes_the_thumbnail_source():
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)

    m.on_foreground(EVE_B)

    assert [src for _dest, src in libs.dwmapi.registered] == [EVE_A, EVE_B]
    # DWM has no retarget: the old binding is unregistered, not updated.
    assert len(libs.dwmapi.unregistered) == 1
    assert m.src_hwnd == EVE_B


def test_non_eve_foreground_is_sticky_last_client():
    """Desktop/browser focus never blanks the fleet's view: no unregister,
    no rebind, the source stays whatever was last admitted."""
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)

    m.on_foreground(BROWSER)

    assert [src for _dest, src in libs.dwmapi.registered] == [EVE_A]
    assert libs.dwmapi.unregistered == []
    assert m.src_hwnd == EVE_A


def test_same_source_foreground_does_not_rebind():
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)

    m.on_foreground(EVE_A)

    assert len(libs.dwmapi.registered) == 1


def test_source_death_releases_routinely_and_stays_sticky():
    """The frozen last frame is the spec-accepted behavior: release the
    thumbnail, keep the hwnd so the next admitted foreground rebinds."""
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)

    m.on_source_gone()

    assert len(libs.dwmapi.unregistered) == 1
    assert m.thumb is None
    assert m.src_hwnd == EVE_A


def test_failed_registration_is_not_a_crash_and_stays_sticky():
    libs = _mirror_libs()
    libs.dwmapi.register_hr = 0x80004005
    m = _mirror(libs)

    m.bind_source(EVE_A)

    assert m.thumb is None
    assert m.src_hwnd == EVE_A


def test_admission_stays_pinned_to_the_house_rule():
    """One admitted-title rule across Wingman: the mirror's predicate must
    agree with bookmarks.is_engine_window_title on every title that rule
    answers about -- a drift here mirrors a window the rest of Wingman
    refuses to call an EVE client. The delegation is by value, not import
    (bookmarks is pure keybind/INI logic and gains no streaming imports);
    this test is the pin that keeps the two honest."""
    samples = [
        "EVE - Kuan Dai",
        "EVE - Kuan Dai = extra",
        "EVE - ",
        "Notepad",
        "EVE - Sigma [offline]",
        "",
        "eVE - lowercase",
    ]
    for title in samples:
        assert mirror.Mirror(_mirror_libs()).admitted(title) == (
            bookmarks.is_engine_window_title(title)
        ), title


# --- 2. window contract ----------------------------------------------------


def test_wndproc_never_activates_and_never_minimizes():
    libs = _mirror_libs()
    m = _mirror(libs)

    ma = m.handle_message(MIRROR, mirror.WM_MOUSEACTIVATE, 0, 0)
    assert ma == mirror.MA_NOACTIVATE

    swallowed = m.handle_message(MIRROR, mirror.WM_SYSCOMMAND, mirror.SC_MINIMIZE, 0)
    assert swallowed == 0


def test_wndproc_swallows_minimize_without_showing_iconic():
    libs = _mirror_libs()
    m = _mirror(libs)
    before = list(libs.user32.shown)
    m.handle_message(MIRROR, mirror.WM_SYSCOMMAND, mirror.SC_MINIMIZE, 0)
    # No show-state change may escape in response -- no SW_MINIMIZE, no
    # SW_FORCEMINIMIZE, nothing: the mirror never minimizes (a minimized
    # mirror stops compositing and the stream pauses, field-proven #315).
    assert libs.user32.shown == before
    # And the belt to the WM_SYSCOMMAND braces: WS_MINIMIZEBOX stripped.
    assert not libs.user32.styles[MIRROR] & mirror.WS_MINIMIZEBOX


def test_wndproc_defers_unknown_messages_to_defwindowproc():
    """Windows pumps messages during CreateWindowExW, before the handle
    exists; swallowing any of them breaks window creation (probe lesson)."""
    libs = _mirror_libs()
    m = _mirror(libs)

    assert m.handle_message(MIRROR, 0x28, 0, 0) == 0xDEF  # WM_ACTIVATE etc.


def test_create_mirror_sits_at_the_bottom_of_the_z_order():
    """Created at HWND_BOTTOM before first show -- the pin must land on a
    window that never rose."""
    libs = _mirror_libs()
    m = mirror.Mirror(libs, sources=("EVE - ",))
    m.create_mirror()

    bottoms = [call for call in libs.user32.window_pos if call[1] == mirror.HWND_BOTTOM]
    assert bottoms, "mirror was never positioned at HWND_BOTTOM"
    assert libs.user32.shown and libs.user32.shown[0][1] == mirror.SW_SHOWNOACTIVATE


# --- 3. park + cloak -------------------------------------------------------


def test_default_park_is_cloak_primary_with_visible_fallback():
    """Cloak-primary: the window is left visible-but-cloaked (no park
    geometry) when the cloak takes; a refused cloak falls back to the
    proven covered on-desktop park -- never off-desktop, it freezes."""
    libs = _mirror_libs()
    m = mirror.Mirror(libs, sources=("EVE - ",))
    m.create_mirror()
    assert m.park_mode == "cloak"
    # Exactly one position call before any bind: the HWND_BOTTOM pin at
    # creation. A cloaked mirror needs no park geometry at all.
    assert len(libs.user32.window_pos) == 1
    assert libs.user32.window_pos[0][1] == mirror.HWND_BOTTOM

    libs = _mirror_libs()
    libs.dwmapi.cloak_hr = 0x80070057
    m = mirror.Mirror(libs, sources=("EVE - ",))
    m.create_mirror()
    assert m.park_mode == "visible"
    (_hwnd, after, x, y, w, h, _flags) = libs.user32.window_pos[-1]
    assert after == mirror.HWND_BOTTOM
    assert (x, y) == (0, 1080 - m.size[1])  # bottom-left of the virtual screen
    assert (w, h) == (0, 0)  # size comes from the source match, not the park


def test_mirror_matches_source_shape_on_bind():
    """The user rejected letterboxing: white bars stream. Borderless
    WS_POPUP resized to the source's outer rect on every bind, never
    rising above HWND_BOTTOM while reshaped."""
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)

    (_hwnd, after, x, y, w, h, _flags) = libs.user32.window_pos[-1]
    assert (x, y, w, h) == (10, 20, 800, 450)  # EVE_A's outer rect
    assert after == mirror.HWND_BOTTOM
    assert tuple(m.client_rect()) == (0, 0, 800, 450)  # dest = whole (shaped) client


def test_thumbnail_dest_is_the_whole_shaped_client():
    """Source-shape matching makes client == source shape, so the
    destination is the full client, sent as edges -- full frame, no bars."""
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)

    props = libs.dwmapi.updates[-1]
    rc = props.rcDestination
    assert (rc.left, rc.top, rc.right, rc.bottom) == (0, 0, 800, 450)


def test_cloak_toggles_and_tracks_state_across_the_mirror_lifetime():
    """Creation parks cloak-primary (the first entry); uncloak and re-cloak
    follow, with park_mode honest at every step."""
    libs = _mirror_libs()
    m = _mirror(libs)
    assert libs.dwmapi.cloak_values == [(mirror.DWMWA_CLOAK, 1)]  # creation
    assert (m.cloaked, m.park_mode) == (True, "cloak")

    m.set_cloak(False)
    assert libs.dwmapi.cloak_values[-1] == (mirror.DWMWA_CLOAK, 0)
    assert (m.cloaked, m.park_mode) == (False, "visible")

    m.set_cloak(True)
    assert libs.dwmapi.cloak_values[-1] == (mirror.DWMWA_CLOAK, 1)
    assert (m.cloaked, m.park_mode) == (True, "cloak")


def test_cloak_failure_reads_as_not_cloaked():
    libs = _mirror_libs()
    libs.dwmapi.cloak_hr = 0x80070057
    m = _mirror(libs)

    m.set_cloak(True)

    assert m.cloaked is False
    # A failed cloak must not read as parked-invisible: the card's wording
    # and the user's expectation both hinge on this flag being honest.
    assert m.park_mode == "visible"


def test_thumbnail_dest_tracks_the_shaped_client_after_rebind():
    """A rebind to a differently-shaped source re-fits the destination:
    the mirror is resized to the new source's outer rect first, so the
    thumbnail's edges follow the new client shape."""
    libs = _mirror_libs()
    m = _mirror(libs)
    m.bind_source(EVE_A)
    m.bind_source(EVE_B)

    rc = libs.dwmapi.updates[-1].rcDestination
    assert (rc.left, rc.top, rc.right, rc.bottom) == (0, 0, 1024, 768)
