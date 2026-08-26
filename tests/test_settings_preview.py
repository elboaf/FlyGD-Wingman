"""Preview section validation. Mirrors test_settings_eve.py's cases."""

import json

import pytest

from wingman import settings


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


def test_show_labels_defaults_on():
    """On preserves the behaviour that shipped: labels have always drawn."""
    assert settings._preview_defaults()["show_labels"] is True


def test_show_labels_accepts_only_a_bool():
    out = settings.validated_preview({"show_labels": False})
    assert out["show_labels"] is False
    out = settings.validated_preview({"show_labels": "no"})
    assert out["show_labels"] is True


def test_minimize_inactive_clients_defaults_off():
    """Off by default: it changes what happens to a real game window,
    which must be asked for."""
    assert settings._preview_defaults()["minimize_inactive_clients"] is False


def test_minimize_inactive_clients_accepts_only_a_bool():
    out = settings.validated_preview({"minimize_inactive_clients": True})
    assert out["minimize_inactive_clients"] is True
    out = settings.validated_preview({"minimize_inactive_clients": "yes"})
    assert out["minimize_inactive_clients"] is False


def test_never_minimize_and_locked_default_empty():
    defaults = settings._preview_defaults()
    assert defaults["never_minimize"] == []
    assert defaults["locked"] == []


def test_never_minimize_and_locked_run_through_roster_deserialize():
    """Same constraints as `seen`: malformed entries drop, hwnd: keys are
    rejected because a client at character-select has no stable name."""
    out = settings.validated_preview(
        {
            "never_minimize": ["Alice", "hwnd:123", 5, "Alice"],
            "locked": ["Bob", "hwnd:456"],
        }
    )
    assert out["never_minimize"] == ["Alice"]
    assert out["locked"] == ["Bob"]


def test_locked_survives_round_trip_with_no_layout_rect(tmp_path):
    """The exact case layout-keyed storage could not handle:
    layout.deserialize drops any entry missing a full rect
    (layout.py:44-52), so a lock stored there for a character who has
    never dragged their preview would vanish on the very next save.
    Storing `locked` as its own top-level list avoids that entirely."""
    path = tmp_path / "settings.json"
    data = settings._fresh_defaults()
    data["preview"]["locked"] = ["NeverDragged"]
    assert data["preview"]["layouts"] == {}
    settings.save(data, path)
    assert settings.load(path)["preview"]["locked"] == ["NeverDragged"]


def test_a_pre_branch_layout_lock_is_migrated_into_top_level_locked():
    """A file saved before `preview.locked` existed recorded the lock on
    the layout entry itself (layout.Entry.locked). Nothing reads that
    field any more, so without this migration the character opens
    unlocked and the first drag silently rewrites the flag to False."""
    out = settings.validated_preview(
        {"layouts": {"Alice": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": True}}}
    )
    assert out["locked"] == ["Alice"]
    # The layout entry itself is untouched -- Entry.locked stays, it is
    # just no longer the source of truth.
    assert out["layouts"]["Alice"]["locked"] is True


def test_an_explicit_locked_list_is_not_clobbered_by_a_legacy_flag():
    """Union, not overwrite: a real preview.locked already reflects the
    user's current choice and must win over a stale layout flag, and the
    same name appearing in both places must not be duplicated."""
    out = settings.validated_preview(
        {
            "locked": ["Bob"],
            "layouts": {
                "Alice": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": True},
                "Bob": {"x": 5, "y": 6, "w": 7, "h": 8, "locked": False},
            },
        }
    )
    assert out["locked"] == ["Bob", "Alice"]


def test_the_legacy_lock_migration_does_not_run_twice():
    """A file already carrying the current defaults_version marker is not
    pre-branch -- its layout `locked` flags (if any survive from a
    downgrade/re-upgrade) must not be re-migrated on every load."""
    out = settings.validated_preview(
        {
            "defaults_version": 2,
            "layouts": {"Alice": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": True}},
        }
    )
    assert out["locked"] == []


def test_snap_defaults_to_on():
    """On by default because it is what shipped; turning it off would
    silently change how every existing install's previews drag."""
    assert settings._preview_defaults()["snap"] is True


def test_snap_survives_a_round_trip():
    assert settings.validated_preview({"snap": False})["snap"] is False


def test_snap_falls_back_when_it_is_not_a_bool():
    assert settings.validated_preview({"snap": "yes"})["snap"] is True


def test_the_preview_defaults_are_a_fixed_point_of_their_own_validator():
    """Normalising runs on every save, so a default its own validator
    rewrites would drift the file on the first write. Named as unguarded
    in docs/preview-roadmap.md; this slice makes it cheap to add."""
    defaults = settings._preview_defaults()
    assert settings.validated_preview(defaults) == defaults
