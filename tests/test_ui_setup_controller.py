"""Read-only setup boundaries on distinct synthetic source and recipient profiles."""

import copy
import io
import json
from dataclasses import fields, replace
from pathlib import Path
from uuid import UUID

import pytest

from tests import fakes
from tests.setup_fixtures import install_lossless_codec, seed_profile, wire
from tests.test_evesettings_codec import CODEC
from tests.test_evesettings_controller import build_controller
from tests.test_ui_setup_documents import value
from wingman import atomicio
from wingman.evesettings import (
    codec,
    setup_documents,
    setup_model,
    setup_profile,
    setup_sharing,
)
from wingman.ui import api as api_mod


@pytest.fixture
def setup(tmp_path, monkeypatch):
    install_lossless_codec(monkeypatch)
    source = seed_profile(tmp_path, case="source", name="Source")
    base = seed_profile(tmp_path)
    controller = build_controller(tmp_path)
    controller._settings["eve_settings"].update(
        root=str(source.root),
        server=str(source.server),
        profile=str(source.profile),
        account_characters={"10": ["11"], "20": ["30", "31"]},
    )
    return controller, source, base


def review(controller, base, text=None, **kwargs):
    return controller.setup_review(
        setup_sharing.export_text(wire()) if text is None else text,
        str(base.profile),
        str(base.account_path),
        str(base.character_path),
        kwargs.pop("destination_name", "Imported"),
        **kwargs,
    )


def export(controller, source):
    return controller.setup_export(
        str(source.profile), str(source.account_path), str(source.character_path)
    )


def test_context_browsing_does_not_persist_selection(setup, monkeypatch):
    controller, source, base = setup
    before = copy.deepcopy(controller._settings)
    writes = []
    controller._ports = replace(controller._ports, update_settings=writes.append)

    def forbidden(*args, **kwargs):
        pytest.fail("read-only browsing called a selection/resolver effect")

    monkeypatch.setattr(controller, "select", forbidden)
    monkeypatch.setattr(controller, "_eve_persist_selection", forbidden)
    monkeypatch.setattr(controller, "resolve_names", forbidden)
    reply = controller.setup_context(str(base.profile))
    assert reply["ok"], reply
    assert set(reply) == {
        "ok",
        "error",
        "root",
        "server",
        "profile",
        "profiles",
        "accounts",
        "characters",
        "account_identity_available",
        "setup_available",
    }
    assert reply["profile"] == str(base.profile) != str(source.profile)
    assert reply["root"] == str(base.root)
    assert reply["server"] == str(base.server)
    assert reply["account_identity_available"] is True
    assert reply["setup_available"] is True
    assert [item["id"] for item in reply["accounts"]] == ["20"]
    assert reply["accounts"][0]["character_ids"] == [
        "30"
    ]  # 31 is confirmed but not local
    assert [item["id"] for item in reply["characters"]] == ["30"]
    assert {item["path"] for item in reply["profiles"]} == {
        str(source.profile),
        str(base.profile),
    }
    assert controller._settings == before
    assert (
        writes
        == controller._running_pushes
        == controller._names_pushes
        == controller._done_pushes
        == []
    )


def test_setup_flag_and_limits_are_independent_fresh_payloads(setup, monkeypatch):
    controller, _, base = setup
    monkeypatch.setattr(codec, "codec_available", lambda: False)
    assert controller.state()["setup_available"] is False
    assert controller.setup_context(str(base.profile))["setup_available"] is False
    limits = controller.setup_limits()
    assert limits == setup_model.limits_payload()
    limits["max_bytes"] = 0
    assert controller.setup_limits()["max_bytes"] == 2 * 1024 * 1024
    assert not review(controller, base)["ok"]


@pytest.mark.parametrize(
    "mutation",
    ["stale", "other-server", "off-tq", "unknown", "escaped", "deleted-profile"],
)
def test_context_refuses_fallback_or_untrusted_bases(setup, mutation, tmp_path):
    controller, _, base = setup
    wanted = base.profile
    if mutation == "stale":
        wanted = base.server / "settings_Missing"
    elif mutation == "other-server":
        wanted = base.root / "d_eve_tq_tranquility" / "settings_Other"
        wanted.mkdir(parents=True)
    elif mutation in ("off-tq", "unknown"):
        server = base.root / (
            "c_eve_singularity" if mutation == "off-tq" else "tranquil_unknown"
        )
        base.server.rename(server)
        wanted = server / base.profile.name
        controller._settings["eve_settings"].update(
            server=str(server), profile=str(wanted)
        )
    elif mutation == "escaped":
        wanted = base.server / "settings_Escape"
        outside = tmp_path / "outside"
        outside.mkdir()
        wanted.symlink_to(outside, target_is_directory=True)
    else:
        controller._settings["eve_settings"]["profile"] = str(
            base.server / "settings_Gone"
        )
    reply = controller.setup_context(str(wanted))
    assert not reply["ok"] and reply["error"]


def test_export_uses_real_source_without_preferences_or_destination(setup):
    controller, source, _ = setup
    (source.profile / "prefs.ini").unlink()
    (source.profile / "core_public__.yaml").unlink()
    before = {p.name: p.read_bytes() for p in source.profile.iterdir()}
    result = export(controller, source)
    assert result["ok"], result
    assert set(result) == {"ok", "error", "text", "summary", "warnings"}
    parsed = setup_sharing.parse_text(result["text"])
    assert parsed.source_kind == "wingman"
    assert parsed.overview["presets"][0]["name"] == "Synthetic Fleet"
    assert (
        "content_revision" not in result["text"]
        and str(source.profile) not in result["text"]
    )
    assert {p.name: p.read_bytes() for p in source.profile.iterdir()} == before
    assert controller._setup_review is None


@pytest.mark.parametrize("operation", ["export", "review"])
@pytest.mark.parametrize(
    "refusal", ["EVE is running.", "Could not verify EVE is closed.", "exception"]
)
def test_snapshots_require_positive_closed_state(
    setup, monkeypatch, operation, refusal
):
    controller, source, base = setup

    def probe():
        if refusal == "exception":
            raise OSError("probe unavailable")
        return refusal

    controller._ports = replace(controller._ports, profile_copy_refusal=probe)
    monkeypatch.setattr(
        codec, "read_snapshot", lambda *a, **kw: pytest.fail("read before closed")
    )
    reply = (
        export(controller, source)
        if operation == "export"
        else review(controller, base)
    )
    assert not reply["ok"] and reply["error"]
    if operation == "review":
        assert reply["error_code"] == "eve_not_closed"
        assert controller._setup_review is None


@pytest.mark.parametrize(
    "mutation",
    [
        "unlinked",
        "ambiguous",
        "deleted",
        "missing",
        "wrong-profile",
        "escape",
        "directory",
        "hardlink",
    ],
)
@pytest.mark.parametrize("operation", ["export", "review"])
def test_pairs_require_unambiguous_confirmed_links_and_real_local_files(
    setup, tmp_path, mutation, operation
):
    controller, source, base = setup
    pair = source if operation == "export" else base
    aid, cid = ("10", "11") if operation == "export" else ("20", "30")
    links = controller._settings["eve_settings"]["account_characters"]
    if mutation == "unlinked":
        links.pop(aid)
    elif mutation == "ambiguous":
        links["99"] = [cid]  # A second saved owner is ambiguous even if not local.
    elif mutation == "deleted":
        controller._eve_deleted.add(("tranquility", int(cid)))
    elif mutation == "missing":
        pair.character_path.unlink()
    elif mutation == "wrong-profile":
        pair = replace(
            pair,
            character_path=base.character_path
            if operation == "export"
            else source.character_path,
        )
    else:
        pair.character_path.unlink()
        if mutation == "directory":
            pair.character_path.mkdir()
        else:
            outside = tmp_path / "other.dat"
            outside.write_bytes(b"not a local dat")
            if mutation == "escape":
                pair.character_path.symlink_to(outside)
            else:
                pair.character_path.hardlink_to(outside)
    reply = (
        export(controller, pair) if operation == "export" else review(controller, pair)
    )
    assert not reply["ok"] and reply["error"]
    assert controller._setup_review is None


def test_review_binds_original_selection_and_distinct_sibling_without_effects(
    setup, monkeypatch
):
    controller, source, base = setup
    before = copy.deepcopy(controller._settings)
    before_files = {p: p.read_bytes() for p in base.root.rglob("*") if p.is_file()}
    writes = []
    controller._ports = replace(controller._ports, update_settings=writes.append)
    text = export(controller, source)["text"]
    real_apply = setup_documents.apply_setup
    applied = []

    def observe(account, character, parsed, **kwargs):
        result = real_apply(account, character, parsed, **kwargs)
        assert result != (account, character)
        applied.append(result)
        return result

    monkeypatch.setattr(setup_documents, "apply_setup", observe)
    reply = review(controller, base, text)
    assert reply["ok"], reply
    assert set(reply) == {
        "ok",
        "error",
        "error_code",
        "review_id",
        "summary",
        "warnings",
        "needs_label_choice",
    }
    offer = controller._setup_review
    assert UUID(reply["review_id"]).version == 4
    assert offer.review_id == reply["review_id"]
    assert offer.text == text and offer.keep_ship_labels is False
    assert offer.selection_context.profile == str(source.profile)
    assert offer.generation == controller._eve_generation()
    assert offer.plan.source == base.profile
    assert (
        offer.plan.mode == "new" and offer.plan.destination.name == "settings_Imported"
    )
    assert (
        offer.account_filename,
        offer.character_filename,
        offer.account_id,
        offer.character_id,
    ) == ("core_user_20.dat", "core_char_30.dat", "20", "30")
    assert offer.manifest == setup_profile.capture_manifest(offer.plan)
    assert set(f.name for f in fields(offer)) == {
        "review_id",
        "text",
        "keep_ship_labels",
        "selection_context",
        "generation",
        "plan",
        "account_filename",
        "character_filename",
        "account_id",
        "character_id",
        "manifest",
    }
    assert len(applied) == 1
    # The same adapter and immutable manifest also authorize the real Task 5 staging seam.
    with setup_profile.stage_setup(
        offer.plan,
        offer.manifest,
        offer.account_filename,
        offer.character_filename,
        setup_sharing.parse_text(text),
        keep_ship_labels=False,
        now=1000.0,
    ) as staged:
        changed = codec.read_document(staged.path / offer.account_filename)
        assert changed != codec.read_document(base.account_path)
    assert controller.setup_discard("wrong-id") is False
    assert controller._setup_review is offer
    assert controller.setup_discard(offer.review_id) is True
    assert controller.setup_discard(offer.review_id) is False
    assert controller._setup_review is None
    assert controller._settings == before and writes == []
    assert {
        p: p.read_bytes() for p in base.root.rglob("*") if p.is_file()
    } == before_files
    assert (
        controller._running_pushes
        == controller._names_pushes
        == controller._done_pushes
        == []
    )


def test_admitted_review_clears_offer_before_parse_and_success_gets_fresh_uuid(
    setup, monkeypatch
):
    controller, _, base = setup
    first = review(controller, base)
    second = review(controller, base)
    assert first["ok"] and second["ok"] and first["review_id"] != second["review_id"]
    parse = setup_sharing.parse_text

    def observe(text):
        assert controller._setup_review is None
        return parse(text)

    monkeypatch.setattr(setup_sharing, "parse_text", observe)
    reply = review(controller, base, "not a setup")
    assert not reply["ok"] and reply["error_code"] and not reply["review_id"]
    assert controller._setup_review is None


@pytest.mark.parametrize("operation", ["context", "export", "review", "discard"])
def test_busy_requests_return_without_effects_or_clearing_offer(setup, operation):
    controller, source, base = setup
    first = review(controller, base)
    assert first["ok"], first
    offer = controller._setup_review
    with controller._eve_mutation:
        if operation == "context":
            result = controller.setup_context(str(base.profile))
        elif operation == "export":
            result = export(controller, source)
        elif operation == "review":
            result = review(controller, base, "bad")
        else:
            assert controller.setup_discard(first["review_id"]) is False
            result = {"ok": False}
    assert not result["ok"]
    assert controller._setup_review is offer
    assert controller._alerts == controller._done_pushes == []


@pytest.mark.parametrize(
    "changed", ["account", "character", "extra", "addition", "removal", "preferences"]
)
def test_review_checks_full_manifest_around_document_reads(setup, monkeypatch, changed):
    controller, _, base = setup
    extra = base.profile / "core_char_31.dat"
    extra.write_bytes(b"original")
    real_read = codec.read_snapshot

    def race(path):
        snapshot = real_read(path)
        if Path(path) == base.character_path:
            target = {
                "account": base.account_path,
                "character": base.character_path,
                "extra": extra,
                "addition": base.profile / "core_user_99.dat",
                "removal": extra,
                "preferences": base.profile / "prefs.ini",
            }[changed]
            if changed == "removal":
                target.unlink()
            else:
                target.write_bytes(b"external")
        return snapshot

    monkeypatch.setattr(codec, "read_snapshot", race)
    reply = review(controller, base)
    assert not reply["ok"] and reply["error"]
    assert controller._setup_review is None


@pytest.mark.parametrize("which", ["account", "character"])
def test_export_rechecks_both_revisions_after_projection(setup, monkeypatch, which):
    controller, source, _ = setup
    real_export = setup_documents.export_setup

    def race(*args):
        result = real_export(*args)
        (
            source.account_path if which == "account" else source.character_path
        ).write_bytes(b"changed")
        return result

    monkeypatch.setattr(setup_documents, "export_setup", race)
    reply = export(controller, source)
    assert not reply["ok"] and reply["text"] == ""


@pytest.mark.parametrize("change", ["generation", "selection", "link", "deleted"])
def test_review_revalidates_context_generation_and_pair_after_dry_run(
    setup, monkeypatch, change
):
    controller, _, base = setup
    real_apply = setup_documents.apply_setup

    def race(*args, **kwargs):
        result = real_apply(*args, **kwargs)
        if change == "generation":
            controller._eve_clear_identification()
        elif change == "selection":
            controller._settings["eve_settings"]["profile"] = str(base.profile)
        elif change == "link":
            controller._settings["eve_settings"]["account_characters"].pop("20")
        else:
            controller._eve_deleted.add(("tranquility", 30))
        return result

    monkeypatch.setattr(setup_documents, "apply_setup", race)
    reply = review(controller, base)
    assert not reply["ok"] and not reply["review_id"]
    assert controller._setup_review is None


@pytest.mark.parametrize("which", ["prefs.ini", "core_public__.yaml"])
def test_review_requires_each_recipient_preference_file(setup, which):
    controller, _, base = setup
    (base.profile / which).unlink()
    reply = review(controller, base)
    assert not reply["ok"] and reply["error_code"] == "missing_local_preferences"
    assert controller._setup_review is None


@pytest.mark.parametrize("operation", ["export", "review"])
def test_controller_propagates_real_affected_stack_refusal(setup, operation):
    controller, source, base = setup
    pair = source if operation == "export" else base
    document = codec.read_document(pair.character_path)
    value(document, "windows", "stacksWindows")["bytes:overview"] = "bytes:Mixed"
    codec.write_document(pair.character_path, document, backup=lambda path: None)
    reply = (
        export(controller, pair) if operation == "export" else review(controller, pair)
    )
    assert not reply["ok"]
    if operation == "review":
        assert reply["error_code"] == "affected_stack"
    assert controller._setup_review is None


@pytest.mark.parametrize("operation", ["export", "review"])
def test_closed_state_is_rechecked_after_snapshot_work(setup, operation):
    controller, source, base = setup
    answers = iter([None, "EVE started during review."])
    controller._ports = replace(
        controller._ports, profile_copy_refusal=lambda: next(answers)
    )
    reply = (
        export(controller, source)
        if operation == "export"
        else review(controller, base)
    )
    assert not reply["ok"] and reply["error"] == "EVE started during review."
    assert controller._setup_review is None


@pytest.mark.parametrize("change", ["selection", "generation"])
def test_discard_refuses_stale_context_without_persisting(setup, change):
    controller, _, base = setup
    reply = review(controller, base)
    assert reply["ok"], reply
    if change == "generation":
        controller._eve_clear_identification()
    else:
        controller._settings["eve_settings"]["profile"] = str(base.profile)
    before = copy.deepcopy(controller._settings)
    assert controller.setup_discard(reply["review_id"]) is False
    assert controller._settings == before
    assert controller._names_pushes == controller._done_pushes == []


@pytest.mark.parametrize("change", ["destination", "preferences"])
def test_review_rechecks_full_manifest_after_adapter_work(setup, monkeypatch, change):
    controller, _, base = setup
    real_apply = setup_documents.apply_setup

    def race(*args, **kwargs):
        result = real_apply(*args, **kwargs)
        if change == "destination":
            (base.server / "settings_Imported").mkdir()
        else:
            (base.profile / "prefs.ini").write_bytes(b"changed")
        return result

    monkeypatch.setattr(setup_documents, "apply_setup", race)
    reply = review(controller, base)
    assert not reply["ok"] and controller._setup_review is None
    if change == "destination":
        assert reply["error_code"] == "destination_exists"


def test_review_uses_real_adapter_refusal_and_missing_local_preferences(setup):
    controller, _, base = setup
    document = codec.read_document(base.character_path)
    codec.write_document(
        base.character_path, codec.Document({}, document.had_crc), backup=lambda p: None
    )
    assert not review(controller, base)["ok"]
    assert controller._setup_review is None
    (base.profile / "prefs.ini").unlink()
    reply = review(controller, base)
    assert not reply["ok"] and reply["error_code"] == "missing_local_preferences"


def test_ambiguous_native_labels_require_explicit_keep_and_no_offer(setup):
    controller, _, base = setup
    text = (Path(__file__).parent / "fixtures/ui_setup/native-complete.yaml").read_text(
        encoding="utf-8"
    )
    reply = review(controller, base, text)
    assert not reply["ok"] and reply["error_code"] == "label_choice_required"
    assert reply["needs_label_choice"] is True and not reply["review_id"]
    assert controller._setup_review is None
    assert review(controller, base, text, keep_ship_labels=True)["ok"]
    assert controller._setup_review.keep_ship_labels is True
    assert not review(controller, base, text, keep_ship_labels="yes")["ok"]


@pytest.mark.parametrize(
    "destination, code",
    [
        ("Base", "destination_exists"),
        ("base", "destination_exists"),
        ("../Escape", "invalid_request"),
        ("", "invalid_request"),
        ("CON", "invalid_request"),
        (None, "invalid_request"),
    ],
)
def test_review_only_accepts_a_valid_new_destination(setup, destination, code):
    controller, _, base = setup
    reply = review(controller, base, destination_name=destination)
    assert not reply["ok"] and not reply["review_id"]
    assert reply["error_code"] == code
    assert controller._setup_review is None


@pytest.mark.parametrize("result", [None, [], ("/tmp/chosen.json",)])
def test_named_dialog_ports_late_bind_window_and_pinned_dialog_arguments(
    tmp_path, monkeypatch, result
):
    api, _ = fakes.build_api(tmp_path)
    calls = []

    class Window:
        def create_file_dialog(self, kind, **kwargs):
            calls.append((kind, kwargs))
            return result

    monkeypatch.setattr(api_mod, "_open_file_dialog_kind", lambda: "open")
    monkeypatch.setattr(api_mod, "_save_file_dialog_kind", lambda: "save")
    api._window = Window()
    want = result[0] if result else ""
    assert api._profiles._ports.choose_setup_input() == want
    assert api._profiles._ports.choose_setup_output("setup.json") == want
    assert calls == [
        (
            "open",
            {
                "directory": "",
                "allow_multiple": False,
                "file_types": ("UI setup (*.json;*.yaml;*.yml)",),
            },
        ),
        (
            "save",
            {
                "directory": "",
                "save_filename": "setup.json",
                "file_types": ("Wingman UI setup (*.json)",),
            },
        ),
    ]


def test_file_cancellation_and_dialog_errors_are_distinct(tmp_path):
    controller = build_controller(tmp_path)
    text = setup_sharing.export_text(wire())
    assert controller.setup_read_file() == {
        "ok": False,
        "cancelled": True,
        "error": "",
        "text": "",
    }
    assert controller.setup_save_file(text) == {
        "ok": False,
        "cancelled": True,
        "error": "",
        "path": "",
    }

    def broken(*args):
        raise RuntimeError("dialog failed")

    controller._ports = replace(
        controller._ports, choose_setup_input=broken, choose_setup_output=broken
    )
    for reply in (controller.setup_read_file(), controller.setup_save_file(text)):
        assert (
            not reply["ok"]
            and not reply["cancelled"]
            and "dialog failed" in reply["error"]
        )


@pytest.mark.parametrize(
    "raw", [b"\xef\xbb\xbfpresets: []", b"presets: []", "presets: [] # \u03bb".encode()]
)
def test_file_read_accepts_utf8_and_strips_only_bom(tmp_path, raw):
    controller = build_controller(tmp_path)
    file = tmp_path / "input.yaml"
    file.write_bytes(raw)
    controller._ports = replace(controller._ports, choose_setup_input=lambda: str(file))
    assert controller.setup_read_file() == {
        "ok": True,
        "cancelled": False,
        "error": "",
        "text": raw.decode("utf-8-sig"),
    }


@pytest.mark.parametrize("raw", [b"\xff", b"a" * (2 * 1024 * 1024 + 1)])
def test_file_read_refuses_legacy_encoding_or_oversize(tmp_path, raw):
    controller = build_controller(tmp_path)
    file = tmp_path / "input.yaml"
    file.write_bytes(raw)
    controller._ports = replace(controller._ports, choose_setup_input=lambda: str(file))
    result = controller.setup_read_file()
    assert not result["ok"] and not result["cancelled"] and result["error"]
    assert result["text"] == ""


def test_file_read_bounds_io_before_decoding(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    controller._ports = replace(
        controller._ports, choose_setup_input=lambda: "/synthetic/input.yaml"
    )

    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert size == 2 * 1024 * 1024 + 1
            return super().read(size)

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: Bounded(b"presets: []"))
    assert controller.setup_read_file()["ok"]


def test_file_save_validates_full_json_and_writes_atomically(tmp_path, monkeypatch):
    controller = build_controller(tmp_path)
    target = tmp_path / "shared.json"
    target.write_text("old", encoding="utf-8")
    calls = []
    controller._ports = replace(
        controller._ports,
        choose_setup_output=lambda suggested: calls.append(suggested) or str(target),
    )
    text = setup_sharing.export_text(wire())
    reply = controller.setup_save_file(text)
    assert reply == {"ok": True, "cancelled": False, "error": "", "path": str(target)}
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(text)
    assert calls == ["wingman-ui-setup.json"]
    before = target.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(atomicio, "replace_with_retry", fail)
    reply = controller.setup_save_file(text)
    assert not reply["ok"] and not reply["cancelled"] and reply["path"] == ""
    assert "disk full" in reply["error"]
    assert target.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []
    calls.clear()
    for invalid in ("presets: []", '{"version": 2}', "bad", 12):
        assert not controller.setup_save_file(invalid)["ok"]
    assert calls == []


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("native", [False, True], ids=["full", "native-yaml"])
def test_native_transport_review_and_real_staging_on_distinct_synthetic_base(
    tmp_path, monkeypatch, native
):
    original_run = codec._run

    def transport(mode, payload, **kwargs):
        return original_run(
            mode, payload, runner=kwargs["runner"], exe=lambda: str(CODEC)
        )

    monkeypatch.setattr(codec, "_run", transport)
    monkeypatch.setattr(codec, "codec_available", lambda: True)
    source = seed_profile(tmp_path, case="source", name="Source")
    base = seed_profile(tmp_path)
    controller = build_controller(tmp_path)
    controller._settings["eve_settings"].update(
        root=str(source.root),
        server=str(source.server),
        profile=str(source.profile),
        account_characters={"10": ["11"], "20": ["30"]},
    )
    exported = export(controller, source)
    assert exported["ok"], exported
    text = (
        (Path(__file__).parent / "fixtures/ui_setup/native-complete.yaml").read_text(
            encoding="utf-8"
        )
        if native
        else exported["text"]
    )
    before = {p: p.read_bytes() for p in base.root.rglob("*") if p.is_file()}
    reply = review(controller, base, text, keep_ship_labels=native)
    assert reply["ok"], reply
    offer = controller._setup_review
    with setup_profile.stage_setup(
        offer.plan,
        offer.manifest,
        offer.account_filename,
        offer.character_filename,
        setup_sharing.parse_text(offer.text),
        keep_ship_labels=offer.keep_ship_labels,
        now=1000.0,
    ) as staged:
        account = codec.read_document(staged.path / offer.account_filename)
        character = codec.read_document(staged.path / offer.character_filename)
        original_account = codec.read_document(base.account_path)
        original_character = codec.read_document(base.character_path)
        assert account != original_account
        if native:
            assert value(account, "overview", "tabsByWindowInstanceID") == [
                list(range(8))
            ]
            assert value(character, "windows", "windowSizesAndPositions_1") == value(
                original_character, "windows", "windowSizesAndPositions_1"
            )
            assert (
                account.doc["bytes:overview"]["bytes:shipLabels"]
                == original_account.doc["bytes:overview"]["bytes:shipLabels"]
            )
        else:
            assert value(account, "overview", "tabsByWindowInstanceID") == [
                [0, 1, 2],
                [3, 4, 5],
                [6, 7],
            ]
            assert value(character, "windows", "windowSizesAndPositions_1")[
                "bytes:overview_1"
            ] == {"tuple": [-20, 200, 320, 420, 1600, 900]}
        for name in ("core_public__.yaml", "prefs.ini"):
            assert (staged.path / name).read_bytes() == before[base.profile / name]
    assert not offer.plan.destination.exists()
    assert controller.setup_discard(offer.review_id) is True
    assert {p: p.read_bytes() for p in base.root.rglob("*") if p.is_file()} == before


def test_file_save_rejects_non_json_destination_without_writing(tmp_path):
    controller = build_controller(tmp_path)
    target = tmp_path / "prefs.ini"
    target.write_bytes(b"keep")
    controller._ports = replace(
        controller._ports, choose_setup_output=lambda suggested: str(target)
    )
    result = controller.setup_save_file(setup_sharing.export_text(wire()))
    assert not result["ok"] and not result["cancelled"] and result["path"] == ""
    assert target.read_bytes() == b"keep"
