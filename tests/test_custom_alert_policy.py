"""Custom policy authority, batch arbitration, and stale-delivery boundaries."""

from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from tests.test_preview_host import alert_mailbox as alert_mailbox
from tests.test_telemetry_coordinator import _source_id
from wingman import settings
from wingman.alerts.controller import AlertsController, AlertsPorts
from wingman.alerts.custom import CustomRule
from wingman.alerts.service import AlertPolicy
from wingman.telemetry.coordinator import AlertEvent
from wingman.telemetry.model import CustomMatch, CustomMatcherHealth


def _rule(rule_id, **changes):
    return asdict(
        replace(
            CustomRule(rule_id, search="fleet invite", enabled=True, sound="obey"),
            **changes,
        )
    )


@pytest.fixture
def runtime(tmp_path):
    def make(*, rules=None, focused=None, **alerts):
        document = settings.load(tmp_path / "settings.json")
        document["preview"] = settings.validated_preview(
            {
                "enabled": True,
                "alerts": {
                    "enabled": True,
                    "persist_until_selected": True,
                    "custom_rules": [_rule("r1")] if rules is None else rules,
                    **alerts,
                },
            }
        )
        h = SimpleNamespace(
            document=document, sounds=[], visuals=[], focus=focused, focus_reads=0
        )
        h.update = lambda: settings.update(document, tmp_path / "settings.json")
        h.controller = AlertsController(
            document,
            ports=AlertsPorts(
                update_settings=h.update,
                reader_state=dict,
                matcher_health=lambda: CustomMatcherHealth("waiting"),
                preview_characters=lambda: ("Alice",),
                preview_available=lambda: True,
                raise_alert=lambda *args: h.visuals.append(args),
                play_sound=lambda *args: h.sounds.append(args),
            ),
        )

        def focus():
            h.focus_reads += 1
            return h.focus

        h.policy = AlertPolicy(
            lambda: document["preview"]["alerts"],
            lambda *args: h.sounds.append(args),
            focus,
            lambda *args: h.visuals.append(args),
            runtime_snapshot=h.controller.runtime_snapshot,
            custom_current=h.controller.is_current,
        )
        return h

    return make


def _match(h, character="Alice", index=0):
    snapshot = h.controller.runtime_snapshot()
    row = snapshot.custom_rules[index]
    return CustomMatch(
        character,
        1,
        _source_id(),
        row.rule.id,
        row.generation,
        snapshot.activation_epoch,
    )


def _edit(h, index=0, **changes):
    rule = h.controller.runtime_snapshot().custom_rules[index].rule
    result = h.controller.edit(rule.id, {**asdict(rule), **changes})
    assert result["applied"] and result["persisted"]


@pytest.mark.parametrize("characters", [("Alice", "Bob"), ("Bob", "Alice")])
@pytest.mark.parametrize("builtin", ["warp_scramble", "combat", "decloak"])
def test_every_builtin_outranks_custom_across_characters(runtime, characters, builtin):
    h = runtime(rules=[_rule("r1", sound="obey")])
    with h.update() as document:
        document["preview"]["alerts"]["events"][builtin]["sound"] = "system-fault"
    builtin_char, custom_char = characters
    out = h.policy.handle(
        [AlertEvent(builtin_char, builtin, "Player")],
        10.0,
        custom_matches=(_match(h, custom_char),),
    )
    assert h.sounds == [("system-fault", 100)]
    assert [(char, kind) for char, kind, _ in out] == [
        (builtin_char, builtin),
        (custom_char, "custom"),
    ]
    assert h.focus_reads == 1


@pytest.mark.parametrize("same_position", [False, True])
def test_custom_ties_use_position_then_id_not_pending_map_order(runtime, same_position):
    h = runtime(rules=[_rule("z", sound="obey"), _rule("a", sound="system-fault")])
    if same_position:
        # Equal ranks normally share a rule/sound; force a presentation-position
        # tie so the stable-ID fallback is independently observable.
        snapshot = h.controller.runtime_snapshot()
        rows = tuple(replace(row, position=0) for row in snapshot.custom_rules)
        h.policy._runtime_snapshot = lambda: replace(
            snapshot, custom_rules=rows, executable=rows
        )
    pending = {"a": _match(h, index=1), "z": _match(h)}
    h.policy.handle([], 10.0, custom_matches=tuple(pending.values()))
    assert h.sounds == [("system-fault" if same_position else "obey", 100)]
    assert len(h.visuals) == 2
    # Losing the sound competition still consumes visual cooldown.
    assert h.policy.handle([], 10.1, custom_matches=tuple(pending.values())) == []


@pytest.mark.parametrize(
    "focused,persist,want_persist,want_sound",
    [
        ("Alice", True, False, False),
        (None, True, True, True),
        (None, False, False, True),
    ],
)
def test_custom_style_focus_and_global_persistence(
    runtime, focused, persist, want_persist, want_sound
):
    h = runtime(focused=focused, persist_until_selected=persist, volume=35)
    match = _match(h)
    out = h.policy.handle([], 10.0, custom_matches=(match,))
    assert out == [("Alice", "custom", "#ff8c42")]
    assert h.sounds == ([("obey", 35)] if want_sound else [])
    assert h.visuals == [
        (
            "Alice",
            "custom",
            {
                "enabled": True,
                "color": "#ff8c42",
                "sound": "obey",
                "cooldown_s": 8,
                "pulses": 3,
                "flash_rate": "normal",
                "persist_until_selected": want_persist,
                "custom_rule_id": "r1",
                "custom_generation": match.generation,
                "custom_activation_epoch": match.activation_epoch,
            },
        )
    ]
    assert h.focus_reads == 1


@pytest.mark.parametrize(
    "reason", ["none", "focused", "filtered", "cooldown", "disabled"]
)
def test_inaudible_builtin_does_not_silence_custom(runtime, reason):
    h = runtime(focused="Bob" if reason == "focused" else None)
    with h.update() as document:
        spec = document["preview"]["alerts"]["events"]["warp_scramble"]
        spec["sound"] = "none" if reason == "none" else "system-fault"
        spec["enabled"] = reason != "disabled"
        document["preview"]["alerts"]["pve_filter"] = True
    event = AlertEvent(
        "Bob",
        "warp_scramble",
        "Sleepless Sentinel" if reason == "filtered" else "Player",
    )
    if reason == "cooldown":
        h.policy.handle([event], 9.0)
        h.sounds.clear()
    h.policy.handle([event], 10.0, custom_matches=(_match(h),))
    assert h.sounds == [("obey", 100)]


def test_none_custom_does_not_mask_audible_sibling(runtime):
    h = runtime(rules=[_rule("r1", sound="none"), _rule("r2", sound="system-fault")])
    h.policy.handle([], 10.0, custom_matches=(_match(h), _match(h, index=1)))
    assert len(h.visuals) == 2
    assert h.sounds == [("system-fault", 100)]


def test_muted_custom_still_flashes_and_consumes_visual_cooldown(runtime):
    h = runtime(volume=0)
    match = _match(h)
    assert h.policy.handle([], 10.0, custom_matches=(match,)) == [
        ("Alice", "custom", "#ff8c42")
    ]
    assert h.sounds == []
    assert h.policy.handle([], 10.1, custom_matches=(match,)) == []


def test_focused_custom_does_not_mask_another_characters_audible_rule(runtime):
    h = runtime(focused="Alice", rules=[_rule("r1"), _rule("r2", sound="system-fault")])
    h.policy.handle([], 10.0, custom_matches=(_match(h), _match(h, "Bob", index=1)))
    assert h.sounds == [("system-fault", 100)]
    assert [spec["persist_until_selected"] for _, _, spec in h.visuals] == [False, True]


def test_custom_bypasses_pve_filter(runtime):
    h = runtime(rules=[_rule("r1", search="Sleepless Sentinel")], pve_filter=True)
    out = h.policy.handle(
        [AlertEvent("Alice", "combat", "Sleepless Sentinel")],
        10.0,
        custom_matches=(_match(h),),
    )
    assert out == [("Alice", "custom", "#ff8c42")]
    assert h.sounds == [("obey", 100)]


@pytest.mark.parametrize(
    "gate",
    [
        "preview",
        "alerts",
        "disabled",
        "blank",
        "removed",
        "closed",
        "old_epoch",
        "zero_tokens",
    ],
)
def test_inactive_or_stale_custom_work_burns_no_cooldown(runtime, gate):
    h = runtime()
    match = _match(h)
    if gate in {"preview", "alerts", "old_epoch"}:
        with h.update() as document:
            target = (
                document["preview"]
                if gate == "preview"
                else document["preview"]["alerts"]
            )
            target["enabled"] = False
        if gate == "old_epoch":
            with h.update() as document:
                document["preview"]["alerts"]["enabled"] = True
    elif gate == "disabled":
        assert h.controller.set_enabled("r1", False)["applied"]
    elif gate == "blank":
        _edit(h, search="")
    elif gate == "removed":
        assert h.controller.remove("r1")["applied"]
    elif gate == "closed":
        h.controller.close_runtime()
    else:
        match = replace(match, generation=0, activation_epoch=0)
    assert h.policy.handle([], 10.0, custom_matches=(match,)) == []
    assert h.sounds == h.visuals == []
    assert h.policy._custom_cooldowns == {}


@pytest.mark.parametrize("missing", ["snapshot", "current", "both"])
def test_custom_requires_both_authority_providers_but_builtins_remain_compatible(
    runtime, missing
):
    h = runtime()
    if missing in {"snapshot", "both"}:
        h.policy._runtime_snapshot = None
    if missing in {"current", "both"}:
        h.policy._custom_current = None
    out = h.policy.handle(
        [AlertEvent("Bob", "decloak", "")], 10.0, custom_matches=(_match(h),)
    )
    assert [(char, kind) for char, kind, _ in out] == [("Bob", "decloak")]


def test_snapshot_revalidation_is_required_even_when_open_runtime_predicate_accepts(
    runtime,
):
    h = runtime()
    match = _match(h)
    h.policy._custom_current = lambda *tokens: True

    def deliver(*args):
        h.visuals.append(args)
        _edit(h, search="edited query")

    h.policy._on_alert = deliver
    h.policy.handle([AlertEvent("Bob", "decloak", "")], 10.0, custom_matches=(match,))
    assert [(char, kind) for char, kind, _ in h.visuals] == [("Bob", "decloak")]
    assert h.policy._custom_cooldowns == {}


def test_custom_cooldown_exact_boundary_and_character_independence(runtime):
    h = runtime()
    alice, bob = _match(h), _match(h, "Bob")
    assert h.policy.handle([], 10.0, custom_matches=(alice,))
    assert h.policy.handle([], 17.999, custom_matches=(alice,)) == []
    assert h.policy.handle([], 17.999, custom_matches=(bob,))
    assert h.policy.handle([], 18.0, custom_matches=(alice,))
    assert len(h.sounds) == 3


def test_edit_invalidates_own_cooldown_and_prunes_history_not_sibling(runtime):
    h = runtime(rules=[_rule("r1"), _rule("r2")])
    old, sibling = _match(h), _match(h, index=1)
    h.policy.handle([], 10.0, custom_matches=(old, sibling))
    for i in range(5):
        _edit(h, name=f"Edited {i}")
        new = _match(h)
        assert h.policy.handle([], 11.0, custom_matches=(old, new, sibling)) == [
            ("Alice", "custom", "#ff8c42")
        ]
        assert len(h.policy._custom_cooldowns) == 2
    assert h.controller.remove("r1")["applied"]
    h.policy.handle([], 11.0)
    assert h.policy._custom_cooldowns == {("Alice", "r2", sibling.generation): 10.0}


def test_same_generation_test_does_not_consume_or_reset_runtime_cooldown(runtime):
    h = runtime()
    match = _match(h)
    h.policy.handle([], 10.0, custom_matches=(match,))
    result = h.controller.test(
        "r1", {"color": "#abcdef", "sound": "obey", "cooldown_s": 8}
    )
    assert result["applied"] and not result["persisted"]
    assert h.visuals[-1][2]["custom_test"] is True
    assert h.visuals[-1][2]["persist_until_selected"] is False
    assert h.policy.handle([], 10.1, custom_matches=(match,)) == []
    assert h.policy.handle([], 18.0, custom_matches=(match,))


def test_config_and_focus_captured_once_from_committed_runtime(runtime):
    h = runtime(focused="Alice", volume=35)
    # The legacy callable must not become a second authority alongside the snapshot.
    h.policy._config = lambda: pytest.fail("read a second configuration")
    with h.update() as document:
        document["preview"]["alerts"]["events"]["combat"]["sound"] = "system-fault"

    def events():
        yield AlertEvent("Alice", "combat", "Player")
        with h.update() as document:
            document["preview"]["alerts"]["volume"] = 5
            document["preview"]["alerts"]["persist_until_selected"] = False
        h.focus = "Bob"
        yield AlertEvent("Bob", "combat", "Player")

    h.policy.handle(events(), 10.0, custom_matches=(_match(h, "Carol"),))
    assert h.sounds == [("system-fault", 35)]
    assert [spec["persist_until_selected"] for _, _, spec in h.visuals] == [
        False,
        True,
        True,
    ]
    assert h.focus_reads == 1


@pytest.mark.parametrize("boundary", ["planning", "delivery"])
@pytest.mark.parametrize("change", ["edit", "remove", "disable", "off_on", "close"])
def test_custom_revalidated_after_planning_and_before_host_admission(
    runtime, boundary, change
):
    h = runtime()
    match = _match(h)

    def mutate():
        if change == "edit":
            _edit(h, search="edited query")
        elif change == "remove":
            assert h.controller.remove("r1")["applied"]
        elif change == "disable":
            assert h.controller.set_enabled("r1", False)["applied"]
        elif change == "close":
            h.controller.close_runtime()
        else:
            for enabled in (False, True):
                with h.update() as document:
                    document["preview"]["alerts"]["enabled"] = enabled

    def events():
        yield AlertEvent("Bob", "decloak", "")
        if boundary == "planning":
            mutate()

    def deliver(*args):
        h.visuals.append(args)
        if boundary == "delivery":
            mutate()

    h.policy._on_alert = deliver
    out = h.policy.handle(events(), 10.0, custom_matches=(match,))
    assert [(char, kind) for char, kind, _ in out] == [("Bob", "decloak")]
    assert len(h.visuals) == 1
    assert h.policy._custom_cooldowns == {}


@pytest.mark.parametrize("change", ["edit", "remove", "close"])
def test_stale_sound_winner_is_dropped_and_valid_sibling_reselected(runtime, change):
    h = runtime(rules=[_rule("r1"), _rule("r2", sound="system-fault")])
    matches = (_match(h), _match(h, index=1))

    def deliver(*args):
        h.visuals.append(args)
        if len(h.visuals) == 2:
            if change == "edit":
                _edit(h, name="Changed")
            elif change == "remove":
                assert h.controller.remove("r1")["applied"]
            else:
                h.controller.close_runtime()

    h.policy._on_alert = deliver
    h.policy.handle([], 10.0, custom_matches=matches)
    assert len(h.visuals) == 2  # Already-admitted visuals are not retracted.
    assert h.sounds == ([] if change == "close" else [("system-fault", 100)])


@pytest.mark.parametrize("change", ["none", "edit", "close", "no_preview"])
def test_policy_metadata_reaches_real_host_and_is_revalidated_at_arm(
    runtime, alert_mailbox, change
):
    h = runtime()
    host, _, armed = alert_mailbox(custom_alert_current=h.controller.is_current)
    h.policy._on_alert = host.raise_alert
    if change == "no_preview":
        host._windows.clear()
    h.policy.handle([], 10.0, custom_matches=(_match(h),))
    pending = host._drain_alerts()
    if change == "edit":
        _edit(h, search="edited query")
    elif change == "close":
        h.controller.close_runtime()
    host._apply_alerts(None, pending)
    assert bool(armed) is (change == "none")
    assert h.sounds == [("obey", 100)]  # No retrospective audio cancellation.


def test_reset_clears_custom_cooldown_for_existing_runtime_generation(runtime):
    h = runtime()
    match = _match(h)
    h.policy.handle([], 10.0, custom_matches=(match,))
    h.policy.reset()
    assert h.policy.handle([], 10.1, custom_matches=(match,))
