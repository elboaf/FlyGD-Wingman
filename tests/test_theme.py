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
