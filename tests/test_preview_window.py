"""Only the gesture arithmetic is tested here -- window creation needs a
desktop and lives in the smoke checklist.

The button split is where this goes subtly wrong. Left is focus and
nothing else, and it fires on the way DOWN so the switch does not wait
for the button to come back up; right is movement; the corner is resize
and must not steal focus on the way past. There is no click-versus-drag
classification any more -- the thing that used to make a one-pixel
wobble still count as a click."""

import pytest

from wingman.preview import window
from wingman.preview.geometry import Rect

R = Rect(100, 100, 320, 210)


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


def test_resize_result_without_an_aspect_is_unchanged():
    """The existing signature must keep working: this is the fallback for
    a client at character select or one that quit mid-drag."""
    out = window.resize_result((100, 100), (150, 130), R, min_size=(80, 60))
    assert out.w == R.w + 50 and out.h == R.h + 30


def test_resize_result_with_an_aspect_locks_the_picture():
    out = window.resize_result(
        (0, 0), (200, 0), R, min_size=(80, 60), aspect=16 / 9, chrome=(4, 34)
    )
    assert abs((out.w - 4) / (out.h - 34) - 16 / 9) < 0.01


def test_resize_result_respects_the_label_band_being_off():
    """Same drag, labels off: the window is 30px shorter for the same
    picture. window.py reads _label_h() live at every other call site."""
    on = window.resize_result(
        (0, 0), (200, 0), R, min_size=(80, 60), aspect=16 / 9, chrome=(4, 34)
    )
    off = window.resize_result(
        (0, 0), (200, 0), R, min_size=(80, 60), aspect=16 / 9, chrome=(4, 4)
    )
    assert on.h - off.h == 30


# A rect ALREADY at 16:9 once the chrome is removed: picture 640x360
# inside a 644x394 window. This is the state every preview is in after
# its first locked drag, which is what makes the dead handle below the
# common case rather than an edge one.
LOCKED = Rect(100, 100, 644, 394)
CHROME = (4, 34)


def test_resize_shrinks_on_a_horizontal_drag_with_the_aspect_locked():
    """The user drags the handle left; the preview must get smaller.

    This was a dead handle. `lock_to_aspect` believed whichever axis
    implied the LARGER picture, so an untouched height beat a shortened
    width and the rect came back byte-identical -- growing worked from
    either axis, shrinking from neither alone.
    """
    out = window.resize_result(
        (200, 200), (100, 200), LOCKED, min_size=(80, 60), aspect=16 / 9, chrome=CHROME
    )
    assert out.w < LOCKED.w
    assert abs((out.w - 4) / (out.h - 34) - 16 / 9) < 0.01


def test_resize_shrinks_on_a_vertical_drag_with_the_aspect_locked():
    """The same dead handle in Y: dragging up alone did nothing."""
    out = window.resize_result(
        (200, 200), (200, 100), LOCKED, min_size=(80, 60), aspect=16 / 9, chrome=CHROME
    )
    assert out.h < LOCKED.h
    assert abs((out.w - 4) / (out.h - 34) - 16 / 9) < 0.01


def test_resize_believes_the_axis_the_user_actually_dragged():
    """A mostly-vertical drag is driven by height, a mostly-horizontal one
    by width. Keeping a mostly-vertical drag effective is what the old
    max() was protecting, and the dominant axis preserves that without
    breaking shrink."""
    vertical = window.resize_result(
        (0, 0), (10, 200), LOCKED, min_size=(80, 60), aspect=16 / 9, chrome=CHROME
    )
    assert vertical.h == LOCKED.h + 200
    horizontal = window.resize_result(
        (0, 0), (200, 10), LOCKED, min_size=(80, 60), aspect=16 / 9, chrome=CHROME
    )
    assert horizontal.w == LOCKED.w + 200


TARGET = 123
FOREGROUND = 999
OUR_TID = 1
FOREGROUND_TID = 2
TARGET_TID = 3


def _activation_libs(
    foregrounds,
    calls,
    *,
    iconic=False,
    foreground_tid=FOREGROUND_TID,
    target_tid=TARGET_TID,
    attached_tids=(FOREGROUND_TID, TARGET_TID),
    set_foreground_error=None,
):
    class FakeUser32:
        def __init__(self):
            self._foregrounds = iter(foregrounds)

        def IsIconic(self, h):
            return iconic

        def ShowWindowAsync(self, h, command):
            calls.append(("show", h, command))
            return True

        def GetForegroundWindow(self):
            value = next(self._foregrounds)
            calls.append(("get_foreground", value))
            return value

        def GetWindowThreadProcessId(self, h, p):
            return target_tid if h == TARGET else foreground_tid

        def AttachThreadInput(self, source, destination, attach):
            calls.append(("attach", source, destination, attach))
            return destination in attached_tids

        def SetForegroundWindow(self, h):
            calls.append(("set_foreground", h))
            if set_foreground_error is not None:
                raise set_foreground_error
            return False

        def SetFocus(self, h):
            calls.append(("set_focus", h))
            return 0

    class FakeLibs:
        user32 = FakeUser32()
        kernel32 = type("K", (), {"GetCurrentThreadId": lambda self: OUR_TID})()

    return FakeLibs()


def test_iconic_target_defers_foreground_work_until_restore():
    """A browser must retain foreground while a minimized EVE client restores.

    Calling SetForegroundWindow before the restore lands briefly leaves no
    usable foreground under hide-on-lost-focus, which flashed the desktop in
    Windows smoke. The timer retry owns foreground work once IsIconic is false.
    """
    calls = []

    class FakeUser32:
        def IsIconic(self, hwnd):
            calls.append(("is_iconic", hwnd))
            return True

        def ShowWindowAsync(self, hwnd, command):
            calls.append(("show", hwnd, command))
            return True

    libs = type("Libs", (), {"user32": FakeUser32()})()

    assert window.activate(libs, TARGET) is window.ActivationResult.PENDING_RESTORE
    assert calls == [
        ("is_iconic", TARGET),
        ("show", TARGET, window.win32.SW_RESTORE),
    ]


def test_non_iconic_target_already_foreground_skips_attachments():
    calls = []
    libs = _activation_libs([TARGET], calls)

    assert window.activate(libs, TARGET) is window.ActivationResult.ACTIVATED
    assert calls == [("get_foreground", TARGET)]


def test_activation_observes_foreground_before_focusing_target():
    """A live target can be foreground but focusless unless keyboard focus is
    assigned while its queue remains attached. SetFocus's return is not a
    verdict; the foreground observation gates it and classifies activation.
    """
    calls = []
    libs = _activation_libs([FOREGROUND, TARGET], calls)

    assert window.activate(libs, TARGET) is window.ActivationResult.ACTIVATED
    assert calls == [
        ("get_foreground", FOREGROUND),
        ("attach", OUR_TID, FOREGROUND_TID, True),
        ("attach", OUR_TID, TARGET_TID, True),
        ("set_foreground", TARGET),
        ("get_foreground", TARGET),
        ("set_focus", TARGET),
        ("attach", OUR_TID, TARGET_TID, False),
        ("attach", OUR_TID, FOREGROUND_TID, False),
    ]


def test_equal_foreground_and_target_threads_are_attached_once():
    calls = []
    libs = _activation_libs([FOREGROUND, TARGET], calls, target_tid=FOREGROUND_TID)

    assert window.activate(libs, TARGET) is window.ActivationResult.ACTIVATED
    assert [call for call in calls if call[0] == "attach"] == [
        ("attach", OUR_TID, FOREGROUND_TID, True),
        ("attach", OUR_TID, FOREGROUND_TID, False),
    ]


def test_activation_refusal_does_not_focus_the_target_and_detaches_in_reverse_order():
    calls = []
    libs = _activation_libs([FOREGROUND, FOREGROUND], calls)

    assert window.activate(libs, TARGET) is window.ActivationResult.REFUSED
    assert calls == [
        ("get_foreground", FOREGROUND),
        ("attach", OUR_TID, FOREGROUND_TID, True),
        ("attach", OUR_TID, TARGET_TID, True),
        ("set_foreground", TARGET),
        ("get_foreground", FOREGROUND),
        ("attach", OUR_TID, TARGET_TID, False),
        ("attach", OUR_TID, FOREGROUND_TID, False),
    ]


def test_activation_exception_detaches_every_successful_attachment_in_reverse():
    calls = []
    libs = _activation_libs(
        [FOREGROUND], calls, set_foreground_error=RuntimeError("foreground failed")
    )

    with pytest.raises(RuntimeError, match="foreground failed"):
        window.activate(libs, TARGET)

    assert [call for call in calls if call[0] == "attach"] == [
        ("attach", OUR_TID, FOREGROUND_TID, True),
        ("attach", OUR_TID, TARGET_TID, True),
        ("attach", OUR_TID, TARGET_TID, False),
        ("attach", OUR_TID, FOREGROUND_TID, False),
    ]


def test_failed_attachment_is_not_detached():
    calls = []
    libs = _activation_libs([FOREGROUND, TARGET], calls, attached_tids=(TARGET_TID,))

    assert window.activate(libs, TARGET) is window.ActivationResult.ACTIVATED
    assert [call for call in calls if call[0] == "attach"] == [
        ("attach", OUR_TID, FOREGROUND_TID, True),
        ("attach", OUR_TID, TARGET_TID, True),
        ("attach", OUR_TID, TARGET_TID, False),
    ]


def test_pending_restore_does_not_log_a_foreground_refusal(caplog):
    calls = []
    libs = _activation_libs([TARGET, FOREGROUND, FOREGROUND], calls, iconic=True)

    with caplog.at_level("INFO"):
        assert window.activate(libs, TARGET) is window.ActivationResult.PENDING_RESTORE

    assert not any("Windows refuses" in record.message for record in caplog.records)


def test_activation_failure_is_visible_at_the_apps_log_level(caplog):
    """__main__.py:64 sets the root logger to INFO. A DEBUG line about a
    failed activation is therefore invisible in the only log a user will
    ever send -- which defeats the point of logging it at all."""
    calls = []
    libs = _activation_libs([FOREGROUND, FOREGROUND], calls)

    with caplog.at_level("INFO"):
        assert window.activate(libs, TARGET) is window.ActivationResult.REFUSED
    assert any("Activation of" in r.message for r in caplog.records)


class _RecordingWindow(window.PreviewWindow):
    """PreviewWindow with the Win32 edges stubbed, to count renders."""

    def __init__(self, rect, opacity=255):
        class FakeUser32:
            def SetWindowPos(self, *a):
                return True

        class FakeLibs:
            user32 = FakeUser32()

        client = type(
            "C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1}
        )()
        super().__init__(
            FakeLibs(),
            client,
            rect,
            lambda c: None,
            lambda *a: None,
            list,
            lambda: rect,
            opacity=opacity,
        )
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


def test_coalesce_moves_keeps_only_the_newest_position():
    """A drag delivers moves faster than a preview can be moved (measured:
    320/s against a 1.8ms handler). Processing every one builds a backlog
    and the window lags the cursor -- which is what the stutter is. Only
    the newest position can be correct."""

    queued = [111, 222, 333]

    def fake_peek(msg_ptr, hwnd, lo, hi, flags):
        if not queued:
            return False
        msg_ptr._obj.lParam = queued.pop(0)
        return True

    assert window.coalesce_moves(fake_peek, 1, 999) == 333


def test_coalesce_moves_returns_the_original_when_the_queue_is_empty():
    """The common case at the start of a slow drag: nothing queued behind
    this event, so the position it carried is the one to use."""
    assert window.coalesce_moves(lambda *a: False, 1, 42) == 42


def test_a_stationary_cursor_does_not_move_the_rect():
    """The vibration bug, as a test.

    Holding the button with the cursor completely still must produce the
    same rect every time. It did not: lParam is client-relative to the
    window's CURRENT position, and it was converted to screen coordinates
    using the position at button-down. Once the window moved, the target
    overshot, the window moved back, that generated another WM_MOUSEMOVE,
    and it oscillated -- visibly vibrating with the mouse held still.
    """
    start_cursor = (500, 400)
    for _ in range(10):
        out = window.drag_target(start_cursor, start_cursor, R)
        assert out == R


def test_the_target_is_independent_of_where_the_window_has_moved_to():
    """Absolute coordinates cannot feed back: the answer depends only on
    how far the CURSOR moved, never on where the window ended up."""
    a = window.drag_target((500, 400), (560, 430), Rect(100, 100, 320, 210))
    b = window.drag_target((500, 400), (560, 430), Rect(100, 100, 320, 210))
    assert a == b == Rect(160, 130, 320, 210)


def test_dragging_back_to_the_origin_restores_the_original_rect():
    """A round trip must land exactly where it started -- no drift
    accumulating across a long drag."""
    start = (500, 400)
    moved = window.drag_target(start, (900, 700), R)
    assert moved != R
    assert window.drag_target(start, start, R) == R


def test_show_labels_left_the_chrome_key():
    """The name is an overlay window now, so the chrome bitmap is the
    same with labels on or off -- and the key must say so, or every
    label toggle forces a full-bitmap re-render for nothing. Toggling
    is set_labels' job, not redraw()'s."""
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    on_key = window.PreviewWindow(
        None,
        client,
        R,
        lambda c: None,
        lambda *a: None,
        list,
        lambda: R,
        show_labels=True,
    )._chrome_key()
    off_key = window.PreviewWindow(
        None,
        client,
        R,
        lambda c: None,
        lambda *a: None,
        list,
        lambda: R,
        show_labels=False,
    )._chrome_key()
    assert on_key == off_key


class _FakeThumb:
    """Records every (rect, opacity) passed to update(), standing in for
    the real Thumbnail that move() would otherwise touch."""

    def __init__(self):
        self.calls = []

    def update(self, rect, opacity=255):
        self.calls.append((rect, opacity))


def test_a_resize_updates_the_thumbnail_rect_to_the_full_interior():
    """The video runs the full interior whether labels are on or off --
    the name is an overlay now, so the flag must not change the picture
    by a single pixel."""
    for show_labels in (True, False):
        w = _RecordingWindow(Rect(100, 100, 320, 210))
        w.show_labels = show_labels
        thumb = _FakeThumb()
        w._thumb = thumb
        new_rect = Rect(100, 100, 400, 260)
        w.move(new_rect)
        assert thumb.calls == [
            (window.geometry.thumbnail_rect(new_rect, window.BORDER), 255)
        ]
        assert thumb.calls[0][0].h == new_rect.h - window.BORDER * 2


def test_a_resize_passes_the_configured_opacity_to_the_thumbnail():
    """opacity is a DWM thumbnail property, not a bitmap one -- see the
    comment on _chrome_key(). It must reach Thumbnail.update() on every
    resize, or every preview stays stuck at the default full opacity no
    matter what the user configured.

    Dropping `self.opacity` from the update() call at window.py's move()
    site turned this red (the recorded call fell back to update()'s
    opacity=255 default instead of 180) -- checked by hand while writing
    this test, then restored."""
    w = _RecordingWindow(Rect(100, 100, 320, 210), opacity=180)
    thumb = _FakeThumb()
    w._thumb = thumb
    w.move(Rect(100, 100, 400, 260))
    assert thumb.calls[-1][1] == 180


def test_opacity_does_not_join_the_chrome_key():
    """opacity never touches the Pillow bitmap -- it's a DWM thumbnail
    property applied separately in Thumbnail.update(). Putting it in the
    cache key would force a ~67k-pixel re-render on every opacity change,
    which is the exact stutter redraw()'s short-circuit exists to avoid."""
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    dim_key = window.PreviewWindow(
        None,
        client,
        R,
        lambda c: None,
        lambda *a: None,
        list,
        lambda: R,
        opacity=60,
    )._chrome_key()
    bright_key = window.PreviewWindow(
        None,
        client,
        R,
        lambda c: None,
        lambda *a: None,
        list,
        lambda: R,
        opacity=255,
    )._chrome_key()
    assert dim_key == bright_key


def test_redraw_renders_no_label_and_no_layered_band(monkeypatch):
    """redraw() draws chrome only: the name lives in the overlay window,
    so chrome.render must be called with no label at all -- a label term
    creeping back here would draw a band the thumbnail overpaints and
    the aspect logic no longer accounts for."""
    calls = []

    def fake_render(size, **kwargs):
        calls.append(kwargs)
        return type("_Img", (), {"size": size})()

    monkeypatch.setattr(window.chrome, "render", fake_render)
    monkeypatch.setattr(window.layered, "push", lambda *a, **k: None)

    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    for show_labels in (True, False):
        w = window.PreviewWindow(
            None,
            client,
            R,
            lambda c: None,
            lambda *a: None,
            list,
            lambda: R,
            show_labels=show_labels,
        )
        w.hwnd = 1
        w.redraw()
    assert len(calls) == 2
    for kwargs in calls:
        assert "label" not in kwargs and "label_h" not in kwargs


class _FakeLibs:
    """Just enough Win32 for _on_message, with the cursor under our control."""

    def __init__(self, cursor=(0, 0)):
        self.cursor = cursor
        outer = self

        class User32:
            def SetCapture(self, h):
                return h

            def ReleaseCapture(self):
                return True

            def SetWindowPos(self, *a):
                return True

            def GetCursorPos(self, ptr):
                ptr._obj.x, ptr._obj.y = outer.cursor
                return True

            def PeekMessageW(self, *a):
                return False  # nothing queued behind this event

            def GetClientRect(self, hwnd, ptr):
                # Called on every button-down now (Task 3), not only during
                # a resize -- these gesture tests need it to succeed even
                # though none of them exercise the aspect lock itself.
                ptr._obj.left, ptr._obj.top = 0, 0
                ptr._obj.right, ptr._obj.bottom = 320, 210
                return True

        self.user32 = User32()


def _window_for_gestures(locked, on_activate=lambda c: None, on_resize_all=None):
    client = type(
        "C",
        (),
        {
            "character": "Pilot",
            "title": "EVE - Pilot",
            "hwnd": 1,
            "stable_key": "Pilot",
        },
    )()
    libs = _FakeLibs()
    w = window.PreviewWindow(
        libs,
        client,
        Rect(100, 100, 320, 210),
        on_activate,
        lambda *a: None,
        list,
        lambda: Rect(0, 0, 1920, 1080),
        locked=locked,
        on_resize_all=on_resize_all,
    )
    w.hwnd = 1
    w.redraw = lambda force=False: None
    return w, libs


def test_a_left_click_activates_on_release(monkeypatch):
    """A press that never crosses CLICK_PX is a click, and the switch
    fires on WM_LBUTTONUP. Button-down can no longer decide: left-drag
    moves the preview now, and at press time it is not yet knowable
    whether this is a click or a drag. EVE-O Preview makes the same trade
    for the same gesture set."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    assert activated == []  # not yet -- the press is still undetermined
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == [w.client]


def test_the_left_release_does_not_activate_a_second_time(monkeypatch):
    """The release switched. A drag afterwards that switched again would
    run the whole minimize/activate sequence twice per click."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == [w.client]


def test_a_left_drag_moves_the_preview(monkeypatch):
    """Left-drag is the move gesture now -- the one you want near the
    preview you are looking at -- and it deliberately does NOT switch the
    client: dragging a preview around is not a request to bring its
    client forward."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert w.rect == Rect(150, 160, 320, 210)
    assert activated == []


def test_a_left_wiggle_under_the_threshold_is_still_a_click(monkeypatch):
    """CLICK_PX exists so the deferred switch does not turn every jittery
    click into a drag. A press that wanders a couple of pixels and
    releases must still switch."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (202, 201)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == [w.client]


def test_a_right_drag_resizes_the_preview():
    """Right-drag is resize, not move: the deliberate second button for
    the gesture you want less often. Top-left anchored, like the corner
    handle."""
    w, libs = _window_for_gestures(locked=False)
    # Freeform: the locked aspect would re-shape the result away
    # from the pointer deltas these tests assert on.
    w.lock_aspect = False

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)

    assert w.rect == Rect(100, 100, 370, 270)


def test_a_right_drag_release_reports_the_new_rect():
    """The layout is only persisted from the rect reported on release."""
    w, libs = _window_for_gestures(locked=False)
    reported = []
    w._on_rect_changed = lambda *a: reported.append(a)
    # Freeform: the locked aspect would re-shape the result away
    # from the pointer deltas these tests assert on.
    w.lock_aspect = False

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)
    w._on_message(window.win32.WM_RBUTTONUP, 2, 0)

    assert reported == [("Pilot", Rect(100, 100, 370, 270), False)]


def test_a_locked_preview_refuses_the_left_drag(monkeypatch):
    """A lock means nothing about the preview may change by mouse. The
    locked left press switches immediately -- there is no drag gesture
    left for it to become -- so this press activated on the way DOWN and
    the subsequent move is arriving at a window with no armed gesture."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=True, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert w.rect == Rect(100, 100, 320, 210)
    assert activated == [w.client]


def test_a_locked_preview_refuses_the_right_drag_resize():
    """A lock stops SIZING too, not just movement: right-drag resize is
    refused outright while locked. Unticking Lock is the way to resize."""
    w, libs = _window_for_gestures(locked=True)
    w.lock_aspect = False

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)
    w._on_message(window.win32.WM_RBUTTONUP, 2, 0)

    assert w.rect == Rect(100, 100, 320, 210)


def test_a_locked_preview_refuses_the_resize_all_chord(monkeypatch):
    """Left+right is a resize gesture like any other; the lock refuses
    it. The chord never arms at all: the first (left) press already
    switched, and the second (right) press arrives on a locked window
    with no gesture in flight."""
    mirrored = []
    activated = []
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    w, libs = _window_for_gestures(
        locked=True, on_activate=activated.append, on_resize_all=mirrored.append
    )

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)

    assert w.rect == Rect(100, 100, 320, 210)
    assert mirrored == []


def test_a_locked_preview_still_focuses_its_client_on_the_way_down(monkeypatch):
    """A lock stops gesture handling, never focus switching -- and with
    every drag refused, the locked switch is free to fire on WM_LBUTTONDOWN
    again (#123's shape): no classification delay is needed when no press
    can become anything but a click."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=True, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)

    assert activated == [w.client]


def test_a_locked_left_press_on_the_resize_corner_still_switches(monkeypatch):
    """The lock refuses sizing by ANY route, the corner handle included --
    so a locked press there is just a click, and a click switches. The
    unlocked corner test below pins the opposite for the same reason."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=True, on_activate=activated.append)

    corner = (319 & 0xFFFF) | ((209 & 0xFFFF) << 16)
    libs.cursor = (419, 309)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, corner)

    assert activated == [w.client]
    assert w._mode is None


def test_the_resize_corner_does_not_activate(monkeypatch):
    """Grabbing the handle is a resize, not a switch. Activating there
    would drag the client to the foreground every time the user adjusted
    a preview's size."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    # Bottom-right corner of a 320x210 window at the origin, in client
    # coordinates: geometry.hit_resize_handle's own frame.
    corner = (319 & 0xFFFF) | ((209 & 0xFFFF) << 16)
    libs.cursor = (419, 309)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, corner)

    assert activated == []
    assert w._mode == "resize"


def test_the_switch_is_handed_to_the_host_not_performed_here(monkeypatch):
    """The window classifies the gesture; the host performs the switch.

    Both halves matter and both are plausible ways to break this. If the
    window keeps calling activate() the switch happens twice and the host
    reads a foreground that has already moved; if the callback is
    dropped, clicking a preview silently does nothing at all.
    """
    activate_calls = []
    monkeypatch.setattr(
        window, "activate", lambda libs, hwnd: activate_calls.append(hwnd) or True
    )
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == [w.client]
    assert activate_calls == []


def test_a_both_button_drag_resizes_every_window_through_the_host():
    """Left+right is the resize-ALL chord: the dragged window resizes
    normally, and its finished size is handed to the host callback so
    every OTHER preview can mirror it. The window hands it off rather
    than touching siblings itself because it does not know they exist."""
    mirrored = []
    w, libs = _window_for_gestures(locked=False, on_resize_all=mirrored.append)
    # Freeform: the locked aspect would re-shape the result away
    # from the pointer deltas these tests assert on.
    w.lock_aspect = False

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    # The chord's second button reclassifies the gesture BEFORE any move
    # happens, so the pending click is cancelled and no switch fires.
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)

    assert w.rect == Rect(100, 100, 370, 270)
    assert mirrored == [Rect(100, 100, 370, 270)]


# --- the ring and the foreground are separate flags --------------------------
#
# They were one flag until a sticky ring was asked for. `selected` draws
# the ring and now survives tabbing out to a browser; `focused` means the
# client really does hold the foreground, and it alone decides whether an
# alert counts as seen. Conflating them again is exactly the regression
# these tests exist to catch: the ring would go back to blinking off
# whenever you left EVE, or a persistent alert on the client you last used
# would expire unread while you were reading Discord.


class _FakeAlert:
    color = "#ff4d4d"
    # Persistent: alerts_state.acknowledge reads this, and set_focused(True)
    # runs the real acknowledgement path against whatever arm returned.
    expires = None


def _bare_window(**kw):
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    return window.PreviewWindow(
        None, client, R, lambda c: None, lambda *a: None, list, lambda: R, **kw
    )


class _ShowRecorder:
    """Records ShowWindow calls; set_hidden touches nothing else."""

    def __init__(self):
        self.shown = []
        outer = self

        class User32:
            def ShowWindow(self, hwnd, cmd):
                outer.shown.append((hwnd, cmd))
                return True

        self.user32 = User32()


def _hidable_window():
    libs = _ShowRecorder()
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    w = window.PreviewWindow(
        libs, client, R, lambda c: None, lambda *a: None, list, lambda: R
    )
    w.hwnd = 77
    return w, libs


def test_a_preview_starts_visible():
    w, _ = _hidable_window()
    assert w.hidden is False


def test_hiding_calls_show_window_with_sw_hide():
    w, libs = _hidable_window()

    w.set_hidden(True)

    assert w.hidden is True
    assert libs.shown == [(77, window.win32.SW_HIDE)]


def test_showing_again_does_not_activate_the_preview():
    """SW_SHOWNOACTIVATE, never SW_SHOW: these windows are WS_EX_NOACTIVATE
    and must never take the foreground away from the client the user is
    flying. SW_SHOW on a re-show would undo that on every alt-tab back."""
    w, libs = _hidable_window()
    w.set_hidden(True)
    libs.shown.clear()

    w.set_hidden(False)

    assert w.hidden is False
    assert libs.shown == [(77, window.win32.SW_SHOWNOACTIVATE)]


def test_set_hidden_is_idempotent():
    """_apply_visibility runs every sweep and every foreground change, so
    an unchanged flag must cost one attribute compare -- not a ShowWindow
    call several times a second."""
    w, libs = _hidable_window()

    w.set_hidden(True)
    w.set_hidden(True)
    w.set_hidden(True)

    assert libs.shown == [(77, window.win32.SW_HIDE)]


def test_hiding_a_window_that_was_never_created_does_nothing():
    """Creation can fail (window.py's create returns None on a failed
    CreateWindowExW), and a sweep that hides everything must not pass a
    null hwnd to ShowWindow."""
    w, libs = _hidable_window()
    w.hwnd = None

    w.set_hidden(True)

    assert w.hidden is True
    assert libs.shown == []


def test_the_ring_alone_does_not_acknowledge_an_alert(monkeypatch):
    """Ringing a preview is now just "this is the client you last used" and
    says nothing about whether anyone looked at it."""
    w = _bare_window()
    monkeypatch.setattr(window.PreviewWindow, "redraw", lambda self, force=False: None)
    acked = []
    monkeypatch.setattr(
        window.PreviewWindow, "acknowledge_alert", lambda self: acked.append(True)
    )

    w.set_selected(True)

    assert w.selected is True
    assert acked == []


def test_taking_the_foreground_acknowledges_a_persistent_alert(monkeypatch):
    """The acknowledgement moved off set_selected, and this is where it
    landed. It has to stay the single choke point every route to the
    client passes through -- clicking the preview, a cycle keybind and
    plain alt-tab all arrive as a foreground change."""
    w = _bare_window()
    acked = []
    monkeypatch.setattr(
        window.PreviewWindow, "acknowledge_alert", lambda self: acked.append(True)
    )

    w.set_focused(True)
    w.set_focused(True)  # idempotent: a re-sweep must not re-acknowledge

    assert w.focused is True
    assert acked == [True]


def test_an_alert_on_a_ringed_but_unfocused_client_is_persistent(monkeypatch):
    """`target_is_selected` tells alerts/state.py "you are already looking
    at this, so let it expire". Feeding it the sticky ring would mean the
    client you last used never raises a persistent alert again."""
    w = _bare_window()
    monkeypatch.setattr(window.PreviewWindow, "redraw", lambda self, force=False: None)
    monkeypatch.setattr(window.PreviewWindow, "_rebuild_frames", lambda self: None)
    monkeypatch.setattr(window.PreviewWindow, "_set_inset", lambda self, px: None)
    seen = []
    monkeypatch.setattr(
        window.alerts_state,
        "arm",
        lambda *a, **kw: seen.append(kw["target_is_selected"]) or _FakeAlert(),
    )

    w.set_selected(True)  # ringed, but the foreground is a browser
    w.arm_alert("combat", {"persist_until_selected": True}, 0.0)
    w.set_focused(True)  # now you actually switched to it
    w.arm_alert("combat", {"persist_until_selected": True}, 0.0)

    assert seen == [False, True]


def test_a_preview_defaults_to_snapping():
    """The attribute exists before any restyle lands, so a preview created
    between launch and the first settings push still snaps."""
    assert window.PreviewWindow.snap is True


def _resize_drag(lock_aspect):
    """Grab the bottom-right handle of a 320x210 preview whose client is
    320x210 (a 32:21 source, per _FakeLibs.GetClientRect) and drag it
    100px right and 0px down."""
    w, libs = _window_for_gestures(locked=False)
    w.lock_aspect = lock_aspect
    libs.cursor = (100 + 320 - 4, 100 + 210 - 4)  # inside the resize handle
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, _lparam(316, 206))
    libs.cursor = (libs.cursor[0] + 100, libs.cursor[1])
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    return w.rect


def _lparam(x, y):
    return (y << 16) | x


def test_a_resize_holds_the_client_shape_while_the_aspect_is_locked():
    """The default, and what has always shipped: a purely horizontal drag
    still changes the height, because the picture keeps its ratio.

    Asserted as the ratio rather than `h != 210`, which passed just as
    readily for a height of 3 and never checked the one thing the test is
    named after. _FakeLibs.GetClientRect reports 320x210, so the picture
    must come back at 32:21 once the chrome is removed -- and the chrome
    is now the BORDER alone, which is the point of the overlay: labels on
    or off, the window is picture + 2px on each side and nothing else."""
    rect = _resize_drag(lock_aspect=True)
    assert rect.w == 420
    assert abs((rect.w - 4) / (rect.h - 4) - 320 / 210) < 0.01


def test_unlocking_the_aspect_makes_the_handle_freeform():
    """The escape hatch. Width follows the pointer and the height is left
    exactly where it was -- the picture stretches, which is the documented
    cost and the same one a mismatched typed size already carries."""
    rect = _resize_drag(lock_aspect=False)
    assert rect.w == 420
    assert rect.h == 210


# --- the selection ring's colour is a setting, not a constant ---------------


def test_the_ring_colour_parses_from_rrggbb_and_falls_back_to_cyan():
    """The window stores the settings string verbatim and parses per
    redraw; an unparsable value falls back to the shipped cyan rather
    than raising mid-drag."""
    w, _libs = _window_for_gestures(locked=False)
    w.selection_color = "#ff5a00"
    assert w._border_color() == (255, 90, 0, 255)
    w.selection_color = "#00c8dc"
    assert w._border_color() == (0, 200, 220, 255)
    w.selection_color = "purple"  # hand-edited settings file
    assert w._border_color() == (0, 200, 220, 255)
    w.selection_color = 7
    assert w._border_color() == (0, 200, 220, 255)


def test_the_ring_colour_participates_in_the_chrome_cache_key():
    """Without the colour in the key, a recolour is a no-op on every
    already-open preview: redraw() short-circuits on an unchanged key and
    the bitmap never repaints -- the exact trap show_labels documents."""
    w, _libs = _window_for_gestures(locked=False)
    base = w._chrome_key()
    w.selection_color = "#ff5a00"
    assert w._chrome_key() != base


# --- the name overlay: a window, not a band ---------------------------------


class _OverlayLibs:
    """Records the Win32 calls the overlay path makes; cursor unused."""

    def __init__(self):
        outer = self
        self.created = []
        self.destroyed = []

        class Kernel32:
            def GetModuleHandleW(self, *_):
                return 1

        class User32:
            def CreateWindowExW(self, ex, cls, name, style, *rest):
                outer.created.append((ex, cls))
                return 0x9000 + len(outer.created)

            def DestroyWindow(self, hwnd):
                outer.destroyed.append(hwnd)
                return True

            def SetWindowPos(self, *a):
                return True

            def ShowWindow(self, hwnd, cmd):
                return True

        self.kernel32 = Kernel32()
        self.user32 = User32()


def _overlay_window(show_labels=True):
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    libs = _OverlayLibs()
    w = window.PreviewWindow(
        libs,
        client,
        Rect(100, 100, 320, 210),
        lambda c: None,
        lambda *a: None,
        list,
        lambda: Rect(0, 0, 1920, 1080),
        show_labels=show_labels,
    )
    w.hwnd = 1
    w.redraw = lambda force=False: None
    return w, libs


def _pill_image(w=90, h=27):
    return type("_Img", (), {"size": (w, h)})()


def test_set_labels_creates_and_destroys_the_overlay_window(monkeypatch):
    """The pill rides in its own WS_EX_LAYERED|WS_EX_TRANSPARENT window,
    owned by the preview: owned composites above the owner -- above the
    DWM thumbnail, which is the whole point -- and the style pair makes
    it click-through so no mouse gesture is stolen from the preview."""
    monkeypatch.setattr(window.chrome, "render_label", lambda *a: _pill_image())
    monkeypatch.setattr(window.layered, "push", lambda *a, **k: None)
    w, libs = _overlay_window(show_labels=False)
    assert w._label_hwnd is None

    w.set_labels(True)
    assert w._label_hwnd == 0x9001
    ex, cls = libs.created[0]
    flags = window.win32.WS_EX_LAYERED | window.win32.WS_EX_TRANSPARENT
    assert ex & flags == flags
    assert cls == "STATIC"  # a system class: no wndproc of ours to leak
    assert libs.destroyed == []

    w.set_labels(False)
    assert w._label_hwnd is None
    assert libs.destroyed == [0x9001]


def test_the_overlay_is_repositioned_by_every_move(monkeypatch):
    """The overlay is a separate HWND in screen coordinates; a move of the
    preview must carry it, or the name stays behind over whatever slid
    into its old corner."""
    pushed = []
    monkeypatch.setattr(window.chrome, "render_label", lambda *a: _pill_image())
    monkeypatch.setattr(
        window.layered, "push", lambda libs, hwnd, img, x, y: pushed.append((x, y))
    )
    w, _libs = _overlay_window()
    w._ensure_label_overlay()
    pushed.clear()

    w.move(Rect(400, 500, 320, 210))  # pure move, no resize

    assert pushed == [(400 + window.BORDER, 500 + window.BORDER)]


def test_the_overlay_re_renders_only_when_the_width_forces_it(monkeypatch):
    """The render cache is keyed on (label, available width): a drag
    re-renders the pill only when the width crosses the ellipsize
    threshold, keeping the per-mousemove cost to one small push."""
    renders = []

    def fake_label(label, max_w):
        renders.append(max_w)
        return _pill_image()

    monkeypatch.setattr(window.chrome, "render_label", fake_label)
    monkeypatch.setattr(window.layered, "push", lambda *a, **k: None)
    w, _libs = _overlay_window()
    w._ensure_label_overlay()
    w.move(Rect(100, 100, 330, 210))  # wider, text still fits the same way
    w.move(Rect(100, 100, 340, 210))
    w._sync_label()  # same width again: cache stands
    assert len(renders) == 1


def test_set_hidden_takes_the_overlay_with_the_preview(monkeypatch):
    """An owned window does not follow its owner into hiding: a hidden
    preview would leave its name floating over whatever moved in."""
    shown = []

    def fake_show(hwnd, cmd):
        shown.append(cmd)

    monkeypatch.setattr(window.chrome, "render_label", lambda *a: _pill_image())
    monkeypatch.setattr(window.layered, "push", lambda *a, **k: None)
    w, libs = _overlay_window()
    w._ensure_label_overlay()
    libs.user32.ShowWindow = fake_show

    w.set_hidden(True)
    assert window.win32.SW_HIDE in shown
    shown.clear()
    w.set_hidden(False)
    assert window.win32.SW_SHOWNOACTIVATE in shown


def test_close_destroys_the_overlay(monkeypatch):
    monkeypatch.setattr(window.chrome, "render_label", lambda *a: _pill_image())
    monkeypatch.setattr(window.layered, "push", lambda *a, **k: None)
    w, libs = _overlay_window()
    w._ensure_label_overlay()

    w.close()

    assert 0x9001 in libs.destroyed
    assert w._label_hwnd is None
