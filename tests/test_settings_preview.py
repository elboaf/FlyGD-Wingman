"""Preview section validation. Mirrors test_settings_eve.py's cases."""
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
    out = settings.validated_preview({"layouts": {
        "Good": {"x": 1, "y": 2, "w": 3, "h": 4},
        "Bad": {"x": "no", "y": 2, "w": 3, "h": 4}}})
    assert set(out["layouts"]) == {"Good"}


def test_each_caller_gets_its_own_preview_section():
    """dict(DEFAULTS) is shallow. Without _fresh_defaults rebuilding it,
    two callers share one dict and one caller's layout edit rewrites the
    other's -- including the module-level DEFAULTS itself."""
    a, b = settings._fresh_defaults(), settings._fresh_defaults()
    a["preview"]["layouts"]["X"] = {"x": 1, "y": 1, "w": 2, "h": 2}
    assert b["preview"]["layouts"] == {}
    assert settings.DEFAULTS["preview"]["layouts"] == {}


def test_client_layout_keys_default_off_and_empty():
    out = settings._preview_defaults()
    assert out["restore_clients_on_launch"] is False
    assert out["client_layouts"] == {}


def test_restore_on_launch_accepts_only_a_bool():
    assert settings.validated_preview(
        {"restore_clients_on_launch": True})["restore_clients_on_launch"]
    assert settings.validated_preview(
        {"restore_clients_on_launch": "yes"}
    )["restore_clients_on_launch"] is False


def test_a_corrupt_client_layout_entry_drops_alone():
    """Same posture as the preview layouts above: one bad character costs
    that character's position, not the section."""
    out = settings.validated_preview({"client_layouts": {
        "Good": {"x": 1, "y": 2, "w": 3, "h": 4},
        "Bad": {"x": "nope", "y": 2, "w": 3, "h": 4},
    }})
    assert list(out["client_layouts"]) == ["Good"]


def test_a_corrupt_client_layouts_section_falls_back_to_empty():
    assert settings.validated_preview({"client_layouts": "nope"}
                                      )["client_layouts"] == {}


def test_client_layouts_survive_a_load_round_trip(tmp_path):
    """The keys must be in DEFAULTS, or save() drops them on every write
    (settings.py:186-189)."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["client_layouts"] = {
        "Pilot": {"x": 1, "y": 2, "w": 3, "h": 4, "maximized": True}}
    data["preview"]["restore_clients_on_launch"] = True
    settings.save(data, path)
    back = settings.load(path)["preview"]
    assert back["restore_clients_on_launch"] is True
    assert back["client_layouts"]["Pilot"]["maximized"] is True
