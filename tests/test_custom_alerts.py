"""Pure custom-alert boundaries, independent of the built-in ownership parser."""

from copy import deepcopy
from dataclasses import asdict

import pytest

from wingman import settings
from wingman.alerts import custom


def test_visible_literal_matching_preserves_categories_and_casefolds():
    from wingman.alerts.custom import normalize_visible, validate_search

    line = "[ 2026.08.25 11:30:00 ] (notify) <b>Straße</b> &amp;  fleet"
    assert normalize_visible(line) == "(notify) strasse & fleet"
    assert validate_search("STRASSE", allow_blank=False) == ("STRASSE", "strasse")
    assert normalize_visible("[Fleet] war<b>p</b>") == "[fleet] warp"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        (
            "[ 2026.08.25 11:30:05 ] (combat) <color=0xffffffff>"
            "<b>Warp scramble attempt</b> <font size=10>from</font> "
            "<fontsize=12>Carol Vex [BURN]</color><color=0xfff0f000> Claw</color>",
            "(combat) warp scramble attempt from carol vex [burn] claw",
        ),
        ("<b>war</b><font size=10>p</font>", "warp"),
        ("&lt;b&gt;Fleet&lt;/b&gt; &amp; &#83;traße", "<b>fleet</b> & strasse"),
        ("  (notify)\tA\nB\r\n C\u00a0  D  ", "(notify) a b c d"),
        ("STRASSE Straße \u03a3\u03c2\u03c3", "strasse strasse \u03c3\u03c3\u03c3"),
        ("[Fleet] (Combat) [2026.08.25]", "[fleet] (combat) [2026.08.25]"),
        ("prefix [ 2026.08.25 11:30:05 ]", "prefix [ 2026.08.25 11:30:05 ]"),
        ("[2026-08-25 11:30:05] (notify)", "[2026-08-25 11:30:05] (notify)"),
        ("  [2026.08.25 11:30:05] (notify)", "(notify)"),
        ("a.* [b] (c)? ^d$ \\e + f{2}|g", "a.* [b] (c)? ^d$ \\e + f{2}|g"),
    ],
)
def test_visible_normalization_is_not_the_builtin_markup_parser(text, want):
    assert custom.normalize_visible(text) == want


@pytest.mark.parametrize(
    ("search", "want"),
    [
        ("abc", ("abc", "abc")),
        ("A" * 200, ("A" * 200, "a" * 200)),
        ("ß" * 100, ("ß" * 100, "ss" * 100)),
        ("  <b>WaRp</b>  fleet  ", ("<b>WaRp</b>  fleet", "warp fleet")),
        ("A\u00a0B", ("A\u00a0B", "a b")),
        ("[Fleet]", ("[Fleet]", "[fleet]")),
        ("&lt;b&gt;", ("&lt;b&gt;", "<b>")),
    ],
)
def test_search_keeps_display_text_but_bounds_the_folded_needle(search, want):
    assert custom.validate_search(search, allow_blank=False) == want


@pytest.mark.parametrize("search", ["", "  ", "\u00a0"])
def test_only_raw_blank_search_is_allowed_for_disabled_configuration(search):
    assert custom.validate_search(search, allow_blank=True) == ("", "")
    with pytest.raises(ValueError):
        custom.validate_search(search, allow_blank=False)


@pytest.mark.parametrize(
    "search",
    [
        "ab",
        "a" * 201,
        "a" * 199 + "ß",
        "ß" * 101,
        "<b></b>",
        "<b>  </b>",
        "&nbsp;",
        "[ 2026.08.25 11:30:05 ]",
        "\t",
        "abc\n",
        "abc\x00def",
        "abc\x7fdef",
        "abc\x85def",
        "abc&#9;def",
        "abc&#x0a;def",
        "abc&NewLine;def",
        "abc&#<b>9</b>;def",
        "<b title='\x00'>abc</b>",
    ],
)
@pytest.mark.parametrize("allow_blank", [False, True])
def test_search_refuses_invalid_input_instead_of_truncating(search, allow_blank):
    with pytest.raises(ValueError):
        custom.validate_search(search, allow_blank=allow_blank)


@pytest.mark.parametrize("search", [None, 3, True, b"abc", [], {}])
def test_search_refuses_non_text_without_echoing_input(search):
    with pytest.raises(ValueError):
        custom.validate_search(search, allow_blank=False)


def test_search_refusals_are_fixed_and_never_include_private_text():
    errors = []
    for search in ("PRIVATE ONE\x00", "PRIVATE TWO\x00"):
        with pytest.raises(ValueError) as exc:
            custom.validate_search(search, allow_blank=False)
        errors.append(str(exc.value))
    assert errors[0] == errors[1]
    assert "PRIVATE" not in errors[0]


def _normalize_style(raw):
    return settings._validated_alert_event(
        raw, {"color": "#ff8c42", "sound": "none", "cooldown_s": 8}
    )


def _validate(raw, *, strict=False):
    return custom.validate_rule(
        raw, normalize_style=_normalize_style, strict_style=strict
    )


def test_new_rule_defaults_are_disabled_blank_and_local_style():
    assert asdict(_validate({"id": "new-rule"})) == {
        "id": "new-rule",
        "name": "Custom alert",
        "search": "",
        "enabled": False,
        "color": "#ff8c42",
        "sound": "none",
        "cooldown_s": 8,
    }


def test_rule_canonicalizes_text_discards_unknown_keys_and_keeps_duplicate_names():
    raw = {
        "id": "Rule_1-X",
        "name": "  Same name  ",
        "search": "  <b>WaRp</b> fleet  ",
        "enabled": True,
        "color": "#ABC123",
        "sound": "obey",
        "cooldown_s": 0,
        "needle": "not authoritative",
    }
    first = _validate(raw, strict=True)
    second = _validate({**raw, "id": "sibling"}, strict=True)
    assert asdict(first) == {
        "id": "Rule_1-X",
        "name": "Same name",
        "search": "<b>WaRp</b> fleet",
        "enabled": True,
        "color": "#ABC123",
        "sound": "obey",
        "cooldown_s": 0,
    }
    assert second.name == "Same name"
    assert raw["name"] == "  Same name  "


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_cleared_search_disables_in_the_same_canonical_rule(enabled, strict):
    rule = _validate({"id": "clear", "search": "  ", "enabled": enabled}, strict=strict)
    assert rule.search == ""
    assert rule.enabled is False


@pytest.mark.parametrize("rule_id", ["a", "A_z-09", "a" * 64])
def test_rule_accepts_bounded_ascii_ids(rule_id):
    assert _validate({"id": rule_id}).id == rule_id


@pytest.mark.parametrize(
    "rule_id", [None, 1, True, "", "a" * 65, "a b", "é", "a\n", " a", "a."]
)
def test_rule_refuses_noncanonical_ids(rule_id):
    with pytest.raises(custom.RuleValidationError):
        _validate({"id": rule_id})


@pytest.mark.parametrize("name", ["X", "  Name  ", "é" * 80, "\U00010400" * 80])
def test_rule_name_uses_unicode_codepoints_without_truncation(name):
    assert _validate({"id": "name", "name": name}).name == name.strip()


@pytest.mark.parametrize(
    "name", [None, 80, False, "", "   ", "a" * 81, "\tName", "Name\x7f", "Name\x85"]
)
def test_rule_refuses_invalid_names(name):
    with pytest.raises(custom.RuleValidationError):
        _validate({"id": "name", "name": name})


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "rule",
        8,
        True,
        {},
        {"id": "rule", "enabled": 1},
        {"id": "rule", "enabled": "yes"},
        {"id": "rule", "search": "ab"},
    ],
)
def test_rule_refuses_wrong_shapes_types_and_invalid_search(raw):
    with pytest.raises(custom.RuleValidationError):
        _validate(raw)


@pytest.mark.parametrize(
    ("fields", "want"),
    [
        (
            {"color": "bad", "sound": "missing", "cooldown_s": True},
            ("#ff8c42", "none", 8),
        ),
        ({"cooldown_s": -1}, ("#ff8c42", "none", 0)),
        ({"cooldown_s": 121}, ("#ff8c42", "none", 120)),
    ],
)
def test_loaded_style_reuses_existing_fallback_and_clamp(fields, want):
    rule = _validate({"id": "style", **fields})
    assert (rule.color, rule.sound, rule.cooldown_s) == want


@pytest.mark.parametrize(
    "field,value",
    [
        ("color", "bad"),
        ("color", None),
        ("sound", "missing"),
        ("sound", None),
        ("cooldown_s", True),
        ("cooldown_s", False),
        ("cooldown_s", 8.0),
        ("cooldown_s", "8"),
        ("cooldown_s", -1),
        ("cooldown_s", 121),
    ],
)
def test_interactive_style_cannot_succeed_with_a_fallback_or_clamp(field, value):
    with pytest.raises(custom.RuleValidationError):
        _validate({"id": "style", field: value}, strict=True)


def test_rule_validation_refusals_do_not_disclose_identity_name_or_search():
    for field in ("id", "name", "search"):
        errors = []
        for private in ("PRIVATE ONE\x00", "PRIVATE TWO\x00"):
            with pytest.raises(custom.RuleValidationError) as exc:
                _validate({"id": "rule", field: private})
            errors.append(str(exc.value))
        assert errors[0] == errors[1]
        assert "PRIVATE" not in errors[0]


def _rule(rule_id, **changes):
    return {
        "id": rule_id,
        "name": "Custom alert",
        "search": "warp",
        "enabled": True,
        "color": "#ff8c42",
        "sound": "none",
        "cooldown_s": 8,
        **changes,
    }


def _preview(*rules, preview_enabled=True, alerts_enabled=True):
    # Task 2 owns settings normalization for custom fields. This fixture is
    # already canonical at the pure projection boundary, not a fake validator.
    preview = settings.validated_preview(
        {"enabled": preview_enabled, "alerts": {"enabled": alerts_enabled}}
    )
    preview["alerts"]["custom_rules"] = list(rules)
    return preview


def test_snapshot_projects_builtin_and_custom_authority_without_mutable_aliases():
    preview = _preview(_rule("active"), _rule("blank", search="", enabled=False))
    preview["alerts"].update(pve_filter=False, persist_until_selected=False, volume=37)
    snapshot = custom.prepare_alert_snapshot(preview)
    assert (snapshot.preview_enabled, snapshot.alerts_enabled) == (True, True)
    assert (snapshot.pve_filter, snapshot.persist_until_selected, snapshot.volume) == (
        False,
        False,
        37,
    )
    assert (snapshot.rules_revision, snapshot.activation_epoch) == (1, 1)
    assert [asdict(row) for row in snapshot.builtins] == [
        {
            "event": "combat",
            "enabled": True,
            "color": "#ff4d4d",
            "sound": "system-fault",
            "cooldown_s": 1,
            "pulses": 3,
            "flash_rate": "normal",
        },
        {
            "event": "warp_scramble",
            "enabled": True,
            "color": "#ffd24d",
            "sound": "obey",
            "cooldown_s": 8,
            "pulses": 3,
            "flash_rate": "normal",
        },
        {
            "event": "decloak",
            "enabled": True,
            "color": "#4dd2ff",
            "sound": "sly",
            "cooldown_s": 8,
            "pulses": 3,
            "flash_rate": "normal",
        },
    ]
    assert [
        (r.rule.id, r.generation, r.position, r.needle) for r in snapshot.custom_rules
    ] == [("active", 1, 0, "warp"), ("blank", 1, 1, "")]
    assert tuple(r.rule.id for r in snapshot.executable) == ("active",)
    original_hash = hash(snapshot)
    preview["alerts"]["events"]["combat"]["color"] = "#000000"
    preview["alerts"]["custom_rules"][0]["search"] = "edited"
    assert hash(snapshot) == original_hash
    assert snapshot.builtins[0].color == "#ff4d4d"
    assert snapshot.custom_rules[0].rule.search == "warp"


def test_unrelated_preview_and_builtin_changes_leave_rule_tokens_unchanged():
    preview = _preview(_rule("rule"))
    previous = custom.prepare_alert_snapshot(preview)
    preview["opacity"] = 65
    preview["alerts"].update(volume=0, pve_filter=False, persist_until_selected=False)
    preview["alerts"]["events"]["combat"].update(
        enabled=False, pulses=7, flash_rate="fast"
    )
    current = custom.prepare_alert_snapshot(preview, previous)
    assert (current.rules_revision, current.activation_epoch) == (1, 1)
    assert current.custom_rules == previous.custom_rules
    assert (current.volume, current.pve_filter, current.persist_until_selected) == (
        0,
        False,
        False,
    )
    assert (
        current.builtins[0].enabled,
        current.builtins[0].pulses,
        current.builtins[0].flash_rate,
    ) == (False, 7, "fast")
    assert custom.prepare_alert_snapshot(deepcopy(preview), current) == current


def test_sibling_edit_reorder_delete_and_add_preserve_unchanged_rule_tokens():
    first = _rule("first")
    second = _rule("second", search="fleet")
    initial = custom.prepare_alert_snapshot(_preview(first, second))
    second = {**second, "name": "Renamed"}
    edited = custom.prepare_alert_snapshot(_preview(first, second), initial)
    assert edited.rules_revision == 2
    assert [(r.rule.id, r.generation) for r in edited.custom_rules] == [
        ("first", 1),
        ("second", 2),
    ]
    reordered = custom.prepare_alert_snapshot(_preview(second, first), edited)
    assert reordered.rules_revision == 3
    assert [(r.rule.id, r.generation, r.position) for r in reordered.custom_rules] == [
        ("second", 2, 0),
        ("first", 1, 1),
    ]
    removed = custom.prepare_alert_snapshot(_preview(first), reordered)
    assert removed.rules_revision == 4
    assert [(r.rule.id, r.generation, r.position) for r in removed.custom_rules] == [
        ("first", 1, 0)
    ]
    added = custom.prepare_alert_snapshot(_preview(first, second), removed)
    assert added.rules_revision == 5
    assert [(r.rule.id, r.generation) for r in added.custom_rules] == [
        ("first", 1),
        ("second", 5),
    ]
    assert added.activation_epoch == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Renamed"),
        ("search", "WARP"),
        ("enabled", False),
        ("color", "#123abc"),
        ("sound", "obey"),
        ("cooldown_s", 0),
    ],
)
def test_each_canonical_rule_edit_invalidates_only_that_rule(field, value):
    initial = custom.prepare_alert_snapshot(_preview(_rule("edit"), _rule("keep")))
    changed = custom.prepare_alert_snapshot(
        _preview(_rule("edit", **{field: value}), _rule("keep")), initial
    )
    assert changed.rules_revision == 2
    assert [r.generation for r in changed.custom_rules] == [2, 1]
    assert changed.activation_epoch == 1


@pytest.mark.parametrize("gate", ["preview_enabled", "alerts_enabled"])
def test_master_off_on_changes_activation_not_rule_generations(gate):
    initial = custom.prepare_alert_snapshot(_preview(_rule("rule")))
    inactive = custom.prepare_alert_snapshot(
        _preview(_rule("rule"), **{gate: False}), initial
    )
    assert inactive.executable == ()
    assert (inactive.rules_revision, inactive.activation_epoch) == (1, 2)
    assert inactive.custom_rules == initial.custom_rules
    still_off = custom.prepare_alert_snapshot(
        _preview(_rule("rule"), preview_enabled=False, alerts_enabled=False), inactive
    )
    assert still_off.activation_epoch == 2
    active = custom.prepare_alert_snapshot(_preview(_rule("rule")), still_off)
    assert (active.rules_revision, active.activation_epoch) == (1, 3)
    assert active.custom_rules == initial.custom_rules


def test_effective_activation_tracks_first_and_last_executable_rule():
    empty = custom.prepare_alert_snapshot(_preview())
    assert (empty.rules_revision, empty.activation_epoch, empty.executable) == (
        1,
        1,
        (),
    )
    disabled = custom.prepare_alert_snapshot(
        _preview(_rule("rule", enabled=False)), empty
    )
    assert (
        disabled.rules_revision,
        disabled.activation_epoch,
        disabled.executable,
    ) == (2, 1, ())
    active = custom.prepare_alert_snapshot(_preview(_rule("rule")), disabled)
    assert (active.rules_revision, active.activation_epoch) == (3, 2)
    removed = custom.prepare_alert_snapshot(_preview(), active)
    assert (removed.rules_revision, removed.activation_epoch, removed.executable) == (
        4,
        3,
        (),
    )


@pytest.mark.parametrize(
    "preview",
    [
        _preview(),
        _preview(_rule("disabled", enabled=False)),
        _preview(_rule("blank", enabled=False, search="")),
        _preview(_rule("rule"), preview_enabled=False),
        _preview(_rule("rule"), alerts_enabled=False),
    ],
)
def test_empty_executable_tuple_never_invokes_normalization(preview, monkeypatch):
    snapshot = custom.prepare_alert_snapshot(preview)

    def forbidden(_text):
        raise AssertionError("Inactive matching must not normalize lines")

    monkeypatch.setattr(custom, "normalize_visible", forbidden)
    assert custom.match_line("anything", snapshot) == ()


def test_matching_is_literal_ordered_and_normalizes_once_for_all_eight_rules(
    monkeypatch,
):
    searches = (
        "WARP",
        "(notify)",
        "[Fleet]",
        "a.*",
        "Straße",
        "&amp; fleet",
        "war<b>p</b>",
        "FLEET",
    )
    snapshot = custom.prepare_alert_snapshot(
        _preview(*(_rule(str(i), search=search) for i, search in enumerate(searches)))
    )
    normalize = custom.normalize_visible
    calls = []

    def counted(text):
        calls.append(text)
        return normalize(text)

    monkeypatch.setattr(custom, "normalize_visible", counted)
    line = (
        "[ 2026.08.25 11:30:00 ] (notify) [Fleet] war<b>p</b> a.* STRASSE &amp; fleet"
    )
    matches = custom.match_line(line, snapshot)
    assert tuple(row.rule.id for row in matches) == (
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
    )
    assert calls == [line]
    assert tuple(row.rule.id for row in custom.match_line("aaaa", snapshot)) == ()


@pytest.mark.parametrize(
    "rule_id,generation,epoch,want",
    [
        ("enabled", 1, 1, True),
        ("disabled", 1, 1, False),
        ("missing", 1, 1, False),
        ("enabled", 0, 1, False),
        ("enabled", 2, 1, False),
        ("enabled", 1, 0, False),
        ("enabled", 1, 2, False),
    ],
)
def test_current_rule_requires_executable_identity_generation_and_epoch(
    rule_id, generation, epoch, want
):
    snapshot = custom.prepare_alert_snapshot(
        _preview(_rule("enabled"), _rule("disabled", enabled=False))
    )
    assert custom.rule_is_current(snapshot, rule_id, generation, epoch) is want


def test_pre_activation_match_stays_stale_after_master_reactivation():
    initial = custom.prepare_alert_snapshot(_preview(_rule("rule")))
    inactive = custom.prepare_alert_snapshot(
        _preview(_rule("rule"), alerts_enabled=False), initial
    )
    assert not custom.rule_is_current(inactive, "rule", 1, 1)
    assert not custom.rule_is_current(inactive, "rule", 1, 2)
    active = custom.prepare_alert_snapshot(_preview(_rule("rule")), inactive)
    assert not custom.rule_is_current(active, "rule", 1, 1)
    assert custom.rule_is_current(active, "rule", 1, 3)


@pytest.mark.parametrize("persist", [False, True])
def test_presentation_is_fresh_style_only_with_fixed_custom_pulses(persist):
    rule = custom.CustomRule(
        "private-id",
        name="Private name",
        search="Private search",
        color="#123abc",
        sound="obey",
        cooldown_s=17,
    )
    spec = custom.presentation_spec(rule, persist=persist)
    assert spec == {
        "enabled": True,
        "color": "#123abc",
        "sound": "obey",
        "cooldown_s": 17,
        "pulses": 3,
        "flash_rate": "normal",
        "persist_until_selected": persist,
    }
    spec["color"] = "#000000"
    assert custom.presentation_spec(rule, persist=persist)["color"] == "#123abc"
