"""The Win32 edge, driven through a double.

Runs on ubuntu-latest: win32.py keeps its structs and constants at module
scope and touches a DLL only inside bind() (win32.py:1-14), so a fake
`libs` exercises every branch here without Windows.

The fakes reach through `ref._obj` to read what byref() wrapped.
Production uses byref because the rest of the package does; a test double
receives the CArgObject rather than a pointer, and _obj is the wrapped
struct.
"""
import ctypes
import types

from obs_youtube_uploader.preview import clientwin32, win32
from obs_youtube_uploader.preview.geometry import Rect
from obs_youtube_uploader.preview.placement import Placement

PMV2 = win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
# What the fake actually receives. c_void_p(-4).value is 18446744073709551612
# on 64-bit, NOT -4: ctypes normalises to unsigned. Comparing against the raw
# constant fails for a reason that has nothing to do with the code under test.
PMV2_RAW = ctypes.c_void_p(PMV2).value


def _libs(user32):
    return types.SimpleNamespace(user32=user32, gdi32=None, dwmapi=None,
                                 kernel32=None)


class FakeUser32:
    def __init__(self, *, placement=None, work_area=(0, 0), ok=True,
                 dpi_previous=7):
        self.placement = placement
        self.work_area = work_area
        self.ok = ok
        self.dpi_previous = dpi_previous
        self.dpi_calls = []
        self.applied = []

    def SetThreadDpiAwarenessContext(self, ctx):
        value = ctx.value if hasattr(ctx, "value") else ctx
        self.dpi_calls.append(value)
        return self.dpi_previous

    def SystemParametersInfoW(self, action, uiparam, ref, winini):
        if not self.ok:
            return 0
        rect = ref._obj
        rect.left, rect.top = self.work_area
        return 1

    def GetWindowPlacement(self, hwnd, ref):
        if self.placement is None:
            return 0
        wp = ref._obj
        wp.showCmd = self.placement[0]
        rect = self.placement[1]
        wp.rcNormalPosition = win32.RECT(rect.x, rect.y,
                                         rect.right, rect.bottom)
        return 1

    def SetWindowPlacement(self, hwnd, ref):
        self.applied.append((hwnd, ref._obj))
        return 1 if self.ok else 0


def test_dpi_context_sets_per_monitor_v2_and_restores_the_previous():
    """Thread-local, so the process keeps the PROCESS_SYSTEM_DPI_AWARE
    contract __main__.py:99-114 chose deliberately."""
    user32 = FakeUser32(dpi_previous=99)
    with clientwin32.dpi_context(_libs(user32)) as accepted:
        assert accepted is True
    assert user32.dpi_calls == [PMV2_RAW, 99]


def test_dpi_context_restores_even_when_the_body_raises():
    user32 = FakeUser32(dpi_previous=99)
    try:
        with clientwin32.dpi_context(_libs(user32)):
            raise ValueError("boom")
    except ValueError:
        pass
    assert user32.dpi_calls == [PMV2_RAW, 99]


def test_dpi_context_reports_a_rejected_override():
    user32 = FakeUser32(dpi_previous=0)
    with clientwin32.dpi_context(_libs(user32)) as accepted:
        assert accepted is False
    assert user32.dpi_calls == [PMV2_RAW]


def test_work_area_origin_reads_the_primary_offset():
    user32 = FakeUser32(work_area=(0, 40))
    assert clientwin32.work_area_origin(_libs(user32)) == (0, 40)


def test_work_area_origin_falls_back_to_zero_when_the_call_fails():
    """A failed SPI_GETWORKAREA must not abort the batch: zero is the
    right guess, since it is correct for every bottom/right taskbar."""
    assert clientwin32.work_area_origin(_libs(FakeUser32(ok=False))) == (0, 0)


def test_read_placement_converts_workspace_to_screen():
    user32 = FakeUser32(placement=(win32.SW_SHOWNORMAL, Rect(10, 20, 800, 600)))
    got = clientwin32.read_placement(1234, (0, 40), _libs(user32))
    assert got == Placement(Rect(10, 60, 800, 600), False)


def test_read_placement_reports_maximized():
    user32 = FakeUser32(placement=(win32.SW_SHOWMAXIMIZED,
                                   Rect(10, 20, 800, 600)))
    assert clientwin32.read_placement(1, (0, 0), _libs(user32)).maximized


def test_a_minimized_client_still_yields_its_restore_rect():
    """rcNormalPosition is where the window will un-minimize to, which is
    the thing worth persisting -- and maximized must read False."""
    user32 = FakeUser32(placement=(win32.SW_SHOWMINIMIZED,
                                   Rect(10, 20, 800, 600)))
    got = clientwin32.read_placement(1, (0, 0), _libs(user32))
    assert got == Placement(Rect(10, 20, 800, 600), False)


def test_read_placement_returns_none_when_the_call_fails():
    assert clientwin32.read_placement(1, (0, 0), _libs(FakeUser32())) is None


def test_apply_placement_converts_screen_back_to_workspace():
    user32 = FakeUser32()
    ok = clientwin32.apply_placement(
        1234, Placement(Rect(10, 60, 800, 600), False), (0, 40),
        _libs(user32))
    assert ok
    hwnd, wp = user32.applied[0]
    assert hwnd == 1234
    assert (wp.rcNormalPosition.left, wp.rcNormalPosition.top) == (10, 20)
    assert wp.showCmd == win32.SW_SHOWNORMAL


def test_apply_placement_always_sets_the_async_flag():
    """Without it, a hung client stalls the calling thread."""
    user32 = FakeUser32()
    clientwin32.apply_placement(1, Placement(Rect(0, 0, 8, 6)), (0, 0),
                                _libs(user32))
    assert user32.applied[0][1].flags & win32.WPF_ASYNCWINDOWPLACEMENT


def test_apply_placement_restores_maximized():
    user32 = FakeUser32()
    clientwin32.apply_placement(1, Placement(Rect(0, 0, 8, 6), True), (0, 0),
                                _libs(user32))
    assert user32.applied[0][1].showCmd == win32.SW_SHOWMAXIMIZED


def test_apply_placement_never_minimizes():
    """Placement carries no minimized state by construction, so no input
    can produce SW_SHOWMINIMIZED. This pins that."""
    user32 = FakeUser32()
    for maximized in (True, False):
        clientwin32.apply_placement(1, Placement(Rect(0, 0, 8, 6), maximized),
                                    (0, 0), _libs(user32))
    assert all(wp.showCmd != win32.SW_SHOWMINIMIZED
               for _hwnd, wp in user32.applied)


def test_apply_placement_reports_failure():
    assert not clientwin32.apply_placement(
        1, Placement(Rect(0, 0, 8, 6)), (0, 0), _libs(FakeUser32(ok=False)))
