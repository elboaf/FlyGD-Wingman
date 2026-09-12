"""Execute new capture staging against production pages, never an EVE profile."""

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from tests.html_tree import PageTree
from tests.test_fittings_page import _run_fittings_node

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "new_shoot", ROOT / "scripts/shoot_screens.py"
)
shoot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shoot
spec.loader.exec_module(shoot)
KEYS = {
    "profiles-formations",
    "profiles-formations-import",
    "profiles-setup-share",
    "profiles-setup-import",
    "settings-previews-crop-narrow",
}


def test_new_capture_inventory():
    screens = {screen.key: screen for screen in shoot.SCREENS}
    assert screens.keys() >= KEYS
    assert all(screens[key].gated for key in KEYS)
    assert screens["settings-previews-crop-narrow"].at_floor
    assert "formations" not in shoot.EXCLUDED_ROUTES
    assert "uisetup" not in shoot.EXCLUDED_ROUTES


def run_screenshot_page(tmp_path, key, regression=None):
    assert hasattr(shoot, "new_screen_prepare_script"), "new staging seam is missing"
    screen = next(screen for screen in shoot.SCREENS if screen.key == key)
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = {
        "page": tree.root,
        "key": key,
        "prepare": shoot.new_screen_prepare_script(screen),
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
        "regression": regression,
    }
    if key.startswith("fittings-"):
        data["fixture"] = shoot.fittings_fixture_setup_script()
        data["reset"] = shoot._fittings_reset_script()
        data["fittings_prepare"] = shoot._fittings_prepare_script(key)
        data["previous_prepare"] = shoot._fittings_prepare_script("fittings-alliance")
        data["previous_stage"] = shoot._fittings_setup_script("fittings-alliance")
    elif regression and key == "settings-previews-crop-narrow":
        data["crop_fixture"] = shoot.load_dev_tool_screenshot_fixture()["crop"]
        data["crop_fixture"]["preview"] = shoot.load_dev_preview_fixture()
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/screenshot_pages.cjs"),
            str(path),
            str(ROOT / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS screenshot" in result.stdout


@pytest.mark.parametrize(
    ("key", "scenario"),
    [
        ("settings-previews-groups", "fidelity"),
        ("settings-characters-waiting", "fidelity"),
        ("settings-characters-partial-cleanup", "fidelity"),
        ("fittings-copy-limit", "fidelity"),
        ("fittings-copy-result", "fidelity"),
        *[
            ("fittings-copy-progress", exit_kind)
            for exit_kind in (
                "cancel",
                "close",
                "leave",
                "teardown",
                "start",
                "late-live",
            )
        ],
    ],
)
def test_capture_fidelity_and_writer_free_exit(tmp_path, key, scenario):
    run_screenshot_page(tmp_path, key, scenario)


@pytest.mark.parametrize(
    "renamed_id",
    [
        pytest.param("fit-gen-2", id="duplicate-selected-name"),
        pytest.param("fit-gen-0", id="unselected-name-collision"),
    ],
)
def test_limit_capture_uses_entry_identity(tmp_path, monkeypatch, renamed_id):
    fixture = shoot.load_dev_fittings_screenshot_fixture()
    entries = {entry["id"]: entry for entry in fixture["entries"]}
    entries[renamed_id]["name"] = entries["fit-gen-1"]["name"]
    for pair in fixture["limit_preflight"]["pairs"]:
        if pair["entry_id"] == renamed_id:
            pair["fitting_name"] = entries[renamed_id]["name"]
    monkeypatch.setattr(
        shoot, "load_dev_fittings_screenshot_fixture", lambda: deepcopy(fixture)
    )
    run_screenshot_page(tmp_path, "fittings-copy-limit", "fidelity")


@pytest.mark.parametrize("stage", ["progress", "results"])
def test_fittings_capture_preserves_pending_confirmation(tmp_path, stage):
    key = "fittings-copy-progress" if stage == "progress" else "fittings-copy-result"
    screen = next(screen for screen in shoot.SCREENS if screen.key == key)
    fixture = shoot.load_dev_fittings_screenshot_fixture()
    fixture["copy_stage"] = stage
    scenario = "interleaving-screenshot-" + stage
    result = _run_fittings_node(
        tmp_path,
        scenario,
        screenshot={
            "payload": fixture,
            "verify": shoot.new_screen_verify_script(screen),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


@pytest.mark.parametrize(
    "geometry",
    [
        "descendant-hit",
        "missing-summary",
        "hidden-summary",
        "hidden-panel",
        "inside-outer-crossing-inner",
        "zero-area",
        "pane-top",
        "pane-bottom",
        "pane-left",
        "pane-right",
        "viewport-top",
        "viewport-bottom",
        "viewport-left",
        "viewport-right",
        "occluded-center",
        "occluded-corner",
        "null-hit",
    ],
)
def test_groups_capture_rejects_clipped_or_occluded_controls(tmp_path, geometry):
    run_screenshot_page(tmp_path, "settings-previews-groups", {"geometry": geometry})


@pytest.mark.parametrize("key", sorted(KEYS))
def test_new_capture_staging_executes_without_bridge_or_clipboard(tmp_path, key):
    run_screenshot_page(tmp_path, key)


@pytest.mark.parametrize(
    "scenario",
    [
        "settled",
        "collapsed",
        "wrong-target",
        "missing-detail",
        "missing-rack",
        "missing-alias",
        "missing-presence",
        "unresolved",
        "late-reset",
        "late-reinject",
        "late-state",
        "cleanup",
        "late-cleanup",
    ],
)
def test_fittings_detail_capture_requires_settled_named_detail(tmp_path, scenario):
    run_screenshot_page(tmp_path, "fittings-detail", scenario)


@pytest.mark.parametrize(
    "control",
    [
        "clear",
        "group-clear",
        "capture",
        "bind",
        "size",
        "copy",
        "exclude",
        "lock",
        "never-minimize",
        "group",
        "add",
        "rename",
        "delete",
        "crop-select",
        "crop-remove",
        "crop-enabled",
        "reentry",
    ],
)
def test_crop_screenshot_blocks_live_controls(tmp_path, control):
    run_screenshot_page(tmp_path, "settings-previews-crop-narrow", {"control": control})


@pytest.mark.parametrize(
    "control", ["bind", "size", "copy", "rename", "delete", "crop-remove"]
)
def test_crop_screenshot_blocks_dialog_started_live(tmp_path, control):
    run_screenshot_page(
        tmp_path,
        "settings-previews-crop-narrow",
        {"control": control, "late": "dialog"},
    )


@pytest.mark.parametrize("control", ["bind", "size"])
def test_crop_screenshot_blocks_parser_started_live(tmp_path, control):
    run_screenshot_page(
        tmp_path,
        "settings-previews-crop-narrow",
        {"control": control, "late": "parser"},
    )


@pytest.mark.parametrize("operation", ["matching", "newer", "older"])
def test_crop_screenshot_cleanup_settles_only_terminal_live_operation(
    tmp_path, operation
):
    run_screenshot_page(
        tmp_path, "settings-previews-crop-narrow", {"operation": operation}
    )


@pytest.mark.parametrize("failure", ["prepare", "stage", "verify", "capture"])
@pytest.mark.parametrize(
    "key", ["profiles-setup-import", "settings-previews-crop-narrow"]
)
def test_new_capture_cleanup_runs_after_any_failure(
    tmp_path, monkeypatch, failure, key
):
    assert hasattr(shoot, "new_screen_cleanup_script"), "cleanup seam is missing"
    screen = next(s for s in shoot.SCREENS if s.key == key)
    monkeypatch.setattr(shoot, "SCREENS", (screen,))
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    expressions = {
        "prepare": shoot.new_screen_prepare_script(screen),
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
    }
    calls = []

    class CDP:
        def set_device_metrics_override(self, *, width, height):
            assert (width, height) == (840, 625)
            calls.append("floor")

        def clear_device_metrics_override(self):
            calls.append("clear")

        def evaluate(self, expression):
            calls.append(expression)
            if expression == "WM.eve_shown !== false":
                return True
            if expression == expressions.get(failure):
                raise shoot.TargetError("injected failure")
            return None

        def screenshot(self):
            calls.append("capture")
            if failure == "capture":
                raise shoot.TargetError("injected failure")
            return b"png"

    shots, _, _ = shoot.walk(CDP(), tmp_path, settle_ms=0)
    assert shots[0]["error"]
    assert shots[0]["fixture"] == "wingman/web/dev.js:DEV_TOOL_SCREENSHOT_FIXTURE"
    assert expressions["cleanup"] in calls
    if screen.at_floor:
        assert calls.index("floor") < calls.index(expressions["prepare"])
        assert calls[-2:] == [expressions["cleanup"], "clear"]
    else:
        assert calls[-1] == expressions["cleanup"]


@pytest.mark.parametrize(
    "source", ["no marker", "var DEV_TOOL_SCREENSHOT_FIXTURE = {broken}"]
)
def test_tool_fixture_extraction_fails_closed(tmp_path, source):
    path = tmp_path / "wingman/web/dev.js"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match=r"not found|Invalid screenshot fixture"):
        shoot.load_dev_tool_screenshot_fixture(str(tmp_path))
