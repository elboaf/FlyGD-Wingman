"""Only the gesture arithmetic is tested here -- window creation needs a
desktop and lives in the smoke checklist.

Click-versus-drag is where this goes subtly wrong: a click that moves one
pixel must still focus the client, and a locked preview must never move
but must still activate on release."""
from obs_youtube_uploader.preview import window
from obs_youtube_uploader.preview.geometry import Rect

R = Rect(100, 100, 320, 210)


def test_a_still_press_is_a_click():
    action, rect = window.drag_result((10, 10), (10, 10), R, locked=False,
                                      drag_min=4)
    assert action == "activate" and rect == R


def test_movement_within_the_drag_threshold_is_still_a_click():
    action, _ = window.drag_result((10, 10), (12, 11), R, locked=False,
                                   drag_min=4)
    assert action == "activate"


def test_movement_past_the_threshold_is_a_drag():
    action, rect = window.drag_result((10, 10), (60, 40), R, locked=False,
                                      drag_min=4)
    assert action == "move"
    assert rect == Rect(150, 130, 320, 210)


def test_a_locked_preview_never_moves_but_still_activates():
    """Locking exists so a carefully placed layout survives a stray drag.
    It must not also break click-to-focus."""
    action, rect = window.drag_result((10, 10), (200, 200), R, locked=True,
                                      drag_min=4)
    assert action == "activate" and rect == R


def test_resize_result_floors_at_the_minimum_size():
    """Dragging the handle up and left past zero must clamp, not invert
    the rect -- DWM rejects an inverted destination and the preview goes
    blank with no error."""
    out = window.resize_result((400, 300), (0, 0), R, min_size=(80, 60))
    assert out.w >= 80 and out.h >= 60


def test_resize_grows_from_the_top_left_anchor():
    out = window.resize_result((100, 100), (150, 130), R, min_size=(80, 60))
    assert (out.x, out.y) == (R.x, R.y)
    assert (out.w, out.h) == (R.w + 50, R.h + 30)


def test_activation_failure_is_visible_at_the_apps_log_level(caplog):
    """__main__.py:64 sets the root logger to INFO. A DEBUG line about a
    failed activation is therefore invisible in the only log a user will
    ever send -- which defeats the point of logging it at all."""
    class FakeUser32:
        def IsIconic(self, h):
            return False

        def GetForegroundWindow(self):
            return 999           # never becomes the target

        def GetWindowThreadProcessId(self, h, p):
            return 0

        def AttachThreadInput(self, a, b, c):
            return False

        def SetForegroundWindow(self, h):
            return True

    class FakeLibs:
        user32 = FakeUser32()
        kernel32 = type("K", (), {"GetCurrentThreadId": lambda self: 1})()

    with caplog.at_level("INFO"):
        assert window.activate(FakeLibs(), 123) is False
    assert any("Activation of" in r.message for r in caplog.records)


class _RecordingWindow(window.PreviewWindow):
    """PreviewWindow with the Win32 edges stubbed, to count renders."""

    def __init__(self, rect):
        class FakeUser32:
            def SetWindowPos(self, *a):
                return True

        class FakeLibs:
            user32 = FakeUser32()

        client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot",
                                "hwnd": 1})()
        super().__init__(FakeLibs(), client, rect, lambda c: None,
                         lambda *a: None, lambda: [], lambda: rect)
        self.hwnd = 1
        self.renders = 0

    def redraw(self, force=False):
        self.renders += 1


def test_a_pure_move_does_not_re_render_the_chrome():
    """A drag emits mouse-moves at >100Hz. Re-rendering a Pillow image and
    pushing ~67k pixels on each one is what made dragging stutter -- and
    none of it changes when only x/y do."""
    w = _RecordingWindow(Rect(100, 100, 320, 210))
    for i in range(30):
        w.move(Rect(100 + i, 100 + i, 320, 210))
    assert w.renders == 0


def test_a_resize_does_re_render():
    """The layered bitmap is sized to the window, so a resize must re-push
    it or the surface stays at the old dimensions."""
    w = _RecordingWindow(Rect(100, 100, 320, 210))
    w.move(Rect(100, 100, 400, 260))
    assert w.renders == 1
