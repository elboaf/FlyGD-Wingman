"""Custom settings rebuild safely and publish only committed immutable authority."""

import copy
import json
from dataclasses import FrozenInstanceError, asdict

import pytest

from wingman import settings
from wingman.alerts.custom import CustomRule, RuleValidationError


def _rule(rule_id="r1", **values):
    return {
        "id": rule_id,
        "name": "Fleet",
        "search": "fleet invite",
        "enabled": True,
        **values,
    }


def _active_document():
    document = settings.load()
    document["preview"]["enabled"] = True
    document["preview"]["alerts"].update(
        enabled=True, custom_rules=[_rule(), _rule("r2")]
    )
    return document


def test_old_settings_gain_an_empty_custom_list_without_version_change():
    old = settings._alerts_defaults()
    version = old["defaults_version"]
    old.pop("custom_rules", None)
    result = settings.validated_alerts(old)
    assert result["custom_rules"] == []
    assert result["defaults_version"] == version


@pytest.mark.parametrize("raw", [None, {}, "nope", 3, (), []])
def test_missing_or_malformed_rule_list_is_empty(raw):
    assert settings.validated_custom_rules(raw) == []


def test_defaults_are_disabled_and_lists_are_independent():
    first, second = settings._alerts_defaults(), settings._alerts_defaults()
    first["custom_rules"].append({"id": "r1"})
    assert second["custom_rules"] == []
    assert settings.validated_custom_rules(first["custom_rules"]) == [
        {
            "id": "r1",
            "name": "Custom alert",
            "search": "",
            "enabled": False,
            "color": "#ff8c42",
            "sound": "none",
            "cooldown_s": 8,
        }
    ]


def test_rebuild_is_detached_strips_unknown_fields_and_keeps_display_search():
    raw = [
        _rule(
            name="  Fleet  ",
            search="  Fleet <b>Invite</b>  ",
            generation=9,
            pulses=16,
            flash_rate="fast",
            extra={"private": []},
        )
    ]
    before = copy.deepcopy(raw)
    result = settings.validated_custom_rules(raw)
    assert result == [
        {
            "id": "r1",
            "name": "Fleet",
            "search": "Fleet <b>Invite</b>",
            "enabled": True,
            "color": "#ff8c42",
            "sound": "none",
            "cooldown_s": 8,
        }
    ]
    result[0]["name"] = "Detached"
    assert raw == before


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        [],
        "rule",
        {},
        _rule(id="bad.id"),
        _rule(id="é"),
        _rule(id="x" * 65),
        _rule(name=""),
        _rule(search="ab"),
        _rule(search="x" * 201),
        _rule(enabled=1),
    ],
)
def test_bad_sibling_does_not_claim_id_or_remove_good_siblings(invalid):
    result = settings.validated_custom_rules([invalid, _rule(), _rule("r2")])
    assert [row["id"] for row in result] == ["r1", "r2"]


def test_first_valid_id_wins_duplicate_names_survive_and_cap_counts_accepted_rows():
    raw = [_rule(search="ab"), _rule(name="First"), _rule(name="Duplicate")]
    raw += [None, *[_rule(f"r{i}") for i in range(2, 12)]]
    result = settings.validated_custom_rules(raw)
    assert [row["id"] for row in result] == [f"r{i}" for i in range(1, 9)]
    assert result[0]["name"] == "First"
    assert all(row["name"] == "Fleet" for row in result[1:])


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("color", "red", "#ff8c42"),
        ("color", "#abcdef\n", "#ff8c42"),
        ("color", None, "#ff8c42"),
        ("color", "#aBcD09", "#aBcD09"),
        ("sound", "missing", "none"),
        ("sound", None, "none"),
        ("sound", "alarm", "system-fault"),
        ("sound", "ring", "obey"),
        ("sound", "notify", "sly"),
        ("cooldown_s", True, 8),
        ("cooldown_s", 8.0, 8),
        ("cooldown_s", -1, 0),
        ("cooldown_s", 121, 120),
    ],
)
def test_persisted_styles_use_existing_fallbacks_with_complete_hex_match(
    key, value, expected
):
    assert settings.validated_custom_rules([_rule(**{key: value})])[0][key] == expected


@pytest.mark.parametrize(
    "key,value",
    [
        ("color", "#abcdef\n"),
        ("color", "red"),
        ("color", None),
        ("sound", "missing"),
        ("sound", "alarm"),
        ("sound", None),
        ("cooldown_s", True),
        ("cooldown_s", 8.0),
        ("cooldown_s", -1),
        ("cooldown_s", 121),
        ("enabled", 1),
        ("search", "ab"),
        ("name", ""),
    ],
)
def test_interactive_invalid_values_refuse_instead_of_silently_normalizing(key, value):
    with pytest.raises(RuleValidationError):
        settings.validate_custom_rule_edit("r1", _rule(**{key: value}))


@pytest.mark.parametrize("draft", [None, [], "draft", 42])
def test_interactive_non_objects_refuse(draft):
    with pytest.raises(RuleValidationError):
        settings.validate_custom_rule_edit("r1", draft)


def test_interactive_adapter_owns_identity_and_returns_domain_rule_without_mutation():
    draft = _rule(
        "ignored",
        name="  Fleet  ",
        search="  FLEET invite  ",
        color="#aBcD09",
        sound="obey",
        cooldown_s=120,
        unknown="ignored",
    )
    before = copy.deepcopy(draft)
    result = settings.validate_custom_rule_edit("chosen", draft)
    assert result == CustomRule(
        "chosen", "Fleet", "FLEET invite", True, "#aBcD09", "obey", 120
    )
    assert draft == before
    with pytest.raises(RuleValidationError):
        settings.validate_custom_rule_edit("bad.id", draft)


def test_blank_search_forces_disabled_in_both_load_and_edit_modes():
    draft = _rule(search="  ", enabled=True)
    loaded = settings.validated_custom_rules([draft])[0]
    edited = settings.validate_custom_rule_edit("r1", draft)
    assert loaded["search"] == edited.search == ""
    assert loaded["enabled"] is edited.enabled is False


def test_load_update_roundtrip_preserves_rules_without_runtime_fields_or_version_bump(
    tmp_path,
):
    path = tmp_path / "settings.json"
    document = _active_document()
    versions = (
        document["preview"]["defaults_version"],
        document["preview"]["alerts"]["defaults_version"],
    )
    with settings.update(document, path):
        pass
    assert settings.load(path) == document == json.loads(path.read_text())
    row = document["preview"]["alerts"]["custom_rules"][0]
    assert row == asdict(CustomRule("r1", "Fleet", "fleet invite", True))
    assert versions == (
        document["preview"]["defaults_version"],
        document["preview"]["alerts"]["defaults_version"],
    )


def test_failed_write_cannot_publish_a_rule_or_generation(monkeypatch, tmp_path):
    document = settings.load(tmp_path / "settings.json")
    reader = settings.committed_preview(document)
    before = reader.alerts_snapshot()

    def fail_save(data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(settings, "_save_locked", fail_save)
    with pytest.raises(OSError), settings.update(document):
        document["preview"]["alerts"]["custom_rules"] = [_rule()]
    assert reader.alerts_snapshot() is before


@pytest.mark.parametrize(
    "preview",
    [
        {},
        {"enabled": "bad", "alerts": None},
        {
            "opacity": 235,
            "defaults_version": 1,
            "alerts": {"custom_rules": [_rule(color="red")]},
        },
    ],
)
def test_initial_preview_is_not_renormalized_but_alert_projection_is(preview):
    document = {"preview": copy.deepcopy(preview)}
    reader = settings.committed_preview(document)
    assert document == {"preview": preview}
    assert reader.snapshot() == preview
    snapshot = reader.alerts_snapshot()
    assert snapshot.preview_enabled is False
    assert snapshot.alerts_enabled is False
    assert snapshot.volume == 100
    assert snapshot.executable == ()
    assert len(snapshot.builtins) == 3
    if snapshot.custom_rules:
        assert snapshot.custom_rules[0].rule.color == "#ff8c42"
    fallback = {"nested": []}
    reader.get("missing", fallback)["nested"].append(1)
    assert fallback == {"nested": []}


def test_alert_readers_never_copy_validate_or_acquire_settings_lock(monkeypatch):
    reader = settings.committed_preview(_active_document())
    snapshot = reader.alerts_snapshot()

    def forbidden(*args, **kwargs):
        pytest.fail("hotpath must read the immutable reference only")

    class ForbiddenLock:
        __enter__ = forbidden
        __exit__ = forbidden

    monkeypatch.setattr(settings, "_SAVE_LOCK", ForbiddenLock())
    monkeypatch.setattr(settings.copy, "deepcopy", forbidden)
    monkeypatch.setattr(settings, "validated_preview", forbidden)
    monkeypatch.setattr(settings, "validated_alerts", forbidden)
    assert reader.alerts_snapshot() is snapshot


def test_nested_alert_values_are_immutable_and_detached_from_all_mutable_readers():
    document = _active_document()
    reader = settings.committed_preview(document)
    snapshot = reader.alerts_snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.volume = 0
    with pytest.raises(FrozenInstanceError):
        snapshot.custom_rules[0].generation = 99
    with pytest.raises(FrozenInstanceError):
        snapshot.custom_rules[0].rule.name = "escaped"
    with pytest.raises(FrozenInstanceError):
        snapshot.builtins[0].sound = "none"
    with pytest.raises(TypeError):
        snapshot.custom_rules[0] = snapshot.custom_rules[1]
    for alerts in (
        document["preview"]["alerts"],
        reader.get("alerts"),
        reader.snapshot()["alerts"],
    ):
        alerts["custom_rules"][0]["name"] = "escaped"
        alerts["events"]["combat"]["sound"] = "none"
    assert snapshot.custom_rules[0].rule.name == "Fleet"
    assert snapshot.builtins[0].sound == "system-fault"
    assert reader.get("alerts")["custom_rules"][0]["name"] == "Fleet"


def test_rule_tokens_follow_canonical_edits_not_order_shifts_or_unrelated_writes(
    tmp_path,
):
    document = _active_document()
    reader = settings.committed_preview(document)
    path = tmp_path / "settings.json"
    initial = reader.alerts_snapshot()
    assert initial.rules_revision == initial.activation_epoch == 1
    with settings.update(document, path):
        document["category"] = "22"
        document["preview"]["alerts"]["custom_rules"][0]["name"] = "  Fleet  "
    noop = reader.alerts_snapshot()
    assert noop == initial
    for field, value in [
        ("name", "New name"),
        ("search", "new search"),
        ("color", "#abcdef"),
        ("sound", "obey"),
        ("cooldown_s", 9),
        ("enabled", False),
    ]:
        before = reader.alerts_snapshot()
        with settings.update(document, path):
            document["preview"]["alerts"]["custom_rules"][0][field] = value
        after = reader.alerts_snapshot()
        assert after.rules_revision == before.rules_revision + 1
        assert after.custom_rules[0].generation == after.rules_revision
        assert after.custom_rules[1].generation == 1
        assert after.activation_epoch == 1  # r2 remains executable
    generation = after.custom_rules[0].generation
    with settings.update(document, path):
        document["preview"]["alerts"]["custom_rules"].reverse()
    reordered = reader.alerts_snapshot()
    assert [
        (row.rule.id, row.generation, row.position) for row in reordered.custom_rules
    ] == [("r2", 1, 0), ("r1", generation, 1)]
    assert reordered.rules_revision == after.rules_revision + 1
    with settings.update(document, path):
        document["preview"]["alerts"]["custom_rules"].pop(1)
    deleted = reader.alerts_snapshot()
    assert len(deleted.custom_rules) == 1
    assert deleted.custom_rules[0].generation == 1
    assert deleted.rules_revision == reordered.rules_revision + 1
    with settings.update(document, path):
        document["preview"]["alerts"]["custom_rules"].append(_rule())
    assert reader.alerts_snapshot().custom_rules[1].generation > generation


def test_activation_epoch_changes_only_when_effective_execution_toggles(tmp_path):
    document = _active_document()
    reader = settings.committed_preview(document)
    path = tmp_path / "settings.json"
    for preview_on, alerts_on, rules, epoch, active in [
        (False, True, [_rule()], 2, False),
        (False, False, [_rule()], 2, False),
        (True, False, [_rule()], 2, False),
        (True, True, [_rule()], 3, True),
        (True, True, [_rule(enabled=False)], 4, False),
        (True, True, [_rule(search="")], 4, False),
        (True, True, [], 4, False),
        (True, True, [_rule()], 5, True),
    ]:
        with settings.update(document, path):
            document["preview"]["enabled"] = preview_on
            document["preview"]["alerts"].update(enabled=alerts_on, custom_rules=rules)
        snapshot = reader.alerts_snapshot()
        assert snapshot.activation_epoch == epoch
        assert bool(snapshot.executable) is active
