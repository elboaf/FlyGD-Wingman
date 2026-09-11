"""Controller contracts exercised against real serialized settings transactions."""

import copy
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from threading import Barrier, Event
from types import SimpleNamespace

import pytest

from wingman import settings
from wingman.alerts.controller import AlertsController, AlertsPorts
from wingman.telemetry.model import CustomMatcherHealth


@pytest.fixture
def harness(tmp_path):
    path = tmp_path / "settings.json"
    document = settings.load(path)
    h = SimpleNamespace(
        path=path,
        document=document,
        sounds=[],
        raised=[],
        available=True,
        characters=("Alice", "Bob"),
        health=CustomMatcherHealth("waiting"),
        reader={
            "running": True,
            "last_error": None,
            "characters": ["Alice", "Bob"],
            "gamelogs_folder": "logs",
        },
    )
    h.ports = AlertsPorts(
        update_settings=lambda: settings.update(document, path),
        reader_state=lambda: copy.deepcopy(h.reader),
        matcher_health=lambda: h.health,
        preview_characters=lambda: h.characters,
        preview_available=lambda: h.available,
        raise_alert=lambda character, event, spec: h.raised.append(
            (character, event, spec)
        ),
        play_sound=lambda sound, volume: h.sounds.append((sound, volume)),
    )
    h.controller = AlertsController(document, ports=h.ports)
    return h


@pytest.fixture
def controller(harness):
    return harness.controller


def test_add_is_disabled_and_enable_without_search_refuses(controller):
    added = controller.add()
    assert added["applied"] and added["persisted"]
    rule = added["state"]["rules"][0]
    assert rule["name"] == "Custom alert"
    assert rule["search"] == ""
    assert rule["enabled"] is False
    assert rule["color"] == "#ff8c42"
    assert rule["sound"] == "none"
    assert rule["cooldown_s"] == 8
    refused = controller.set_enabled(rule["id"], True)
    assert not refused["applied"] and not refused["persisted"]
    assert controller.state()["rules"] == added["state"]["rules"]


def _draft(rule, **changes):
    return {key: value for key, value in {**rule, **changes}.items() if key != "id"}


def _add(controller):
    result = controller.add()
    assert result["applied"] and result["persisted"]
    return next(
        row for row in result["state"]["rules"] if row["id"] == result["rule_id"]
    )


def _assert_refused(result):
    assert result["applied"] is False
    assert result["persisted"] is False
    assert result["error"]


def test_eight_rule_capacity_and_duplicate_names(controller):
    rules = [_add(controller) for _ in range(8)]
    assert len({row["id"] for row in rules}) == 8
    assert {row["name"] for row in rules} == {"Custom alert"}
    before = controller.runtime_snapshot()
    _assert_refused(controller.add())
    assert controller.runtime_snapshot() is before
    assert controller.state()["limit"] == len(controller.state()["rules"]) == 8


def test_concurrent_adds_cannot_oversubscribe_capacity(harness):
    barrier = Barrier(12)

    def add():
        barrier.wait(timeout=5)
        return harness.controller.add()

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: add(), range(12)))
    assert sum(result["applied"] for result in results) == 8
    saved = settings.load(harness.path)["preview"]["alerts"]["custom_rules"]
    assert len(saved) == len({row["id"] for row in saved}) == 8
    assert harness.controller.state()["rules"] == saved


@pytest.mark.parametrize("rule_id", [None, "", "missing", "bad.id", [], {}, 1])
@pytest.mark.parametrize("method", ["edit", "set_enabled", "remove"])
def test_unknown_or_invalid_ids_refuse_without_writing(controller, rule_id, method):
    rule = _add(controller)
    before = controller.runtime_snapshot()
    args = {"edit": (_draft(rule),), "set_enabled": (True,), "remove": ()}
    _assert_refused(getattr(controller, method)(rule_id, *args[method]))
    assert controller.runtime_snapshot() is before


@pytest.mark.parametrize(
    "field", ["name", "search", "enabled", "color", "sound", "cooldown_s"]
)
def test_incomplete_full_edit_refuses(controller, field):
    rule = _add(controller)
    draft = _draft(rule, search="fleet invite")
    del draft[field]
    before = controller.runtime_snapshot()
    _assert_refused(controller.edit(rule["id"], draft))
    assert controller.runtime_snapshot() is before


@pytest.mark.parametrize("draft", [None, [], "draft", 42])
def test_nonobject_edit_refuses(controller, draft):
    rule = _add(controller)
    _assert_refused(controller.edit(rule["id"], draft))


def test_edit_canonicalizes_owns_identity_and_roundtrips(harness):
    c = harness.controller
    rule = _add(c)
    draft = _draft(
        rule,
        name="  Fleet  ",
        search="  Fleet <b>Invite</b>  ",
        enabled=True,
        color="#abcdef",
        sound="obey",
        cooldown_s=120,
    )
    draft.update(id="not-authority", custom_generation=0, unknown="discard")
    original = copy.deepcopy(draft)
    result = c.edit(rule["id"], draft)
    assert result["applied"] and result["persisted"] and result["error"] is None
    expected = {
        "id": rule["id"],
        "name": "Fleet",
        "search": "Fleet <b>Invite</b>",
        "enabled": True,
        "color": "#abcdef",
        "sound": "obey",
        "cooldown_s": 120,
    }
    assert result["state"]["rules"] == [expected]
    assert result["rule_id"] == rule["id"]
    assert draft == original
    assert (
        settings.load(harness.path)
        == harness.document
        == json.loads(harness.path.read_text())
    )
    assert harness.document["preview"]["alerts"]["custom_rules"] == [expected]
    assert result["state"]["revision"] == c.runtime_snapshot().rules_revision == 3


def test_canonical_noops_skip_save_and_retain_snapshot(controller, monkeypatch):
    rule = _add(controller)
    before = controller.runtime_snapshot()

    def forbidden(*args, **kwargs):
        pytest.fail("no-op must not attempt disk I/O")

    monkeypatch.setattr(settings, "_save_locked", forbidden)
    for result in (
        controller.edit(rule["id"], _draft(rule, name="  Custom alert  ", search="  ")),
        controller.set_enabled(rule["id"], False),
    ):
        assert result["applied"] and result["persisted"] and result["error"] is None
        assert result["rule_id"] == rule["id"]
    assert controller.runtime_snapshot() is before


@pytest.mark.parametrize("enabled", [None, 0, 1, "true", "false", [], {}])
def test_toggle_refuses_nonboolean_values(controller, enabled):
    rule = _add(controller)
    before = controller.runtime_snapshot()
    _assert_refused(controller.set_enabled(rule["id"], enabled))
    assert controller.runtime_snapshot() is before


def test_enable_then_clear_disables_atomically(controller):
    rule = _add(controller)
    controller.edit(rule["id"], _draft(rule, search="fleet invite"))
    enabled = controller.set_enabled(rule["id"], True)
    assert enabled["applied"] and enabled["state"]["rules"][0]["enabled"] is True
    rule = enabled["state"]["rules"][0]
    cleared = controller.edit(rule["id"], _draft(rule, search="   "))
    assert cleared["applied"]
    assert cleared["state"]["rules"][0]["search"] == ""
    assert cleared["state"]["rules"][0]["enabled"] is False
    _assert_refused(controller.set_enabled(rule["id"], True))


def test_remove_preserves_sibling_and_its_generation(controller):
    first, second = _add(controller), _add(controller)
    before = controller.runtime_snapshot()
    result = controller.remove(first["id"])
    assert result["applied"] and result["persisted"]
    assert result["state"]["rules"] == [second]
    assert result["rule_id"] == first["id"]
    after = controller.runtime_snapshot()
    assert after.rules_revision == before.rules_revision + 1
    assert after.custom_rules[0].generation == before.custom_rules[1].generation


def test_concurrent_independent_edits_preserve_both_rows(harness):
    rules = [_add(harness.controller), _add(harness.controller)]
    barrier = Barrier(2)

    def edit(index):
        barrier.wait(timeout=5)
        return harness.controller.edit(
            rules[index]["id"], _draft(rules[index], name=f"Rule {index}")
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, range(2)))
    assert all(result["applied"] and result["persisted"] for result in results)
    assert [row["name"] for row in harness.controller.state()["rules"]] == [
        "Rule 0",
        "Rule 1",
    ]
    assert (
        settings.load(harness.path)["preview"]["alerts"]["custom_rules"]
        == harness.controller.state()["rules"]
    )


@pytest.mark.parametrize("method", ["add", "edit", "set_enabled", "remove"])
def test_failed_save_rolls_back_each_mutation_and_keeps_snapshot(
    harness, monkeypatch, method
):
    c = harness.controller
    rule = _add(c)
    c.edit(rule["id"], _draft(rule, search="fleet invite"))
    before, document, disk = (
        c.runtime_snapshot(),
        copy.deepcopy(harness.document),
        harness.path.read_bytes(),
    )

    def fail(*args, **kwargs):
        raise OSError("PRIVATE SEARCH OR PATH")

    monkeypatch.setattr(settings, "_save_locked", fail)
    args = {
        "add": (),
        "edit": (rule["id"], _draft(rule, name="Edited")),
        "set_enabled": (rule["id"], True),
        "remove": (rule["id"],),
    }
    result = getattr(c, method)(*args[method])
    _assert_refused(result)
    assert "PRIVATE" not in result["error"]
    assert c.runtime_snapshot() is before
    assert result["state"]["rules"] == [asdict(row.rule) for row in before.custom_rules]
    assert harness.document == document
    assert harness.path.read_bytes() == disk


def test_blocked_save_exposes_no_candidate_and_reads_do_not_wait(harness, monkeypatch):
    c = harness.controller
    rule = _add(c)
    before = c.runtime_snapshot()
    entered, release = Event(), Event()
    save = settings._save_locked

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        save(*args, **kwargs)

    monkeypatch.setattr(settings, "_save_locked", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        write = pool.submit(c.edit, rule["id"], _draft(rule, name="Committed later"))
        try:
            assert entered.wait(5)
            state = pool.submit(c.state).result(timeout=2)
            assert state["rules"] == [rule]
            assert c.runtime_snapshot() is before
        finally:
            release.set()
        result = write.result(timeout=5)
    assert result["state"]["rules"][0]["name"] == "Committed later"
    assert result["state"]["revision"] == before.rules_revision + 1


def test_state_ports_run_outside_settings_transaction(harness):
    calls = []

    def reader():
        # Fail rather than strand a test worker on a regressed non-reentrant lock.
        assert settings._SAVE_LOCK.acquire(blocking=False)
        settings._SAVE_LOCK.release()
        with settings.update(harness.document, harness.path):
            harness.document["category"] = "22"
        calls.append(True)
        return copy.deepcopy(harness.reader)

    c = AlertsController(
        harness.document, ports=replace(harness.ports, reader_state=reader)
    )
    result = c.add()
    assert result["applied"] and calls == [True]
    assert harness.document["category"] == "22"


@pytest.mark.parametrize("search", ["", "ab", "<b></b>", "\u0001private", None, {}])
def test_test_uses_only_draft_style_and_trusted_timed_tokens(harness, search):
    c = harness.controller
    rule = _add(c)
    with settings.update(harness.document, harness.path):
        harness.document["preview"]["alerts"].update(
            volume=37, persist_until_selected=True
        )
    before, disk = c.runtime_snapshot(), harness.path.read_bytes()
    draft = _draft(
        rule,
        name=None,
        search=search,
        enabled="not a boolean",
        color="#abcdef",
        sound="obey",
        cooldown_s=120,
    )
    draft.update(
        id="forged",
        custom_rule_id="forged",
        custom_generation=99,
        custom_activation_epoch=99,
        custom_test=False,
        persist_until_selected=True,
        pulses=16,
    )
    original = copy.deepcopy(draft)
    # Neither master nor rule enable gates a presentation-only Test. Repetition
    # with a 120-second cooldown must still present on every invocation.
    for _ in range(2):
        result = c.test(rule["id"], draft)
        assert result == {"applied": True, "persisted": False, "error": None}
    assert harness.sounds == [("obey", 37), ("obey", 37)]
    expected = {
        "enabled": True,
        "color": "#abcdef",
        "sound": "obey",
        "cooldown_s": 120,
        "pulses": 3,
        "flash_rate": "normal",
        "persist_until_selected": False,
        "custom_test": True,
        "custom_rule_id": rule["id"],
        "custom_generation": 0,
        "custom_activation_epoch": 0,
    }
    assert harness.raised == [
        (name, "custom", expected) for name in ("Alice", "Bob", "Alice", "Bob")
    ]
    assert harness.raised[0][2] is not harness.raised[1][2]
    assert draft == original
    assert c.runtime_snapshot() is before
    assert harness.path.read_bytes() == disk


@pytest.mark.parametrize("rule_id", [None, "", "missing", [], {}, 1])
def test_test_requires_existing_id(harness, rule_id):
    rule = _add(harness.controller)
    _assert_refused(harness.controller.test(rule_id, _draft(rule, sound="obey")))
    assert harness.sounds == harness.raised == []


@pytest.mark.parametrize(
    "draft", [None, [], "draft", {}, {"color": "#abcdef", "sound": "obey"}]
)
def test_test_requires_style_object(harness, draft):
    rule = _add(harness.controller)
    _assert_refused(harness.controller.test(rule["id"], draft))
    assert harness.sounds == harness.raised == []


@pytest.mark.parametrize(
    "changes",
    [
        {"color": "red"},
        {"color": "#abcdef\n"},
        {"sound": "missing"},
        {"sound": "alarm"},
        {"cooldown_s": True},
        {"cooldown_s": 121},
    ],
)
def test_test_refuses_invalid_style_without_side_effects(harness, changes):
    rule = _add(harness.controller)
    before = harness.controller.runtime_snapshot()
    _assert_refused(harness.controller.test(rule["id"], _draft(rule, **changes)))
    assert harness.sounds == harness.raised == []
    assert harness.controller.runtime_snapshot() is before


@pytest.mark.parametrize(
    "available,characters,reason",
    [(False, ("Alice",), "Previews"), (True, (), "No EVE clients")],
)
@pytest.mark.parametrize(
    "sound,volume,audible",
    [("obey", 41, True), ("none", 41, False), ("obey", 0, False)],
)
def test_test_no_visual_truthfully_reports_audible_effect(
    harness, available, characters, reason, sound, volume, audible
):
    c = harness.controller
    rule = _add(c)
    harness.available, harness.characters = available, characters
    with settings.update(harness.document, harness.path):
        harness.document["preview"]["alerts"]["volume"] = volume
    result = c.test(rule["id"], _draft(rule, sound=sound))
    assert result["applied"] is audible
    assert result["persisted"] is False
    assert reason in result["error"]
    assert ("only the sound played" in result["error"]) is audible
    assert harness.sounds == ([("obey", 41)] if audible else [])
    assert harness.raised == []


@pytest.mark.parametrize("sound,volume", [("none", 100), ("obey", 0)])
def test_test_silent_visual_is_still_applied(harness, sound, volume):
    rule = _add(harness.controller)
    with settings.update(harness.document, harness.path):
        harness.document["preview"]["alerts"]["volume"] = volume
    assert harness.controller.test(rule["id"], _draft(rule, sound=sound)) == {
        "applied": True,
        "persisted": False,
        "error": None,
    }
    assert harness.sounds == []
    assert len(harness.raised) == 2


def _activate(harness):
    rule = _add(harness.controller)
    result = harness.controller.edit(
        rule["id"], _draft(rule, search="fleet invite", enabled=True)
    )
    assert result["applied"]
    with settings.update(harness.document, harness.path):
        harness.document["preview"]["enabled"] = True
        harness.document["preview"]["alerts"]["enabled"] = True
    return result["state"]["rules"][0]


def test_current_tokens_follow_commits_and_reserved_tokens_require_only_identity(
    harness,
):
    c = harness.controller
    rule = _activate(harness)
    snapshot = c.runtime_snapshot()
    generation, epoch = snapshot.custom_rules[0].generation, snapshot.activation_epoch
    assert c.is_current(rule["id"], generation, epoch)
    assert c.is_current(rule["id"], 0, 0)
    assert not c.is_current(rule["id"], 0, epoch)
    assert not c.is_current(rule["id"], generation, 0)
    c.edit(rule["id"], _draft(rule, name="Changed"))
    assert not c.is_current(rule["id"], generation, epoch)
    assert c.is_current(rule["id"], 0, 0)
    c.set_enabled(rule["id"], False)
    assert c.is_current(rule["id"], 0, 0)
    c.remove(rule["id"])
    assert not c.is_current(rule["id"], 0, 0)


def test_final_close_is_one_way_and_rejects_test_and_runtime_tokens(harness):
    c = harness.controller
    rule = _activate(harness)
    before = c.runtime_snapshot()
    generation, epoch = before.custom_rules[0].generation, before.activation_epoch
    assert c.is_current(rule["id"], generation, epoch)
    c.close_runtime()
    c.close_runtime()
    assert c.runtime_snapshot() is before
    assert not c.is_current(rule["id"], generation, epoch)
    assert not c.is_current(rule["id"], 0, 0)
    _assert_refused(c.test(rule["id"], _draft(rule, sound="obey")))
    assert harness.sounds == harness.raised == []
    c.edit(rule["id"], _draft(rule, name="After close"))
    latest = c.runtime_snapshot()
    assert not c.is_current(
        rule["id"], latest.custom_rules[0].generation, latest.activation_epoch
    )
    assert not c.is_current(rule["id"], 0, 0)


@pytest.mark.parametrize("invalidate", ["close", "remove"])
def test_test_rechecks_current_before_first_effect(harness, invalidate):
    rule = _add(harness.controller)

    def characters():
        if invalidate == "close":
            c.close_runtime()
        else:
            c.remove(rule["id"])
        return ("Alice",)

    c = AlertsController(
        harness.document, ports=replace(harness.ports, preview_characters=characters)
    )
    _assert_refused(c.test(rule["id"], _draft(rule, sound="obey")))
    assert harness.sounds == harness.raised == []


def test_close_after_admitted_sound_refuses_pending_visuals(harness):
    rule = _add(harness.controller)

    def sound(sound_id, volume):
        harness.sounds.append((sound_id, volume))
        c.close_runtime()

    c = AlertsController(
        harness.document, ports=replace(harness.ports, play_sound=sound)
    )
    result = c.test(rule["id"], _draft(rule, sound="obey"))
    assert result["applied"] and not result["persisted"]
    assert result["error"]
    assert harness.sounds == [("obey", 100)]
    assert harness.raised == []


def test_close_between_characters_refuses_remaining_rings(harness):
    rule = _add(harness.controller)

    def raise_alert(character, event, spec):
        harness.raised.append((character, event, spec))
        c.close_runtime()

    c = AlertsController(
        harness.document, ports=replace(harness.ports, raise_alert=raise_alert)
    )
    result = c.test(rule["id"], _draft(rule))
    assert result["applied"] and not result["persisted"]
    assert [entry[0] for entry in harness.raised] == ["Alice"]


def test_state_projects_current_health_and_retains_degradation_obligation(harness):
    c = harness.controller
    rule = _activate(harness)
    initial = c.runtime_snapshot()
    revision, epoch = initial.rules_revision, initial.activation_epoch
    harness.health = CustomMatcherHealth("active", revision, epoch)
    assert c.state()["matcher"] == {"state": "active", "detail": None}
    assert c.state()["revision"] == revision
    # A committed edit is not evidence the new matcher was ever invoked.
    c.edit(rule["id"], _draft(rule, name="Changed"))
    assert c.state()["matcher"] == {"state": "waiting", "detail": None}
    harness.health = CustomMatcherHealth("degraded", revision, epoch, "matcher_error")
    assert c.state()["matcher"] == {"state": "degraded", "detail": "matcher_error"}
    c.set_enabled(rule["id"], False)
    assert c.state()["matcher"] == {"state": "inactive", "detail": None}
    assert harness.health.state == "degraded"
    c.set_enabled(rule["id"], True)
    assert c.state()["matcher"] == {"state": "degraded", "detail": "matcher_error"}
    current = c.runtime_snapshot()
    harness.health = CustomMatcherHealth(
        "active", current.rules_revision, current.activation_epoch
    )
    assert c.state()["matcher"] == {"state": "active", "detail": None}


@pytest.mark.parametrize("state", ["inactive", "waiting", "active", "degraded"])
def test_committed_inactivity_outranks_retained_health(harness, state):
    harness.health = CustomMatcherHealth(state, detail="retained")
    assert harness.controller.state()["matcher"] == {
        "state": "inactive",
        "detail": None,
    }


def test_old_activation_and_absent_invocation_show_waiting(harness):
    c = harness.controller
    _activate(harness)
    initial = c.runtime_snapshot()
    harness.health = CustomMatcherHealth(
        "active", initial.rules_revision, initial.activation_epoch
    )
    for enabled in (False, True):
        with settings.update(harness.document, harness.path):
            harness.document["preview"]["alerts"]["enabled"] = enabled
    assert c.state()["matcher"] == {"state": "waiting", "detail": None}
    harness.health = CustomMatcherHealth("inactive")
    assert c.state()["matcher"] == {"state": "waiting", "detail": None}


def test_state_returns_detached_fields_and_does_not_revise_on_health_reads(harness):
    c = harness.controller
    rule = _add(c)
    before = c.runtime_snapshot()
    state = c.state()
    assert set(state) == {
        "revision",
        "rules",
        "limit",
        "previews_enabled",
        "alerts_enabled",
        "reader",
        "matcher",
    }
    assert state["previews_enabled"] is state["alerts_enabled"] is False
    assert state["reader"] == harness.reader
    state["rules"][0]["name"] = "Not authority"
    state["reader"]["characters"].clear()
    assert c.state()["rules"] == [rule]
    assert c.state()["reader"]["characters"] == ["Alice", "Bob"]
    assert c.runtime_snapshot() is before


@pytest.mark.parametrize(
    "changes",
    [
        {"search": "ab"},
        {"search": "<b></b>"},
        {"color": "red"},
        {"name": ""},
        {"enabled": 1},
        {"sound": "alarm"},
        {"cooldown_s": True},
    ],
)
def test_invalid_edit_is_refused_without_changing_committed_authority(
    controller, changes
):
    rule = _add(controller)
    before = controller.runtime_snapshot()
    _assert_refused(controller.edit(rule["id"], _draft(rule, **changes)))
    assert controller.runtime_snapshot() is before


@pytest.mark.parametrize("method", ["edit", "set_enabled", "remove"])
def test_identity_lookup_is_inside_the_serialized_transaction(harness, method):
    rule = _add(harness.controller)

    def update_after_remove():
        with settings.update(harness.document, harness.path):
            harness.document["preview"]["alerts"]["custom_rules"].clear()
        return settings.update(harness.document, harness.path)

    c = AlertsController(
        harness.document,
        ports=replace(harness.ports, update_settings=update_after_remove),
    )
    args = {"edit": (_draft(rule),), "set_enabled": (False,), "remove": ()}
    result = getattr(c, method)(rule["id"], *args[method])
    _assert_refused(result)
    assert result["state"]["rules"] == []


def test_noop_comparison_is_inside_transaction(harness):
    rule = _add(harness.controller)

    def update_after_edit():
        with settings.update(harness.document, harness.path):
            harness.document["preview"]["alerts"]["custom_rules"][0]["name"] = (
                "Other writer"
            )
        return settings.update(harness.document, harness.path)

    c = AlertsController(
        harness.document,
        ports=replace(harness.ports, update_settings=update_after_edit),
    )
    result = c.edit(rule["id"], _draft(rule))
    assert result["applied"] and result["persisted"]
    assert result["state"]["rules"] == [rule]
    assert settings.load(harness.path)["preview"]["alerts"]["custom_rules"] == [rule]


def test_controller_shares_committed_reader_and_starts_no_thread(harness, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("controller must remain thread-free")

    monkeypatch.setattr(threading.Thread, "start", forbidden)
    c = AlertsController(harness.document, ports=harness.ports)
    reader = settings.committed_preview(harness.document)
    assert c.runtime_snapshot() is reader.alerts_snapshot()
    rule = _add(c)
    assert (
        c.runtime_snapshot()
        is reader.alerts_snapshot()
        is harness.controller.runtime_snapshot()
    )
    assert c.test(rule["id"], _draft(rule))["applied"]
    assert not any("window" in name for name in vars(c))
    assert not any(
        type(value).__module__.startswith("wingman.ui") for value in vars(c).values()
    )
    c.close_runtime()


def test_controller_import_does_not_load_ui_or_native_window_modules():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from wingman.alerts.controller import AlertsController; "
            "import sys; assert not any(name == 'wingman.ui' or name.startswith('wingman.ui.') "
            "or name in {'webview', 'pystray'} for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_mutation_reply_can_include_a_later_legitimate_revision(harness):
    @contextmanager
    def update_then_commit():
        with settings.update(harness.document, harness.path) as document:
            yield document
        with settings.update(harness.document, harness.path):
            harness.document["preview"]["alerts"]["custom_rules"].append(
                {"id": "later"}
            )

    c = AlertsController(
        harness.document,
        ports=replace(harness.ports, update_settings=update_then_commit),
    )
    result = c.add()
    assert result["applied"] and result["persisted"]
    assert [row["id"] for row in result["state"]["rules"]] == [
        result["rule_id"],
        "later",
    ]
    assert result["state"]["revision"] == c.runtime_snapshot().rules_revision == 3


def test_test_reads_committed_volume_while_another_writer_is_blocked(
    harness, monkeypatch
):
    c = harness.controller
    rule = _add(c)
    with settings.update(harness.document, harness.path):
        harness.document["preview"]["alerts"]["volume"] = 25
    entered, release = Event(), Event()
    save = settings._save_locked

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        save(*args, **kwargs)

    def write():
        with settings.update(harness.document, harness.path):
            harness.document["preview"]["alerts"]["volume"] = 99

    monkeypatch.setattr(settings, "_save_locked", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(write)
        try:
            assert entered.wait(5)
            result = pool.submit(c.test, rule["id"], _draft(rule, sound="obey")).result(
                timeout=2
            )
            assert result["applied"] and not result["persisted"]
            assert harness.sounds == [("obey", 25)]
        finally:
            release.set()
        pending.result(timeout=5)
    assert c.runtime_snapshot().volume == 99
