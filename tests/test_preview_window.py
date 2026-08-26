"""Only the gesture arithmetic is tested here -- window creation needs a
desktop and lives in the smoke checklist.

Click-versus-drag is where this goes subtly wrong: a click that moves one
pixel must still focus the client, and a locked preview must never move
but must still activate on release."""

from obs_youtube_uploader.preview import window
from obs_youtube_uploader.preview.geometry import Rect

R = Rect(100, 100, 320, 210)


def test_a_still_press_is_a_click():
    action, rect = window.drag_result((10, 10), (10, 10), R, locked=False, drag_min=4)
    assert action == "activate" and rect == R


def test_movement_within_the_drag_threshold_is_still_a_click():
    action, _ = window.drag_result((10, 10), (12, 11), R, locked=False, drag_min=4)
    assert action == "activate"


def test_movement_past_the_threshold_is_a_drag():
    action, rect = window.drag_result((10, 10), (60, 40), R, locked=False, drag_min=4)
    assert action == "move"
    assert rect == Rect(150, 130, 320, 210)


def test_a_locked_preview_never_moves_but_still_activates():
    """Locking exists so a carefully placed layout survives a stray drag.
    It must not also break click-to-focus."""
    action, rect = window.drag_result((10, 10), (200, 200), R, locked=True, drag_min=4)
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


def test_a_locked_preview_ignores_a_left_drag():
    """That is what the lock is for: a carefully placed layout should
    survive a stray drag."""
    w, libs = _window_for_gestures(locked=True)
    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (400, 300)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    assert w.rect == Rect(100, 100, 320, 210)


def test_a_locked_preview_still_moves_on_a_right_drag():
    """The documented override: a lock stops accidental movement, not
    deliberate movement. Both buttons shared one 'drag' mode, so the lock
    suppressed the override too and it silently did nothing."""
    w, libs = _window_for_gestures(locked=True)
    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_RBUTTONDOWN, 2, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 2, 0)
    assert w.rect == Rect(150, 160, 320, 210)


def test_an_unlocked_left_drag_still_moves():
    w, libs = _window_for_gestures(locked=False)
    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (250, 260)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    assert w.rect == Rect(150, 160, 320, 210)


def test_a_click_hands_the_switch_to_the_host_exactly_once(monkeypatch):
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


def test_a_click_on_a_locked_preview_still_reaches_the_host(monkeypatch):
    """A lock stops movement, not focus switching -- drag_result() says so
    and the delegation must not quietly change that."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=True, on_activate=activated.append)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (400, 300)  # past DRAG_MIN: locked, so still a click
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == [w.client]


def test_a_real_drag_release_reports_the_rect_instead_of_activating(monkeypatch):
    """The other side of the classification: a moved preview must not also
    steal the foreground on release."""
    monkeypatch.setattr(window, "activate", lambda libs, hwnd: True)
    activated = []
    w, libs = _window_for_gestures(locked=False, on_activate=activated.append)
    reported = []
    w._on_rect_changed = lambda *a: reported.append(a)

    libs.cursor = (200, 200)
    w._on_message(window.win32.WM_LBUTTONDOWN, 1, 0)
    libs.cursor = (400, 300)
    w._on_message(window.win32.WM_MOUSEMOVE, 1, 0)
    w._on_message(window.win32.WM_LBUTTONUP, 1, 0)

    assert activated == []
    assert len(reported) == 1


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
