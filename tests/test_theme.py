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
