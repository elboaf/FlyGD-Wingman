"""Real settings transactions must retain snapshots and explicit exclusions."""

import copy
import json

import pytest

from wingman import settings


def test_saved_layout_defaults_are_empty_and_independent(tmp_path):
    path = tmp_path / "missing.json"
    first, second = settings.load(path), settings.load(path)
    assert first["preview"]["saved_layouts"] == {"version": 1, "items": []}
    first["preview"]["saved_layouts"]["items"].append({"id": "changed"})
    assert second["preview"]["saved_layouts"] == {"version": 1, "items": []}
    assert settings.DEFAULTS["preview"]["saved_layouts"] == {"version": 1, "items": []}


def test_explicit_exclusions_survive_reload_without_expanding_history(tmp_path):
    path = tmp_path / "settings.json"
    doc = settings.load(path)
    names = [f"Pilot{i}" for i in range(65)]
    with settings.update(doc, path) as live:
        live["preview"].update(excluded=names, seen=names)
    with settings.update(doc, path) as live:
        live["channel_title"] = "Unrelated"
    saved = settings.load(path)["preview"]
    assert saved["excluded"] == names
    assert len(saved["seen"]) == 64


def test_legacy_working_state_does_not_acquire_a_fabricated_snapshot(tmp_path):
    path = tmp_path / "settings.json"
    current = {"Alice": {"x": -100, "y": 30, "w": 320, "h": 210, "locked": True}}
    path.write_text(
        json.dumps({"preview": {"layouts": current, "excluded": ["Alice"]}})
    )
    preview = settings.load(path)["preview"]
    assert preview["saved_layouts"] == {"version": 1, "items": []}
    assert preview["layouts"] == current
    assert preview["excluded"] == ["Alice"]


def test_snapshot_normalization_survives_save_reload_and_unrelated_update(tmp_path):
    path = tmp_path / "settings.json"
    valid = {
        "id": "saved",
        "name": "Rolling",
        "characters": {
            "Alice": {"visible": True, "rect": {"x": -10, "y": -20, "w": 30, "h": 40}},
            "Offline": {"visible": False, "rect": None},
        },
    }
    malformed = {
        **valid,
        "id": "bad",
        "name": "Bad",
        "characters": {
            **valid["characters"],
            "Broken": {"visible": "false", "rect": None},
        },
    }
    current = {"Alice": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": True}}
    path.write_text(
        json.dumps(
            {
                "preview": {
                    "layouts": current,
                    "saved_layouts": {
                        "version": 1,
                        "items": [malformed, valid],
                    },
                }
            }
        )
    )
    doc = settings.load(path)
    expected = {"version": 1, "items": [valid]}
    assert doc["preview"]["saved_layouts"] == expected
    settings.save(doc, path)
    with settings.update(doc, path) as live:
        live["channel_title"] = "Unrelated"
        live["preview"]["opacity"] = 100
        live["preview"]["layouts"]["Alice"]["x"] = 99
    assert settings.load(path) == doc
    assert doc["preview"]["saved_layouts"] == expected
    assert doc["preview"]["layouts"]["Alice"]["x"] == 99
    assert doc["preview"]["layouts"]["Alice"]["locked"] is True
    canonical = path.read_bytes()
    with settings.update(doc, path):
        pass
    assert path.read_bytes() == canonical


@pytest.mark.parametrize("new_first", [False, True])
def test_apply_exclusion_merge_over_capacity_is_lossless_in_either_order(
    tmp_path, new_first
):
    from wingman.preview.savedlayouts import SavedCharacter, SavedLayout, apply_snapshot

    path = tmp_path / "settings.json"
    doc = settings.load(path)
    names = [f"Absent{i}" for i in range(64)]
    initial = ["New", *names] if new_first else names
    with settings.update(doc, path) as live:
        live["preview"]["excluded"] = initial
    snapshot = SavedLayout("s", "Hidden", (SavedCharacter("New", False, None),))
    with settings.update(doc, path) as live:
        apply_snapshot(live["preview"], snapshot)
    expected = ["New", *names] if new_first else [*names, "New"]
    assert settings.load(path)["preview"]["excluded"] == expected
    with settings.update(doc, path) as live:
        live["channel_title"] = "Unrelated"
    assert settings.load(path)["preview"]["excluded"] == expected
    visible = SavedLayout("s", "Visible", (SavedCharacter("New", True, None),))
    with settings.update(doc, path) as live:
        apply_snapshot(live["preview"], visible)
    assert settings.load(path)["preview"]["excluded"] == names


def test_failed_persistence_restores_all_exclusions_and_snapshot_state(
    tmp_path, monkeypatch
):
    from wingman.preview.savedlayouts import (
        SavedCharacter,
        SavedLayout,
        apply_snapshot,
        serialize,
    )

    path = tmp_path / "settings.json"
    doc = settings.load(path)
    names = [f"Pilot{i}" for i in range(70)]
    snapshot = SavedLayout("s", "Hide", (SavedCharacter("New", False, None),))
    with settings.update(doc, path) as live:
        live["preview"]["excluded"] = names
        live["preview"]["saved_layouts"] = serialize((snapshot,))
    before, disk = copy.deepcopy(doc), path.read_bytes()
    assert len(before["preview"]["excluded"]) == 70

    def fail(*args, **kwargs):
        raise OSError("Disk refused")

    monkeypatch.setattr(settings, "_save_locked", fail)
    with (
        pytest.raises(OSError, match="Disk refused"),
        settings.update(doc, path) as live,
    ):
        apply_snapshot(live["preview"], snapshot)
        live["preview"]["saved_layouts"]["items"].clear()
    assert doc == before
    assert path.read_bytes() == disk


def test_direct_preview_choice_transactions_retain_all_other_exclusions(tmp_path):
    path = tmp_path / "settings.json"
    doc = settings.load(path)
    names = [f"Pilot{i}" for i in range(65)]
    with settings.update(doc, path) as live:
        live["preview"]["excluded"] = names
    with settings.update(doc, path) as live:
        live["preview"]["excluded"].append("New")
    assert settings.load(path)["preview"]["excluded"] == [*names, "New"]
    with settings.update(doc, path) as live:
        live["preview"]["excluded"].remove("Pilot64")
    assert settings.load(path)["preview"]["excluded"] == [*names[:64], "New"]
