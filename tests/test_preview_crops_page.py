"""Crop bridge/layout guards; actual browser evidence lives in the Task 9 report.

These deliberately complement, not replace, executing the real dev page.
"""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"
SRC = (WEB / "previews.js").read_text(encoding="utf-8")


def body(name):
    # Fleet Bar has its own render() above the Preview IIFE.
    return SRC.rsplit(f"function {name}(", 1)[1].split("\n  function ", 1)[0]


def test_crop_ui_has_semantic_requests_and_registered_handler():
    for method in (
        "select_preview_crop",
        "set_preview_crop_enabled",
        "remove_preview_crop",
        "get_preview_crop_state",
    ):
        assert method in SRC
    assert "WM.handle('onPreviewCrops'" in SRC
    assert SRC.index("WM.handle('onPreviewCrops'") < SRC.index(
        "var host = WM.el('preview-binds')"
    )


def test_crop_owners_join_null_prototype_roster():
    assert "Object.create(null)" in body("rows")
    assert "Object.keys(cropState.definitions" in body("rows")
    assert "ownValue(cropState.definitions, name)" in body("hasEnabledCrop")
    assert "runtime_enabled" not in body("hasEnabledCrop")


def test_crop_only_roster_repaint_preserves_group_draft_and_safe_name_lookup():
    assert "cropRosterEdit" in body("acceptCrops")
    assert "draft.value = edit.value" in body("render")
    assert "ownValue(gbc, characterName)" in body("makeGroupSelect")
    assert "ownValue(state.hotkeys.characters, entry.name)" in body("render")


def test_crop_hydration_uses_delivery_revision_not_outcome_revision():
    accept = body("acceptCrops")
    assert "payload.revision < cropState.revision" in accept
    assert "cropState = payload" in accept
    assert "operation.revision" not in accept
    assert "acceptCrops(payload.crops" in body("refresh")
    assert "get_preview_crop_state" in body("refreshCrops")


def test_crop_receipts_do_not_patch_committed_definitions():
    request = body("requestCrop")
    assert "!cropHydrated" in request
    assert "endCapture()" in request
    assert "operation_id" in request
    assert "pending" in request
    assert "refreshCrops" in request
    assert "cropState.definitions[" not in request


def test_crop_field_stays_inside_configure_with_safe_removal():
    assert "makeCropField(characterName)" in body("makeCharacterDetail")
    field = body("makeCropField")
    assert "'Crop'" in field
    assert "'btn', 'Select region…'" in field
    assert "'btn danger', 'Remove'" in field
    assert "'check'" in field and "'box'" in field
    assert "WM.confirm(" in field
    assert field.index("endCapture()") < field.index("WM.confirm(")
    assert "selection and position" in field and "Disable" in field
    assert "destructive: true" in field


def test_crop_repaint_does_not_refresh_hotkeys_or_unrelated_controls():
    paint = body("paintCrops")
    assert "paintCropField" in paint
    assert "paintCropLocks" in paint
    assert "refresh()" not in paint
    assert "state.hotkeys =" not in paint
    assert "detailInteraction" in body("finishCropFocus")
    leave = SRC.split("addEventListener('wm:section'", 1)[1]
    assert "cropHydrated = false" in leave
    assert "delete cropRequests" not in leave


def test_crop_status_and_conflict_gates_cover_runtime_states():
    for status in (
        "master-off",
        "offline",
        "selecting",
        "saving",
        "live",
        "cap-suppressed",
        "invalid-source",
        "degraded",
        "stopping",
        "disabled",
    ):
        assert "'" + status + "'" in body("cropMessage")
    assert "cropState.cap" in body("cropMessage")
    assert "cropState.busy" in body("paintCropField")
    assert "cropState.runtime_enabled" in body("paintCropField")
