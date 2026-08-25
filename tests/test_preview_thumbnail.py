"""Lifecycle only -- the DWM calls are faked. What matters here is that a
failed registration degrades instead of raising, and that close() is
idempotent: a double-unregister is a use-after-free in DWM's handle
table, and the crash lands nowhere near this file."""

from obs_youtube_uploader.preview import thumbnail
from obs_youtube_uploader.preview.geometry import Rect


class FakeDwm:
    def __init__(self, hr=0):
        self.hr, self.unregistered, self.updates = hr, [], []

    def DwmRegisterThumbnail(self, dest, src, out):
        out._obj.value = 0xABC
        return self.hr

    def DwmUnregisterThumbnail(self, handle):
        self.unregistered.append(handle)
        return 0

    def DwmUpdateThumbnailProperties(self, handle, props):
        self.updates.append(props._obj)
        return 0


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
