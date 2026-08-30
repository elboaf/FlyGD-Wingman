"""Only the gesture arithmetic is tested here -- window creation needs a
desktop and lives in the smoke checklist.

The button split is where this goes subtly wrong. Left is focus and
nothing else, and it fires on the way DOWN so the switch does not wait
for the button to come back up; right is movement; the corner is resize
and must not steal focus on the way past. There is no click-versus-drag
classification any more -- the thing that used to make a one-pixel
wobble still count as a click."""

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


def test_activation_failure_is_visible_at_the_apps_log_level(caplog):
    """__main__.py:64 sets the root logger to INFO. A DEBUG line about a
    failed activation is therefore invisible in the only log a user will
    ever send -- which defeats the point of logging it at all."""

    class FakeUser32:
        def IsIconic(self, h):
            return False

        def GetForegroundWindow(self):
            return 999  # never becomes the target

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


def test_show_labels_joins_the_chrome_key():
    """Without this, toggling the flag on an open preview does nothing:
    redraw() short-circuits on an unchanged key and the bitmap never
    repaints."""
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
    assert on_key != off_key


def test_label_h_reclaims_the_band_when_labels_are_off():
    """geometry.thumbnail_rect must receive the new label height, or the
    mirrored video stays inset inside a band that chrome no longer draws."""
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    w = window.PreviewWindow(
        None,
        client,
        R,
        lambda c: None,
        lambda *a: None,
        list,
        lambda: R,
        show_labels=False,
    )
    assert w._label_h() == 0
    rect = window.geometry.thumbnail_rect(R, window.BORDER, w._label_h())
    assert rect == window.geometry.thumbnail_rect(R, window.BORDER, 0)
    assert rect.h == R.h - window.BORDER * 2


def test_label_h_defaults_on_and_matches_todays_behaviour():
    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    w = window.PreviewWindow(
        None, client, R, lambda c: None, lambda *a: None, list, lambda: R
    )
    assert w._label_h() == window.LABEL_H


class _FakeThumb:
    """Records every (rect, opacity) passed to update(), standing in for
    the real Thumbnail that move() would otherwise touch."""

    def __init__(self):
        self.calls = []

    def update(self, rect, opacity=255):
        self.calls.append((rect, opacity))


def test_a_resize_updates_the_thumbnail_rect_with_the_current_label_height():
    """move()'s thumbnail_rect call must use _label_h(), not a hardcoded
    LABEL_H, or the mirrored video stays inset behind a band chrome no
    longer draws once labels are turned off.

    Reverting that one call site back to `LABEL_H` must turn this test
    red -- checked by hand while writing it."""
    for show_labels, expected_label_h in ((True, window.LABEL_H), (False, 0)):
        w = _RecordingWindow(Rect(100, 100, 320, 210))
        w.show_labels = show_labels
        thumb = _FakeThumb()
        w._thumb = thumb
        new_rect = Rect(100, 100, 400, 260)
        w.move(new_rect)
        assert thumb.calls == [
            (
                window.geometry.thumbnail_rect(
                    new_rect, window.BORDER, expected_label_h
                ),
                255,
            )
        ]


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


def test_redraw_passes_the_current_label_height_to_chrome_render(monkeypatch):
    """redraw()'s chrome.render(label_h=...) call must reflect show_labels
    too -- covering the one call site the thumbnail test above does not
    reach. Hardcoding label_h=LABEL_H here must turn this test red --
    checked by hand while writing it."""
    calls = []

    def fake_render(size, label, **kwargs):
        calls.append(kwargs["label_h"])
        return type("_Img", (), {"size": size})()

    monkeypatch.setattr(window.chrome, "render", fake_render)
    monkeypatch.setattr(window.layered, "push", lambda *a, **k: None)

    client = type("C", (), {"character": "Pilot", "title": "EVE - Pilot", "hwnd": 1})()
    for show_labels, expected_label_h in ((True, window.LABEL_H), (False, 0)):
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
    assert calls == [window.LABEL_H, 0]


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


def _window_for_gestures(locked, on_activate=lambda c: None):
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
    )
    w.hwnd = 1
    w.redraw = lambda force=False: None
    return w, libs


def test_a_left_press_activates_on_the_way_down(monkeypatch):
    """The point of the change: the switch starts on WM_LBUTTONDOWN, so
    it no longer waits out however long the button is held (60-120ms of
    a normal click). EVE-O Preview fires its ThumbnailActivated from
    MouseDown for the same reason."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)

    assert activated == [w.client]


def test_the_left_release_does_not_activate_a_second_time(monkeypatch):
    """The press already switched. A release that switched again would
    run the whole minimize/activate sequence twice per click."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == [w.client]


def test_a_left_drag_no_longer_moves_the_preview(monkeypatch):
    """The breaking half of EVE-O parity. Left is focus only; movement
    moved to the right button, which is where EVE-O and TriffView have
    always had it. Dragging left now just leaves the preview where it
    is, having focused its client."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    w, libs = _window_for_gestures(locked=False)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert w.rect == Rect(100, 100, 320, 210)


def test_a_right_drag_moves_the_preview():
    """Right-drag is now the ONLY way to move one."""
    w, libs = _window_for_gestures(locked=False)
    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)
    assert w.rect == Rect(150, 160, 320, 210)


def test_a_right_drag_release_reports_the_new_rect():
    """The layout is only persisted from the rect reported on release."""
    w, libs = _window_for_gestures(locked=False)
    reported = []
    w._on_rect_changed = lambda *a: reported.append(a)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)
    w._on_message(window.win32.WM_RBUTTONUP, 2, 0)

    assert reported == [("Pilot", Rect(150, 160, 320, 210), False)]


def test_a_locked_preview_refuses_the_right_drag_too(monkeypatch):
    """The lock's meaning had to change with the buttons. It used to stop
    a left drag while right-drag stayed as the deliberate override -- but
    now that right-drag is the only move gesture, honouring the override
    would leave the lock controlling nothing at all. So a lock stops
    movement outright, which is also what EVE-O's LockThumbnailLocation
    does. Unticking Lock is the way to move one again."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    w, libs = _window_for_gestures(locked=True)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)

    assert w.rect == Rect(100, 100, 320, 210)


def test_a_locked_preview_still_focuses_its_client(monkeypatch):
    """A lock stops movement, never focus switching. That survived the
    button split intact."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=True, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)

    assert activated == [w.client]


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

    assert activated == [w.client]
    assert activate_calls == []


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
    must come back at 32:21 once the chrome is removed."""
    rect = _resize_drag(lock_aspect=True)
    assert rect.w == 420
    assert abs((rect.w - 4) / (rect.h - 34) - 320 / 210) < 0.01


def test_unlocking_the_aspect_makes_the_handle_freeform():
    """The escape hatch. Width follows the pointer and the height is left
    exactly where it was -- the picture stretches, which is the documented
    cost and the same one a mismatched typed size already carries."""
    rect = _resize_drag(lock_aspect=False)
    assert rect.w == 420
    assert rect.h == 210
