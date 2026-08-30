"""should_minimize / should_restore: pure logic. Five reasons not to
minimize, one to; and the one case that has to undo a minimize."""

import pytest

from wingman.preview.switching import should_minimize, should_restore

BASE = dict(
    enabled=True,
    previous_key="Alice",
    next_key="Bravo",
    never=[],
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": False},
        {"previous_key": None},
        {"previous_key": ""},
        {"next_key": "Alice"},  # previous_key == next_key
        {"never": ["Alice"]},
    ],
    ids=[
        "feature-off",
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


@pytest.mark.parametrize(
    "activated, minimized, expected",
    [
        (False, True, True),
        (True, True, False),
        (False, False, False),
        (True, False, False),
    ],
    ids=["refused-after-minimize", "took", "refused-nothing-minimized", "clean"],
)
def test_should_restore(activated, minimized, expected):
    """The safety property, in the shape minimize-first forces on it.
    TriffView activates first and returns early on failure so a refused
    switch minimizes nothing. Minimizing first is what removes the settle
    and the race with the outgoing foreground, but it means the outgoing
    client is already gone when a refusal is learned -- so the refusal
    must bring it back, or the user is left on an empty desktop with
    nothing focused, which is strictly worse than the switch not working.
    """
    assert should_restore(activated=activated, minimized=minimized) is expected
