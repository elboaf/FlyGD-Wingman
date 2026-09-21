"""Current main-window cards exercise real owners, never live domain actions."""

import json
import subprocess
from copy import deepcopy
from dataclasses import asdict, replace
from threading import RLock
from types import SimpleNamespace

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


def _sharing_screenshot_status(*, live=False, newer=False, pending=False):
    """Independent observations, not values read back from the JS fixture."""
    from wingman.fleetsharing import protocol as p
    from wingman.fleetsharing.config import canonical_origin
    from wingman.fleetsharing.state import AutomaticState
    from wingman.fleetsharing.worker import (
        PendingSourceStatus,
        SharingMetadata,
        SharingStatus,
    )

    source_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    source_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    source_generation = 4 if newer else 3
    consent = p.Consent(0, 0, False, None, None, None, None)
    status = SharingStatus(
        "active",
        metadata=SharingMetadata(
            loaded=True,
            binding="screenshot-only-binding",
            paired_origin="https://authgd.example",
            device_id=source_a,
            has_session=True,
            session_expires_at="2026-09-07T12:30:00.000Z",
            feature_enabled=True,
            approved_capabilities=(p.SHARED_CAPABILITY,),
            session_approved_capabilities=(p.SHARED_CAPABILITY,),
            acknowledged_capabilities=(p.SHARED_CAPABILITY,),
        ),
        sources=p.Sources(
            (
                p.SourceView(
                    source_a, source_generation, 1, "active", None, None, None
                ),
                p.SourceView(source_b, 2, 2, "ended", "boss_lost", None, None),
            ),
            (
                p.SourceCharacter(1, "Aiga Otsolen", source_a, True, True),
                p.SourceCharacter(2, "Ariadne", source_b, False, True),
            ),
        ),
        eligibility=p.Eligibility(
            1,
            "ready",
            tuple(
                p.EligibilityEntry(
                    character,
                    source_a,
                    source_generation,
                    1,
                    "2026-09-07T12:00:10.000Z",
                )
                for character in (1, 2)
            ),
        ),
        observed_participation=p.Participation(True, 1),
        automatic=AutomaticState(observed_consent=consent),
        automatic_status=p.AutomaticStatus(consent, "none", "off", "none", None, ()),
        automatic_stage="settled",
    )
    if live or newer:
        # Distinct live observations prove cleanup neither retains synthetic
        # consent nor restores stale binding/generation authority.
        consent = p.Consent(
            2 if newer else 1,
            2 if newer else 1,
            True,
            source_a,
            "2026-09-07T12:00:01.000Z" if newer else "2026-09-07T12:00:00.000Z",
            None,
            None,
        )
        capabilities = (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY)
        status = replace(
            status,
            metadata=replace(
                status.metadata,
                binding="live-newer-binding" if newer else "live-only-binding",
                paired_origin="https://newer.example"
                if newer
                else "https://live.example",
                approved_capabilities=capabilities,
                session_approved_capabilities=capabilities,
                acknowledged_capabilities=capabilities,
            ),
            automatic=AutomaticState(observed_consent=consent),
            automatic_status=p.AutomaticStatus(
                consent, "this_device", "waiting_for_fleet", "none", None, ()
            ),
        )

    if pending:
        # An already-persisted live request exercises the separate worklist;
        # constructing this observation does not enqueue or execute a command.
        command = p.SourceStart(
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            1,
            source_a,
            "2026-09-07T12:00:01.000Z",
        )
        assert p.parse_source_command(p.source_command_body(command)) == command
        status = replace(
            status,
            pending_sources=(
                PendingSourceStatus(
                    command.source_id, "start", 1, "persisted", command
                ),
            ),
        )

    # Dataclasses do not validate wire enums, completeness or contradictions.
    # Round-trip observations through the real pure codecs before projecting.
    assert p.parse_consent(asdict(consent)) == consent
    assert (
        p.parse_automatic_status(_sharing_json(asdict(status.automatic_status)))
        == status.automatic_status
    )
    assert (
        p.parse_participation(asdict(status.observed_participation))
        == status.observed_participation
    )
    assert (
        p.parse_sources(
            {"protocol": p.API_VERSION, **_sharing_json(asdict(status.sources))}
        )
        == status.sources
    )
    assert (
        p.parse_eligibility(
            {"protocol": p.API_VERSION, **_sharing_json(asdict(status.eligibility))}
        )
        == status.eligibility
    )
    metadata = status.metadata
    for capabilities in (
        metadata.approved_capabilities,
        metadata.session_approved_capabilities,
        metadata.acknowledged_capabilities,
    ):
        assert p.capabilities(list(capabilities)) == capabilities
    assert canonical_origin(metadata.paired_origin) == metadata.paired_origin
    return status


def _sharing_json(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _sharing_screenshot_projection(*, live=False, newer=False, pending=False):
    from wingman.fleetsharing import config
    from wingman.ui.api import Api

    status = _sharing_screenshot_status(live=live, newer=newer, pending=pending)
    # No Api/worker construction: this read needs detached observations and a
    # liveness sentinel, never a real runtime, network, DPAPI or native owner.
    receiver = SimpleNamespace(
        _sharing_delivery_lock=RLock(),
        _sharing_status=status,
        _sharing_controls=Api._sharing_controls,
        _fleet_sharing=object(),
        _sharing_closed=False,
        _sharing_enabled=True,
        _sharing_preference_order=0,
        _sharing_preference_error=None,
        _sharing_runtime_error=None,
        _sharing_browser_error=None,
        _sharing_browser_retry=None,
        _sharing_telemetry_available=True,
        _sharing_presentation=None,
        _sharing_presentation_order=0,
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            config, "resolve_relay_origin", lambda: status.metadata.paired_origin
        )
        return _sharing_json(Api.fleet_sharing_state(receiver))


def _assert_sharing_projection(actual, expected, path=()):
    # Equality alone accepts bool/int substitutions, including inside arrays.
    assert type(actual) is type(expected), (path, actual, expected)
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), (path, actual.keys(), expected.keys())
        for key, value in expected.items():
            _assert_sharing_projection(actual[key], value, (*path, key))
    elif isinstance(expected, list):
        assert len(actual) == len(expected), (path, len(actual), len(expected))
        for index, value in enumerate(expected):
            _assert_sharing_projection(actual[index], value, (*path, index))
    else:
        assert actual == expected, (path, actual, expected)


def test_sharing_screenshot_fixture_uses_current_control_projection():
    state = shoot.load_dev_tool_screenshot_fixture()["fleet"]["sharing"]["state"]
    _assert_sharing_projection(state, _sharing_screenshot_projection())


def _sharing_projection_mutations(value, path=()):
    """Derive guard probes from the real DTO, not another hand-kept schema."""
    if isinstance(value, dict):
        yield "extra-key", path, dict(value, unexpected=None)
        for key, item in value.items():
            yield "missing-key", path, {k: v for k, v in value.items() if k != key}
            yield from _sharing_projection_mutations(item, (*path, key))
    elif isinstance(value, list):
        yield "extra-item", path, [*value, value[0] if value else None]
        if value:
            yield "missing-item", path, value[1:]
        if len(value) > 1 and value != value[::-1]:
            yield "reordered-items", path, value[::-1]
        for index, item in enumerate(value):
            yield from _sharing_projection_mutations(item, (*path, index))
    elif type(value) is bool:
        yield "bool-as-int", path, int(value)
        yield "changed-bool", path, not value
    elif type(value) is int:
        yield "int-as-float", path, float(value)
        yield "changed-int", path, value + 1
        if value in (0, 1):
            yield "int-as-bool", path, bool(value)
    elif isinstance(value, str):
        yield "stale-string", path, "stale-" + value
    elif value is None:
        yield "changed-null", path, False


@pytest.mark.parametrize(
    "fault",
    [
        "missing-key",
        "extra-key",
        "missing-item",
        "extra-item",
        "reordered-items",
        "bool-as-int",
        "int-as-bool",
        "int-as-float",
        "changed-bool",
        "changed-int",
        "stale-string",
        "changed-null",
    ],
)
def test_sharing_screenshot_projection_guard_rejects_drift(fault):
    expected = _sharing_screenshot_projection()
    _assert_sharing_projection(deepcopy(expected), expected)
    cases = 0
    for kind, path, replacement in _sharing_projection_mutations(expected):
        if kind != fault:
            continue
        changed = deepcopy(expected)
        if path:
            owner = changed
            for step in path[:-1]:
                owner = owner[step]
            owner[path[-1]] = replacement
        else:
            changed = replacement
        with pytest.raises(AssertionError):
            _assert_sharing_projection(changed, expected)
        cases += 1
    assert cases, f"No projection paths exercise {fault}"


@pytest.mark.parametrize(
    "case",
    [
        "cold",
        "live-before",
        "live-during",
        "cold-then-live",
        "repeat",
        "authority",
        "focus",
        "worklists",
    ],
)
def test_sharing_screenshot_lifecycle_preserves_live_authority(tmp_path, case):
    run_current_page(tmp_path, "settings-fleet-sharing", "sharing-lifecycle-" + case)


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
    if screen.section == "fleet":
        data["live_sharing"] = _sharing_screenshot_projection(live=True)
        data["live_sharing_newer"] = _sharing_screenshot_projection(
            live=True, newer=True, pending=scenario == "sharing-lifecycle-worklists"
        )
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
