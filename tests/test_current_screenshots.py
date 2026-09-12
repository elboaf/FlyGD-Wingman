"""Current main-window cards exercise real owners, never live domain actions."""

import json
import subprocess

import pytest

from tests.html_tree import PageTree
from tests.test_new_screenshots import ROOT, shoot

# Explicit coverage contract; the original inventory remains in order.
SYNTHETIC = {
    "settings-companions-populated": "companions",
    "settings-companions-detail-narrow": "companions",
    "settings-companions-add": "companions",
    "settings-companions-source-narrow": "companions",
    "settings-wanderer": "previews",
    "settings-wanderer-narrow": "previews",
    "settings-fleet-characters-narrow": "fleet",
    "settings-fleet-sharing": "fleet",
    "settings-fleet-sharing-details": "fleet",
    "settings-fleet-sharing-history-narrow": "fleet",
}
LIVE = {
    "settings-uploading": "uploading",
    "settings-uploading-recording": "uploading",
    "settings-uploading-integrations": "uploading",
    "settings-uploading-webhook": "uploading",
    "settings-bookmarks-windows": "bookmarks",
    "settings-bookmarks-sigbar": "bookmarks",
    "settings-alerts-custom-narrow": "alerts",
}


SUBPAGES = {
    "settings-uploading": "youtube",
    "settings-uploading-recording": "recording",
    "settings-uploading-integrations": "recording",
    "settings-uploading-webhook": "combatlogs",
    "settings-previews": "windows",
    "settings-previews-middle": "windows",
    "settings-previews-table": "characters",
    "settings-previews-sticky-conflict": "characters",
    "settings-previews-detail": "characters",
    "settings-previews-copy": "characters",
    "settings-previews-groups": "characters",
    "settings-previews-narrow": "characters",
    "settings-previews-crop-narrow": "characters",
    "settings-wanderer": "wanderer",
    "settings-wanderer-narrow": "wanderer",
}


@pytest.mark.parametrize(
    "key", [key for key in SUBPAGES if key.startswith("settings-previews")]
)
def test_preview_stages_select_visible_subpages_and_their_scroll_owner(tmp_path, key):
    run_current_page(tmp_path, key, "preview-subpage")


def test_current_inventory_and_floor_coverage():
    screens = {s.key: s for s in shoot.SCREENS}
    assert screens.keys() >= SYNTHETIC.keys() | LIVE.keys()
    for key, section in (SYNTHETIC | LIVE).items():
        assert screens[key].section == section
        assert screens[key].at_floor == key.endswith("-narrow")
        assert screens[key].gated == (section not in {"companions", "uploading"})
        assert shoot.screen_setup_script(screens[key])
        assert shoot.new_screen_verify_script(screens[key])


@pytest.mark.parametrize("key", SYNTHETIC)
@pytest.mark.parametrize(
    "scenario", ["normal", "late-read", "late-synthetic", "invalid"]
)
def test_current_synthetic_owners(tmp_path, key, scenario):
    run_current_page(tmp_path, key, scenario)


@pytest.mark.parametrize("key", LIVE)
def test_lower_cards_frame_live_content_without_actions(tmp_path, key):
    run_current_page(tmp_path, key, "live-card")


@pytest.mark.parametrize(
    "key",
    ["settings-companions-populated", "settings-wanderer", "settings-fleet-sharing"],
)
def test_cleanup_before_any_live_hydration_erases_synthetic_content(tmp_path, key):
    run_current_page(tmp_path, key, "cold")


def test_companion_capture_does_not_take_over_a_live_dialog(tmp_path):
    run_current_page(tmp_path, "settings-companions-source-narrow", "live-dialog")


@pytest.mark.parametrize("evidence", ["cached", "same", "newer"])
def test_sharing_cleanup_preserves_failed_refresh_authority(tmp_path, evidence):
    run_current_page(tmp_path, "settings-fleet-sharing", "sharing-read-" + evidence)


@pytest.mark.parametrize("delivery", ["live", "buffered"])
def test_wanderer_cleanup_obeys_live_binding_health_fence(tmp_path, delivery):
    run_current_page(tmp_path, "settings-wanderer", "wanderer-fence-" + delivery)


@pytest.mark.parametrize(
    "action", ["toggle-button", "toggle-check", "reset", "character", "overlap"]
)
def test_fleet_capture_refuses_pending_live_writes(tmp_path, action):
    run_current_page(
        tmp_path, "settings-fleet-characters-narrow", "fleet-pending-" + action
    )


@pytest.mark.parametrize("action", ["pair", "grant", "overlap"])
def test_sharing_capture_refuses_pending_browser_actions(tmp_path, action):
    run_current_page(tmp_path, "settings-fleet-sharing", "sharing-pending-" + action)


def test_fleet_cleanup_restores_focused_master_without_changing_live_focus_policy(
    tmp_path,
):
    run_current_page(tmp_path, "settings-fleet-characters-narrow", "fleet-focused")


def run_current_page(tmp_path, key, scenario):
    screen = next((s for s in shoot.SCREENS if s.key == key), None)
    assert screen, f"missing current capture: {key}"
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = {
        "page": tree.root,
        "key": key,
        "section": screen.section,
        "scenario": scenario,
        "prepare": shoot.new_screen_prepare_script(screen),
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
        "fixture": shoot.load_dev_tool_screenshot_fixture(),
        "tab": SUBPAGES.get(key),
    }
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/current_screenshot_pages.cjs"),
            str(path),
            str(ROOT / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS current screenshot" in result.stdout


@pytest.mark.parametrize("key", SYNTHETIC)
@pytest.mark.parametrize(
    "failure", [None, "prepare", "entry", "stage", "verify", "capture"]
)
def test_current_walk_prepares_before_entry_and_always_cleans(
    tmp_path, monkeypatch, key, failure
):
    screen = next((s for s in shoot.SCREENS if s.key == key), None)
    assert screen, f"missing current capture: {key}"
    monkeypatch.setattr(shoot, "SCREENS", (screen,))
    monkeypatch.setattr(shoot.time, "sleep", lambda _: None)
    expressions = {
        "prepare": shoot.new_screen_prepare_script(screen),
        "entry": f"WM.openSettingsSection({screen.section!r})",
        "stage": shoot.screen_setup_script(screen),
        "verify": shoot.new_screen_verify_script(screen),
        "cleanup": shoot.new_screen_cleanup_script(screen),
    }
    calls = []

    class CDP:
        def evaluate(self, expression):
            calls.append(expression)
            if expression == "WM.eve_shown !== false":
                return True
            if failure and expression == expressions.get(failure):
                raise shoot.TargetError("injected " + failure)
            return None

        def screenshot(self):
            calls.append("capture")
            if failure == "capture":
                raise shoot.TargetError("injected capture")
            return b"png"

        def set_device_metrics_override(self, *, width, height):
            assert (width, height) == (840, 625)
            calls.append("floor")

        def clear_device_metrics_override(self):
            calls.append("clear")

    shots, _, _ = shoot.walk(CDP(), tmp_path, settle_ms=0)
    assert bool(shots[0]["error"]) == bool(failure)
    assert shots[0]["fixture"] == "wingman/web/dev.js:DEV_TOOL_SCREENSHOT_FIXTURE"
    assert expressions["cleanup"] in calls
    if failure != "prepare":
        assert calls.index(expressions["prepare"]) < calls.index(expressions["entry"])
    if screen.at_floor:
        assert calls.index("floor") < calls.index(expressions["prepare"])
        assert calls[-1] == "clear"
