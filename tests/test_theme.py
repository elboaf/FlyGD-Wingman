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
