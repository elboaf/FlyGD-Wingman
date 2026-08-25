"""Preview section validation. Mirrors test_settings_eve.py's cases."""

import json

import pytest

from obs_youtube_uploader import settings


@pytest.mark.parametrize("raw", [None, [], "nope", 3])
def test_whole_section_of_wrong_type_falls_back(raw):
    assert settings.validated_preview(raw) == settings._preview_defaults()


def test_unknown_keys_are_dropped():
    out = settings.validated_preview({"enabled": True, "nonsense": 1})
    assert "nonsense" not in out and out["enabled"] is True


@pytest.mark.parametrize("given,expected", [(0, 20), (999, 255), (128, 128)])
def test_opacity_is_clamped_not_rejected(given, expected):
    """A fully transparent preview is indistinguishable from a broken one,
    so clamp into a visible range rather than falling back to default."""
    assert settings.validated_preview({"opacity": given})["opacity"] == expected


def test_sizes_are_floored():
    out = settings.validated_preview({"width": 1, "height": 1})
    assert out["width"] >= 120 and out["height"] >= 90


def test_booleans_are_not_accepted_as_sizes():
    """bool is an int in Python; True would silently become a width."""
    out = settings.validated_preview({"width": True})
    assert out["width"] == settings._preview_defaults()["width"]


def test_a_corrupt_layout_entry_drops_alone():
    out = settings.validated_preview(
        {
            "layouts": {
                "Good": {"x": 1, "y": 2, "w": 3, "h": 4},
                "Bad": {"x": "no", "y": 2, "w": 3, "h": 4},
            }
        }
    )
    assert set(out["layouts"]) == {"Good"}


def test_each_caller_gets_its_own_preview_section():
    """dict(DEFAULTS) is shallow. Without _fresh_defaults rebuilding it,
    two callers share one dict and one caller's layout edit rewrites the
    other's -- including the module-level DEFAULTS itself."""
    a, b = settings._fresh_defaults(), settings._fresh_defaults()
    a["preview"]["layouts"]["X"] = {"x": 1, "y": 1, "w": 2, "h": 2}
    assert b["preview"]["layouts"] == {}
    assert settings.DEFAULTS["preview"]["layouts"] == {}


def test_restore_preview_positions_defaults_on():
    """On preserves the behaviour that shipped: a preview has always
    reopened where the user last dragged it."""
    assert settings._preview_defaults()["restore_preview_positions"] is True


def test_restore_preview_positions_accepts_only_a_bool():
    assert (
        settings.validated_preview({"restore_preview_positions": False})[
            "restore_preview_positions"
        ]
        is False
    )
    assert (
        settings.validated_preview({"restore_preview_positions": "no"})[
            "restore_preview_positions"
        ]
        is True
    )


def test_the_client_window_keys_are_gone():
    """The feature that moved EVE's own windows was removed: it rewrote
    the client's resolution, and EVE rewrites its settings in response.

    A key left in _preview_defaults() is a key validated_preview puts
    back into the section on every load and every write, so the section
    would keep carrying a setting nothing reads."""
    out = settings._preview_defaults()
    assert "restore_clients_on_launch" not in out
    assert "client_layouts" not in out


def test_a_settings_file_still_holding_the_client_window_keys_loads(tmp_path):
    """Every installed copy has them, so this is the whole migration.

    The mechanism is _normalize, NOT save()'s projection: _save_locked
    projects TOP-LEVEL keys only and copies data["preview"] wholesale, so
    a bare save() would preserve both keys. What drops them is
    validated_preview rebuilding the section from _preview_defaults(),
    which _normalize runs -- and load() and update() both call it. Every
    production writer goes through update(), so no migration step is
    needed; that is a fact about the writers, not about save().
    """
    path = tmp_path / "settings.json"
    raw = settings._fresh_defaults()
    raw["preview"]["restore_clients_on_launch"] = True
    raw["preview"]["client_layouts"] = {
        "Pilot": {"x": 1, "y": 2, "w": 3, "h": 4, "maximized": True}
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    section = settings.load(path)["preview"]
    assert "restore_clients_on_launch" not in section
    assert "client_layouts" not in section
    assert section["restore_preview_positions"] is True

    live = json.loads(path.read_text(encoding="utf-8"))
    with settings.update(live, path):
        pass
    on_disk = json.loads(path.read_text(encoding="utf-8"))["preview"]
    assert "restore_clients_on_launch" not in on_disk
    assert "client_layouts" not in on_disk


def test_restore_preview_positions_survives_a_load_round_trip(tmp_path):
    """The key must be in _preview_defaults(), or validated_preview drops
    it from the section on every load and every update()."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["restore_preview_positions"] = False
    settings.save(data, path)
    assert settings.load(path)["preview"]["restore_preview_positions"] is False
