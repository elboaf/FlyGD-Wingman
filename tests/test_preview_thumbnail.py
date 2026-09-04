"""Lifecycle only -- the DWM calls are faked. What matters here is that a
failed registration degrades instead of raising, and that close() is
idempotent: a double-unregister is a use-after-free in DWM's handle
table, and the crash lands nowhere near this file."""

from wingman.preview import thumbnail
from wingman.preview.geometry import Rect


class FakeDwm:
    def __init__(self, hr=0, register_hr=None, update_hr=None):
        # Support both old API (hr=) and new independent control
        self.register_hr = register_hr if register_hr is not None else hr
        self.update_hr = update_hr if update_hr is not None else hr
        self.unregistered, self.updates = [], []

    def DwmRegisterThumbnail(self, dest, src, out):
        out._obj.value = 0xABC
        return self.register_hr

    def DwmUnregisterThumbnail(self, handle):
        self.unregistered.append(handle)
        return 0

    def DwmUpdateThumbnailProperties(self, handle, props):
        self.updates.append(props._obj)
        return self.update_hr


class FakeLibs:
    def __init__(self, dwm):
        self.dwmapi = dwm


def test_registration_failure_returns_none_not_an_exception():
    libs = FakeLibs(FakeDwm(hr=0x80004005))
    assert thumbnail.Thumbnail.register(libs, 1, 2) is None


def test_close_is_idempotent():
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.close()
    t.close()
    assert len(dwm.unregistered) == 1


def test_update_after_close_is_a_no_op():
    """The sweep can race a client closing; an update against a freed
    handle must not reach DWM."""
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.close()
    t.update(Rect(0, 0, 10, 10))
    assert dwm.updates == []


def test_update_sends_the_destination_rect_as_edges_not_extents():
    """DWM wants left/top/right/bottom. Passing width/height in the last
    two fields renders a thumbnail that is correct at the origin and
    wrong everywhere else -- easy to miss on a preview at (0,0)."""
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.update(Rect(5, 35, 310, 170))
    rc = dwm.updates[0].rcDestination
    assert (rc.left, rc.top, rc.right, rc.bottom) == (5, 35, 315, 205)


def test_update_returns_raw_hresult():
    dwm = FakeDwm(update_hr=-2147467259)
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    assert t.update(Rect(0, 0, 10, 10)) == -2147467259


def test_hresult_format_is_unsigned_and_fixed_width():
    assert thumbnail._format_hresult(-2147467259) == "0x80004005"
    assert thumbnail._format_hresult(0x80004005) == "0x80004005"


def test_update_after_close_returns_none():
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.close()
    assert t.update(Rect(0, 0, 10, 10)) is None


def test_update_without_source_preserves_full_client_flags():
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    t.update(Rect(5, 35, 310, 170))
    props = dwm.updates[0]
    assert props.dwFlags == (
        thumbnail.win32.DWM_TNP_RECTDESTINATION
        | thumbnail.win32.DWM_TNP_VISIBLE
        | thumbnail.win32.DWM_TNP_OPACITY
        | thumbnail.win32.DWM_TNP_SOURCECLIENTAREAONLY
    )


def test_update_with_source_sets_rectsource_as_edges():
    dwm = FakeDwm()
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 1, 2)
    assert t.update(Rect(0, 0, 320, 180), source_rect=Rect(100, 50, 400, 225)) == 0
    props = dwm.updates[0]
    assert props.dwFlags & thumbnail.win32.DWM_TNP_RECTSOURCE
    # SOURCECLIENTAREAONLY must remain set alongside RECTSOURCE: crop
    # coordinates are relative to the EVE client area, not outer-window
    # chrome, and a source-rect update that dropped this flag would mirror
    # the wrong pixels the moment a client had any non-client chrome.
    assert props.dwFlags & thumbnail.win32.DWM_TNP_SOURCECLIENTAREAONLY
    src = props.rcSource
    assert (src.left, src.top, src.right, src.bottom) == (100, 50, 500, 275)


def test_update_failure_logs_unsigned_hresult_and_handles(caplog):
    dwm = FakeDwm(update_hr=-2147467259)
    t = thumbnail.Thumbnail.register(FakeLibs(dwm), 0x10, 0x20)
    with caplog.at_level("WARNING"):
        t.update(Rect(0, 0, 10, 10), source_rect=Rect(1, 2, 3, 4))
    assert "hr=0x80004005" in caplog.text
    assert "src=0x20" in caplog.text
    assert "dest=0x10" in caplog.text


def test_successful_update_is_silent(caplog):
    t = thumbnail.Thumbnail.register(FakeLibs(FakeDwm()), 1, 2)
    with caplog.at_level("WARNING"):
        t.update(Rect(0, 0, 10, 10))
    assert "DwmUpdateThumbnailProperties failed" not in caplog.text
