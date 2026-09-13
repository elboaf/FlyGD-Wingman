"""Exact, uncapped configured identities — not transient recent-roster history."""

import importlib

import pytest


def model():
    return importlib.import_module("wingman.preview.labelmarkers")


def test_marker_map_keeps_exact_owners_and_drops_bad_entries():
    assert model().validated_markers(
        {
            "Alice": "cyan",
            "alice": "blue",
            " Alice ": "green",
            "hwnd:0x1": "orange",
            "Bad": "#56B4E9",
            "Reset": "",
            "constructor": "purple",
            "__proto__": "yellow",
        }
    ) == {
        "Alice": "cyan",
        "alice": "blue",
        "constructor": "purple",
        "__proto__": "yellow",
    }


@pytest.mark.parametrize(
    "bad", [None, True, False, [], {}, 1, "#56B4E9", "Cyan", "", "unknown"]
)
def test_invalid_marker_drops_only_its_entry(bad):
    assert model().validated_markers({"Alice": bad, "Bob": "green"}) == {"Bob": "green"}


@pytest.mark.parametrize(
    "name",
    [None, True, 1, "", " ", " Alice", "Alice ", "Al\nice", "Al\x00ice", "hwnd:123"],
)
def test_owner_boundary_refuses_aliasing_and_native_fallbacks(name):
    assert not model().valid_owner(name)


@pytest.mark.parametrize("raw", [None, True, [], "cyan"])
def test_bad_map_defaults_empty(raw):
    assert model().validated_markers(raw) == {}


def test_choices_are_named_keys_and_reset_not_rgb_values():
    markers = model()
    assert markers.marker_choices() == [{"key": "", "label": "None"}] + [
        {"key": key, "label": label}
        for key, (label, _) in markers.MARKER_PALETTE.items()
    ]
    assert len(markers.marker_choices()) == 7
    for key in markers.MARKER_PALETTE:
        assert markers.validated_markers({"Pilot": key}) == {"Pilot": key}
    changed = markers.marker_choices()
    changed[0]["label"] = "mutated"
    assert markers.marker_choices()[0]["label"] == "None"
