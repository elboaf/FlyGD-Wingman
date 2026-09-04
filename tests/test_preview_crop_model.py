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


def test_stack_starts_at_monitor_bottom_right_and_moves_up():
    monitor = Rect(-1920, 0, 1920, 1080)
    assert model.stack_from_bottom_right(0, monitor, (320, 180)) == Rect(
        -328, 892, 320, 180
    )
    assert model.stack_from_bottom_right(1, monitor, (320, 180)) == Rect(
        -328, 704, 320, 180
    )
