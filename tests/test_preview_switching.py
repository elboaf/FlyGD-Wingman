"""The pure decision for post-success inactive-client minimization."""

import pytest

from wingman.preview import switching
from wingman.preview.switching import should_minimize

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


def test_rollback_policy_is_removed_with_activate_first():
    assert not hasattr(switching, "should_restore")
