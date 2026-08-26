"""should_minimize: pure logic, five reasons to say no and one to say yes."""

import pytest

from wingman.preview.switching import should_minimize

BASE = dict(
    enabled=True,
    activated=True,
    previous_key="Alice",
    next_key="Bravo",
    never=[],
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": False},
        {"activated": False},
        {"previous_key": None},
        {"previous_key": ""},
        {"next_key": "Alice"},  # previous_key == next_key
        {"never": ["Alice"]},
    ],
    ids=[
        "feature-off",
        "activation-failed",
        "no-previous-client",
        "empty-previous-client",
        "previous-equals-next",
        "previous-is-never-minimize",
    ],
)
def test_false_paths(overrides):
    assert should_minimize(**{**BASE, **overrides}) is False


def test_true_when_nothing_blocks_it():
    assert should_minimize(**BASE) is True


def test_activated_false_wins_even_if_everything_else_says_minimize():
    """The safety property: a failed switch must never minimize the client
    the user was just on, no matter how the other inputs line up. Ported
    from TriffView, whose switch sequence returns early on failed
    activation -- otherwise the user is left looking at an empty desktop
    with nothing focused."""
    assert (
        should_minimize(
            enabled=True,
            activated=False,
            previous_key="Alice",
            next_key="Bravo",
            never=[],
        )
        is False
    )
