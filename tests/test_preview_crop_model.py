import importlib.util
from pathlib import Path

import pytest

from wingman.preview.geometry import Rect

# Load the manual model module using the update-harness pattern
model_path = Path(__file__).parent / "manual" / "preview_crop_model.py"
spec = importlib.util.spec_from_file_location("preview_crop_model", model_path)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


# Step 1: Mapping tests
def test_map_selection_scales_edges_outward():
    result = model.map_selection(
        Rect(25, 10, 51, 31),
        destination=Rect(10, 0, 200, 100),
        source_size=(1000, 500),
    )
    assert result == Rect(75, 50, 255, 155)


def test_map_selection_clamps_to_destination_and_source():
    result = model.map_selection(
        Rect(-50, -20, 400, 300),
        destination=Rect(10, 10, 200, 100),
        source_size=(1000, 500),
    )
    assert result == Rect(0, 0, 1000, 500)


def test_map_selection_rejects_smaller_than_minimum_after_clamp():
    assert (
        model.map_selection(Rect(10, 10, 1, 1), Rect(0, 0, 200, 100), (1000, 500))
        is None
    )


# Step 4: Stage, fit, central-source, and placement tests
@pytest.mark.parametrize("stage", [1, 2, 4, 8])
def test_validated_stage_accepts_probe_stages(stage):
    assert model.validated_stage(stage) == stage


@pytest.mark.parametrize("stage", [0, 3, 5, 16])
def test_validated_stage_rejects_other_counts(stage):
    with pytest.raises(ValueError):
        model.validated_stage(stage)


def test_central_source_is_middle_half():
    assert model.central_source((1000, 600)) == Rect(250, 150, 500, 300)


def test_fit_within_preserves_aspect_and_bounds():
    assert model.fit_within((2560, 1440), (1200, 800)) == (1200, 675)


@pytest.mark.parametrize(
    "source,maximum",
    [
        ((0, 0), (1200, 800)),
        ((0, 720), (1200, 800)),
        ((1280, 0), (1200, 800)),
        ((-4, -4), (1200, 800)),
        ((1280, 720), (0, 800)),
        ((1280, 720), (1200, 0)),
        ((1280, 720), (-1, -1)),
    ],
)
def test_fit_within_reports_nothing_for_a_degenerate_source_or_maximum(source, maximum):
    """A 1-pixel client's central half is 0x0, so this is reachable from a
    live client rather than only from a hand-built tuple. (0, 0) is a size
    no window can be created at, which is what the caller must act on --
    a ZeroDivisionError on the preview pump thread would end the probe."""
    assert model.fit_within(source, maximum) == (0, 0)


def test_stack_starts_at_monitor_bottom_right_and_moves_up():
    monitor = Rect(-1920, 0, 1920, 1080)
    assert model.stack_from_bottom_right(0, monitor, (320, 180)) == Rect(
        -328, 892, 320, 180
    )
    assert model.stack_from_bottom_right(1, monitor, (320, 180)) == Rect(
        -328, 704, 320, 180
    )


def test_stack_wraps_upward_rows_into_columns_before_leaving_the_monitor():
    monitor = Rect(-1920, -1080, 1920, 1080)
    assert [
        model.stack_from_bottom_right(i, monitor, (480, 270)) for i in range(8)
    ] == [
        Rect(-488, -278, 480, 270),
        Rect(-488, -556, 480, 270),
        Rect(-488, -834, 480, 270),
        Rect(-976, -278, 480, 270),
        Rect(-976, -556, 480, 270),
        Rect(-976, -834, 480, 270),
        Rect(-1464, -278, 480, 270),
        Rect(-1464, -556, 480, 270),
    ]


@pytest.mark.parametrize("monitor", [Rect(0, 0, 640, 360), Rect(-320, -240, 320, 240)])
@pytest.mark.parametrize("size", [(480, 270), (180, 320)])
def test_small_monitors_fit_all_eight_crops_without_overlap_or_rescue(monitor, size):
    rectangles = [model.stack_from_bottom_right(i, monitor, size) for i in range(8)]
    assert len(set(rectangles)) == 8
    for index, rect in enumerate(rectangles):
        assert 0 < rect.w <= size[0] and 0 < rect.h <= size[1]
        assert monitor.x + 8 <= rect.x and rect.right <= monitor.right - 8
        assert monitor.y + 8 <= rect.y and rect.bottom <= monitor.bottom - 8
        assert abs(rect.w * size[1] - rect.h * size[0]) <= max(size)
        for other in rectangles[:index]:
            assert (
                rect.right + 8 <= other.x
                or other.right + 8 <= rect.x
                or rect.bottom + 8 <= other.y
                or other.bottom + 8 <= rect.y
            )


def test_stack_gap_controls_both_edge_inset_and_spacing():
    """A non-default gap must move the bottom-right inset AND the
    inter-window spacing; a gap that only affected one of the two would
    let stacked crops touch the monitor edge or overlap each other."""
    monitor = Rect(-1920, 0, 1920, 1080)
    assert model.stack_from_bottom_right(0, monitor, (320, 180), gap=20) == Rect(
        -340, 880, 320, 180
    )
    assert model.stack_from_bottom_right(1, monitor, (320, 180), gap=20) == Rect(
        -340, 680, 320, 180
    )
