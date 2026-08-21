import logging

import pytest

from obs_youtube_uploader import theme


@pytest.fixture(autouse=True)
def _clear_consumers():
    """theme._consumers is module-level state that register() mutates;
    without this, consumers registered by one test leak into the next."""
    saved = list(theme._consumers)
    theme._consumers.clear()
    yield
    theme._consumers.clear()
    theme._consumers.extend(saved)


def test_detect_mode_dark_when_reader_returns_zero():
    assert theme.detect_mode(reader=lambda: 0) == "dark"


def test_detect_mode_light_when_reader_returns_one():
    assert theme.detect_mode(reader=lambda: 1) == "light"


def test_detect_mode_light_when_reader_returns_none():
    # Safe default: an unreadable registry value must not be treated as dark.
    assert theme.detect_mode(reader=lambda: None) == "light"


TOKEN_NAMES = [
    "SUCCESS",
    "ERROR",
    "WARNING",
    "MUTED",
    "LINK",
    "FG",
    "ROW_ODD",
    "ROW_EVEN",
    "ROW_PRESELECT",
]


def test_tokens_has_exactly_light_and_dark_modes():
    assert set(theme.TOKENS.keys()) == {"light", "dark"}


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("name", TOKEN_NAMES)
def test_every_token_name_present_in_both_modes(mode, name):
    assert name in theme.TOKENS[mode]
    assert theme.TOKENS[mode][name].startswith("#")


def test_token_uses_explicit_mode():
    assert theme.token("SUCCESS", "dark") == theme.TOKENS["dark"]["SUCCESS"]


def test_token_defaults_to_current_mode(monkeypatch):
    monkeypatch.setattr(theme, "current_mode", lambda: "dark")
    assert theme.token("SUCCESS") == theme.TOKENS["dark"]["SUCCESS"]


def test_token_raises_keyerror_on_unknown_name():
    with pytest.raises(KeyError):
        theme.token("NOT_A_REAL_TOKEN", "light")


class _FakeRoot:
    """Stand-in for tk.Tk() - apply() must not require a real display,
    since this test suite runs on ubuntu-latest with no Tk available."""


def test_apply_calls_every_registered_consumer_with_the_mode(monkeypatch):
    monkeypatch.setattr(theme, "sv_ttk", None)
    calls = []
    theme.register(lambda mode: calls.append(("a", mode)))
    theme.register(lambda mode: calls.append(("b", mode)))

    theme.apply(_FakeRoot(), "dark")

    assert calls == [("a", "dark"), ("b", "dark")]
    assert theme.current_mode() == "dark"


def test_apply_continues_past_a_raising_consumer(monkeypatch, caplog):
    monkeypatch.setattr(theme, "sv_ttk", None)
    calls = []

    def bad(mode):
        raise RuntimeError("boom")

    theme.register(bad)
    theme.register(lambda mode: calls.append(mode))

    with caplog.at_level(logging.WARNING):
        theme.apply(_FakeRoot(), "light")

    assert calls == ["light"]  # the second consumer still ran
    assert any("boom" in r.message or r.exc_info for r in caplog.records)


def test_apply_never_raises_when_sv_ttk_is_unavailable(monkeypatch):
    monkeypatch.setattr(theme, "sv_ttk", None)
    theme.apply(_FakeRoot(), "dark")  # must not raise


def test_apply_swallows_sv_ttk_set_theme_failure(monkeypatch, caplog):
    class _BadSvTtk:
        @staticmethod
        def set_theme(mode, root=None):
            raise RuntimeError("no display")

    monkeypatch.setattr(theme, "sv_ttk", _BadSvTtk())
    calls = []
    theme.register(lambda mode: calls.append(mode))

    with caplog.at_level(logging.WARNING):
        theme.apply(_FakeRoot(), "dark")  # must not raise

    assert calls == ["dark"]  # consumers still run even though sv_ttk failed


def test_unregister_removes_the_consumer(monkeypatch):
    monkeypatch.setattr(theme, "sv_ttk", None)
    calls = []

    def consumer(mode):
        calls.append(mode)

    theme.register(consumer)
    theme.unregister(consumer)
    theme.apply(_FakeRoot(), "dark")

    assert calls == []


def test_unregister_is_idempotent():
    # SettingsWindow may be destroyed more than once in edge cases; a
    # double-unregister must not raise.
    theme.unregister(lambda mode: None)  # never registered - must be a no-op


class _FakeWindow:
    """Stand-in for a Toplevel. wm_frame() returns the hex window id string
    Tk really hands back, so the test covers the parse too."""

    def __init__(self, frame="0x1a2b3c"):
        self._frame = frame
        self.frame_calls = 0

    def wm_frame(self):
        self.frame_calls += 1
        if self._frame is None:
            raise RuntimeError("window is not realised")
        return self._frame


def _recording_setter(results):
    """results: HRESULT to return per call, consumed in order."""
    calls = []

    def setter(hwnd, attr, value):
        calls.append((hwnd, attr, value))
        return results[len(calls) - 1] if len(calls) <= len(results) else 0

    return calls, setter


def test_apply_titlebar_sets_attribute_20_when_it_succeeds():
    calls, setter = _recording_setter([0])
    win = _FakeWindow("0x1a2b3c")

    theme.apply_titlebar(win, "dark", setter=setter)

    assert calls == [(0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE, 1)]


def test_apply_titlebar_falls_back_to_attribute_19_when_20_fails():
    """Attribute 20 is only recognised from Windows 10 20H1 on; on earlier
    builds DwmSetWindowAttribute returns a failing HRESULT rather than
    raising, so a caller that ignored the return value would leave the title
    bar light on exactly the hosts that need the fallback."""
    calls, setter = _recording_setter([-2147024809, 0])  # E_INVALIDARG, then OK
    win = _FakeWindow("0x1a2b3c")

    theme.apply_titlebar(win, "dark", setter=setter)

    assert calls == [
        (0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE, 1),
        (0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1, 1),
    ]


def test_apply_titlebar_clears_the_flag_in_light_mode():
    calls, setter = _recording_setter([0])

    theme.apply_titlebar(_FakeWindow(), "light", setter=setter)

    assert calls == [(0x1a2b3c, theme.DWMWA_USE_IMMERSIVE_DARK_MODE, 0)]


def test_apply_titlebar_is_a_noop_off_windows(monkeypatch):
    """No setter injected means the real DWM path, which does not exist off
    Windows. It must return before even touching the window - wm_frame() on a
    non-Windows Tk returns an X11 id that is meaningless to DWM."""
    monkeypatch.setattr(theme.sys, "platform", "linux")
    win = _FakeWindow()

    theme.apply_titlebar(win, "dark")

    assert win.frame_calls == 0


def test_apply_titlebar_swallows_an_unrealised_window(caplog):
    """wm_frame() has no usable HWND until the toplevel is on screen. Ordering
    is the caller's job, but this must degrade rather than take a window
    constructor down - the same policy as apply()."""
    calls, setter = _recording_setter([0])

    with caplog.at_level(logging.WARNING):
        theme.apply_titlebar(_FakeWindow(frame=None), "dark", setter=setter)

    assert calls == []


def test_apply_titlebar_swallows_a_raising_setter(caplog):
    def boom(hwnd, attr, value):
        raise OSError("dwmapi.dll missing")

    with caplog.at_level(logging.WARNING):
        theme.apply_titlebar(_FakeWindow(), "dark", setter=boom)  # must not raise
