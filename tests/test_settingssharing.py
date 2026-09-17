"""Settings export/import: pure model plus the controller's named operations.

conftest.py redirects LOCALAPPDATA per test, so the controller's
settings.update() call persists through the real paths machinery into
tmp_path and the round-trip is exercised end to end.
"""

import json

import pytest

from wingman import settings as settings_mod
from wingman.settingssharing import (
    EXCLUDED_KEYS,
    FORMAT,
    TYPE,
    VERSION,
    SettingsShareController,
    SettingsShareError,
    SettingsSharePorts,
    apply_document,
    export_document,
    export_text,
    parse_text,
    review,
)


def live_settings() -> dict:
    return settings_mod.load()


def always(value):
    return lambda *args, **kwargs: value


def ports(input_path="", output_path=""):
    return SettingsSharePorts(
        choose_settings_input=always(input_path),
        choose_settings_output=always(output_path),
    )


# ---- model: export -------------------------------------------------------


def test_export_carries_every_default_key_except_the_webhook():
    document = export_document(live_settings())
    assert document["format"] == FORMAT
    assert document["version"] == VERSION
    assert document["type"] == TYPE
    exported = document["settings"]
    assert set(exported) == set(settings_mod.DEFAULTS) - EXCLUDED_KEYS
    assert "discord_webhook" not in exported


def test_webhook_identity_never_travels_to_another_credential():
    config = live_settings()
    config.update(
        discord_webhook="https://discord.com/api/webhooks/123/token",
        discord_webhook_name="Private webhook",
    )
    document = export_document(config)
    assert "discord_webhook_name" not in document["settings"]
    document["settings"]["discord_webhook_name"] = "Smuggled name"
    assert "discord_webhook_name" not in parse_text(json.dumps(document))
    apply_document({"discord_webhook_name": "Smuggled name"}, config)
    assert config["discord_webhook_name"] == "Private webhook"


def test_export_text_round_trips_through_parse():
    config = live_settings()
    config["privacy"] = "public"
    config["preview"]["snap"] = not config["preview"]["snap"]
    imported = parse_text(export_text(config))
    assert imported["privacy"] == "public"
    assert imported["preview"]["snap"] == config["preview"]["snap"]
    # Sections travel whole: the preview dict is deep-copied, so mutating
    # the parse result cannot reach the exporter's caller.
    imported["preview"]["snap"] = "mutated"
    assert config["preview"]["snap"] != "mutated"


def test_cycle_groups_with_member_order_round_trip_through_the_envelope():
    """The cycle-group rework changed the shape of preview.hotkeys; the
    export path is key-agnostic (whole-section deepcopy), so this pins the
    interplay rather than the mechanism: a group's ordered member list IS
    the cycle order, and an export/import cycle must not re-sort, dedupe
    or trim it. An old pre-group envelope, by contrast, imports with
    members emptied -- the same wipe-on-load the settings validator does,
    never a migration."""
    config = live_settings()
    group = {
        "id": "g1",
        "name": "DPS",
        "members": ["Zulu", "Alpha", "Kilo"],
        "cycle": "Ctrl+F2",
        "cycle_prev": "Ctrl+F3",
    }
    config["preview"]["hotkeys"]["groups"] = [group]
    imported = parse_text(export_text(config))
    assert imported["preview"]["hotkeys"]["groups"] == [group]
    # And through the real apply path, normalization included.
    fresh = settings_mod.load()
    apply_document(imported, fresh)
    with settings_mod.update(fresh):
        pass
    assert fresh["preview"]["hotkeys"]["groups"] == [group]

    old_envelope = {
        "format": FORMAT,
        "version": VERSION,
        "type": TYPE,
        "settings": {
            "preview": {
                "hotkeys": {
                    "characters": {"Alice": "Ctrl+F1"},
                    "cycle_next": "Ctrl+Alt+Right",
                    "cycle_prev": "Ctrl+Alt+Left",
                    "group_by_character": {"Alice": "g1"},
                    "groups": [{"id": "g1", "name": "DPS", "cycle": "Ctrl+F2"}],
                }
            }
        },
    }
    legacy = parse_text(json.dumps(old_envelope))
    target = settings_mod.load()
    apply_document(legacy, target)
    with settings_mod.update(target):
        pass
    hotkeys = target["preview"]["hotkeys"]
    assert "cycle_next" not in hotkeys and "group_by_character" not in hotkeys
    assert hotkeys["groups"] == [
        {"id": "g1", "name": "DPS", "members": [], "cycle": "Ctrl+F2", "cycle_prev": ""}
    ]


def test_export_uses_defaults_for_keys_missing_from_the_document():
    config = live_settings()
    del config["notify_mode"]
    document = export_document(config)
    assert document["settings"]["notify_mode"] == settings_mod.DEFAULTS["notify_mode"]


# ---- model: parse ---------------------------------------------------------


def test_parse_rejects_a_webhook_smuggled_into_the_settings_object():
    text = export_text(live_settings())
    document = json.loads(text)
    document["settings"]["discord_webhook"] = "https://discord.com/api/webhooks/1/x"
    imported = parse_text(json.dumps(document))
    assert "discord_webhook" not in imported


def test_learned_channel_state_is_never_exported_or_imported():
    current = live_settings()
    current["channel_id"] = "UClearned-from-the-last-upload"
    current["channel_title"] = "Someone elses channel"
    exported = export_document(current)["settings"]
    assert "channel_id" not in exported and "channel_title" not in exported
    imported = parse_text(export_text(current))
    assert "channel_id" not in imported and "channel_title" not in imported
    # And the recipient's learned state survives an import.
    with settings_mod.update(current):
        apply_document(imported, current)
    assert current["channel_id"] == "UClearned-from-the-last-upload"
    assert current["channel_title"] == "Someone elses channel"


def test_parse_drops_unknown_top_level_keys():
    text = export_text(live_settings())
    document = json.loads(text)
    document["settings"]["not_a_setting"] = {"evil": True}
    imported = parse_text(json.dumps(document))
    assert "not_a_setting" not in imported


@pytest.mark.parametrize(
    ("mangle", "code"),
    [
        pytest.param(lambda d: "{not json", "invalid_json", id="not-json"),
        pytest.param(lambda d: [], "invalid_envelope", id="not-an-object"),
        pytest.param(
            lambda d: {**d, "format": "other"}, "unsupported_format", id="format"
        ),
        pytest.param(
            lambda d: {**d, "version": 99}, "unsupported_version", id="version-int"
        ),
        pytest.param(
            lambda d: {**d, "version": "1"}, "unsupported_version", id="version-str"
        ),
        pytest.param(lambda d: {**d, "type": "other"}, "unsupported_type", id="type"),
        pytest.param(
            lambda d: {k: v for k, v in d.items() if k != "settings"},
            "invalid_envelope",
            id="settings-missing",
        ),
        pytest.param(
            lambda d: {**d, "settings": []}, "invalid_envelope", id="settings-list"
        ),
    ],
)
def test_parse_refuses_broken_envelopes_with_a_stable_code(mangle, code):
    text = export_text(live_settings())
    if code == "invalid_json":
        document = mangle(text)
    else:
        document = json.dumps(mangle(json.loads(text)))
    with pytest.raises(SettingsShareError) as caught:
        parse_text(document)
    assert caught.value.code == code


def test_parse_refuses_text_over_the_byte_budget():
    text = "x" * (4 * 1024 * 1024 + 1)
    with pytest.raises(SettingsShareError) as caught:
        parse_text(text)
    assert caught.value.code == "byte_limit"


def test_parse_refuses_non_text():
    with pytest.raises(SettingsShareError) as caught:
        parse_text(b"{}")
    assert caught.value.code == "invalid_text"


# ---- model: review and apply ----------------------------------------------


def test_review_names_changed_keys_and_keeps_the_rest():
    current = live_settings()
    imported = parse_text(export_text(current))
    imported["privacy"] = "public"
    imported["notify_mode"] = "popup"
    summary = review(imported, current)
    assert summary["changed"] == ["notify_mode", "privacy"]
    assert "discord_webhook" in summary["kept"]
    assert "preview" not in summary["changed"]


def test_apply_overlays_only_imported_keys_inside_update():
    current = live_settings()
    current["discord_webhook"] = "https://example/webhook"
    current["privacy"] = "private"
    imported = {"privacy": "public", "not_a_setting": 1, "discord_webhook": "evil"}
    with settings_mod.update(current):
        apply_document(imported, current)
    assert current["privacy"] == "public"
    # The one secret in the document can never be reached through an import.
    assert current["discord_webhook"] == "https://example/webhook"
    # The overlay trusts the imported value; update()'s normalization is
    # what validates it. A raw invalid value here would be coerced, which
    # is the contract -- this asserts the live document stays normalized.
    assert current["privacy"] in settings_mod.VALID_PRIVACY


def test_apply_through_update_normalizes_and_persists():
    current = live_settings()
    imported = parse_text(export_text(current))
    imported["privacy"] = "not-a-choice"
    imported["preview"] = {"width": 50, "enabled": True, "junk": True}
    with settings_mod.update(current):
        apply_document(imported, current)
    assert current["privacy"] == settings_mod.DEFAULTS["privacy"]
    assert current["preview"]["enabled"] is True
    # Clamped to the validator's floor, and the unknown inner key dropped.
    assert current["preview"]["width"] >= 120
    assert "junk" not in current["preview"]
    reloaded = settings_mod.load()
    assert reloaded["preview"]["enabled"] is True


def test_apply_absent_keys_keep_their_current_values():
    current = live_settings()
    current["gamelogs_dir"] = "C:/logs"
    imported = {"privacy": "public"}
    with settings_mod.update(current):
        apply_document(imported, current)
    assert current["gamelogs_dir"] == "C:/logs"


# ---- controller ------------------------------------------------------------


def test_export_file_writes_the_envelope(tmp_path):
    destination = tmp_path / "wingman-settings.json"
    controller = SettingsShareController(
        live_settings(), ports=ports(output_path=str(destination))
    )
    reply = controller.export_file()
    assert reply["ok"] is True and reply["error"] == ""
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["format"] == FORMAT
    assert "discord_webhook" not in document["settings"]


def test_export_file_reports_cancellation_and_non_json_names(tmp_path):
    cancel = SettingsShareController(live_settings(), ports=ports())
    assert cancel.export_file() == {
        "ok": False,
        "cancelled": True,
        "error": "",
        "path": "",
    }
    bad = SettingsShareController(
        live_settings(), ports=ports(output_path=str(tmp_path / "export.txt"))
    )
    reply = bad.export_file()
    assert reply["ok"] is False and reply["error"]


def test_import_read_summarizes_and_apply_persists(tmp_path):
    destination = tmp_path / "wingman-settings.json"
    source = live_settings()
    source["privacy"] = "public"
    (tmp_path / "source.json").write_text(export_text(source), encoding="utf-8")

    controller = SettingsShareController(
        live_settings(),
        ports=ports(
            input_path=str(tmp_path / "source.json"), output_path=str(destination)
        ),
    )
    read = controller.import_read()
    assert read["ok"] is True and read["error"] == ""
    assert read["summary"]["changed"] == ["privacy"]

    apply = controller.import_apply(read["review_id"])
    assert apply == {"ok": True, "error": ""}
    assert settings_mod.load()["privacy"] == "public"
    # The offer is consumed: a second apply of the same id cannot re-apply.
    again = controller.import_apply(read["review_id"])
    assert again["ok"] is False and again["error"]


def test_import_read_cancellation_and_malformed_files(tmp_path):
    controller = SettingsShareController(live_settings(), ports=ports())
    assert controller.import_read()["cancelled"] is True
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    reply = SettingsShareController(
        live_settings(), ports=ports(input_path=str(bad))
    ).import_read()
    assert reply["ok"] is False and reply["error"]
    assert controller.import_review("whatever")["ok"] is False


def test_import_offer_is_single_slot_and_claimed_by_identity(tmp_path):
    first = tmp_path / "first.json"
    source = live_settings()
    source["privacy"] = "public"
    first.write_text(export_text(source), encoding="utf-8")
    second = tmp_path / "second.json"
    other = live_settings()
    other["notify_mode"] = "popup"
    second.write_text(export_text(other), encoding="utf-8")

    controller = SettingsShareController(
        live_settings(), ports=ports(input_path=str(first))
    )
    offer_a = controller.import_read()
    # A newer read supersedes the older offer.
    controller._ports = ports(input_path=str(second))
    offer_b = controller.import_read()
    stale = controller.import_review(offer_a["review_id"])
    assert stale["ok"] is False
    assert controller.import_discard(offer_a["review_id"]) is False
    fresh = controller.import_review(offer_b["review_id"])
    assert fresh["ok"] is True
    assert fresh["summary"]["changed"] == ["notify_mode"]
    assert controller.import_apply(offer_a["review_id"])["ok"] is False
    assert controller.import_apply(offer_b["review_id"])["ok"] is True
    assert settings_mod.load()["notify_mode"] == "popup"
    assert controller.import_discard(offer_b["review_id"]) is False


# ---- apply-side live refresh -----------------------------------------------


def applied_ports(calls, **kwargs):
    return SettingsSharePorts(
        choose_settings_input=always(kwargs.get("input_path", "")),
        choose_settings_output=always(kwargs.get("output_path", "")),
        on_applied=lambda: calls.append("applied"),
    )


def test_apply_invokes_on_applied_once_after_the_save(tmp_path):
    source = live_settings()
    source["privacy"] = "public"
    (tmp_path / "source.json").write_text(export_text(source), encoding="utf-8")
    calls = []
    controller = SettingsShareController(
        live_settings(),
        ports=applied_ports(calls, input_path=str(tmp_path / "source.json")),
    )
    read = controller.import_read()
    assert controller.import_apply(read["review_id"])["ok"] is True
    assert calls == ["applied"]
    # The port runs after the document is durable.
    assert settings_mod.load()["privacy"] == "public"


def test_failed_or_superseded_applies_never_invoke_on_applied(tmp_path):
    calls = []
    controller = SettingsShareController(live_settings(), ports=applied_ports(calls))
    # No offer was ever read: the id is stale and nothing is applied.
    assert controller.import_apply("missing")["ok"] is False
    assert calls == []
    # A discarded offer cannot trigger the port either.
    source = live_settings()
    (tmp_path / "source.json").write_text(export_text(source), encoding="utf-8")
    controller = SettingsShareController(
        live_settings(),
        ports=applied_ports(calls, input_path=str(tmp_path / "source.json")),
    )
    read = controller.import_read()
    assert controller.import_discard(read["review_id"]) is True
    assert controller.import_apply(read["review_id"])["ok"] is False
    assert calls == []


def test_on_applied_failure_does_not_fail_the_apply(tmp_path):
    source = live_settings()
    source["privacy"] = "public"
    (tmp_path / "source.json").write_text(export_text(source), encoding="utf-8")

    def explode():
        raise RuntimeError("live refresh failed")

    controller = SettingsShareController(
        live_settings(),
        ports=SettingsSharePorts(
            choose_settings_input=always(str(tmp_path / "source.json")),
            choose_settings_output=always(""),
            on_applied=explode,
        ),
    )
    read = controller.import_read()
    apply = controller.import_apply(read["review_id"])
    # The import is already durable; a live-refresh failure must not reach
    # the page as an apply error inviting a second apply of a claimed id.
    assert apply["ok"] is True and apply["error"] == ""
    assert settings_mod.load()["privacy"] == "public"
