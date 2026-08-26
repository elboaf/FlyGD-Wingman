"""The size ceiling, the frame count, and the index mapping.

The GDI path itself is Windows only and is covered by the smoke
checklist, not here. What is pure -- how many frames a preview gets and
which one a given phase index selects -- is covered, because the mapping
is where the two-frame fallback can silently go wrong: state.frame_index
always returns an index into the six-entry FRAME_ALPHAS, whatever the
cache actually holds.
"""

import pytest

from wingman.alerts import state
from wingman.preview import alertframes


def test_a_small_preview_gets_the_full_pulse():
    assert alertframes.frame_count((320, 210)) == 6


def test_a_large_preview_falls_back_to_a_blink():
    """Six frames at 1920x1080 is ~50MB held indefinitely under
    persistence, and a fleet-wide aggression arms every preview at once."""
    assert alertframes.frame_count((1920, 1080)) == 2


def test_the_ceiling_is_on_area_not_either_edge():
    """A wide, short preview and a tall, narrow one cost the same."""
    assert alertframes.frame_count((1280, 200)) == alertframes.frame_count((200, 1280))


def test_the_blink_keeps_the_dimmest_and_the_brightest():
    assert alertframes.alphas_for((1920, 1080)) == (
        state.FRAME_ALPHAS[0],
        state.FRAME_ALPHAS[-1],
    )


def test_a_small_preview_uses_every_alpha():
    assert alertframes.alphas_for((320, 210)) == state.FRAME_ALPHAS


@pytest.mark.parametrize("index", range(len(state.FRAME_ALPHAS)))
def test_every_phase_index_is_in_range_for_a_blink(index):
    """state.frame_index knows nothing about the cache's size, so every
    index it can return has to land inside a two-frame cache too. This is
    the bug the plan's own sketch would have shipped: it passed
    frame_index() straight to a cache that may hold two frames."""
    assert 0 <= alertframes.frame_for(index, 2) < 2


@pytest.mark.parametrize("index", range(len(state.FRAME_ALPHAS)))
def test_a_full_cache_maps_each_index_to_itself(index):
    assert alertframes.frame_for(index, len(state.FRAME_ALPHAS)) == index


def test_the_blink_splits_the_pulse_in_half():
    """The dim half of the wave blinks dark, the bright half blinks lit --
    rather than, say, five indices mapping to one frame."""
    halves = [alertframes.frame_for(i, 2) for i in range(len(state.FRAME_ALPHAS))]
    assert halves == [0, 0, 0, 1, 1, 1]
