"""should_hide: pure logic behind hide-on-lost-focus."""

import pytest

from wingman.preview.visibility import should_hide

# An EVE client holds the foreground: the ordinary case, nothing hides.
BASE = dict(
    enabled=True,
    foreground=0x1234,
    client_hwnds=[0x1234, 0x5678],
    foreground_is_ours=False,
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": False, "foreground": 0x9999},
        {},
        {"foreground": 0x5678},
        {"foreground": 0x9999, "foreground_is_ours": True},
    ],
    ids=[
        "feature-off",
        "foreground-is-a-client",
        "foreground-is-another-client",
        "foreground-is-one-of-ours",
    ],
)
def test_stays_visible(overrides):
    assert should_hide(**{**BASE, **overrides}) is False


def test_hides_when_foreground_is_a_stranger():
    assert should_hide(**{**BASE, "foreground": 0x9999}) is True


def test_hides_when_every_client_is_minimized():
    """A minimized window cannot hold the foreground, so the literal
    "all clients minimized" case falls out of the same predicate: whatever
    the user alt-tabbed to is not in client_hwnds."""
    assert should_hide(**{**BASE, "foreground": 0xDEAD}) is True


def test_hides_when_no_clients_are_running():
    assert should_hide(**{**BASE, "foreground": 0x9999, "client_hwnds": []}) is True


def test_no_foreground_at_all_hides():
    """GetForegroundWindow returns 0 when the foreground window is being
    destroyed or a secure desktop (UAC, lock screen) has it. Nothing of
    ours is up, so nothing should be drawn over it."""
    assert should_hide(**{**BASE, "foreground": 0}) is True


def test_ownership_wins_over_a_zero_foreground():
    """Belt and braces: if the host ever reports 0 as ours, ownership is
    the more specific claim and previews stay up rather than flickering."""
    assert (
        should_hide(
            enabled=True,
            foreground=0,
            client_hwnds=[0x1234],
            foreground_is_ours=True,
        )
        is False
    )


def test_off_never_hides_even_with_nothing_running():
    assert (
        should_hide(
            enabled=False,
            foreground=0,
            client_hwnds=[],
            foreground_is_ours=False,
        )
        is False
    )
