"""Setup review and creation on distinct synthetic source and recipient profiles."""

import contextlib
import copy
import errno
import io
import json
import logging
from dataclasses import fields, replace
from pathlib import Path
from uuid import UUID

import pytest

from tests import fakes, test_setup_catalog
from tests.setup_fixtures import install_lossless_codec, seed_profile, wire
from tests.test_evesettings_codec import CODEC
from tests.test_evesettings_controller import QueuedThreads, build_controller
from tests.test_ui_setup_documents import value
from wingman import atomicio
from wingman.evesettings import (
    codec,
    profilecopy,
    setup_catalog,
    setup_documents,
    setup_model,
    setup_profile,
    setup_sharing,
)
from wingman.ui import api as api_mod

catalog_fixture = test_setup_catalog.catalog_fixture


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
        account_names={"10": "Synthetic source", "20": "Synthetic recipient"},
        account_characters={"10": ["11"], "20": ["30", "31"]},
    )
    return controller, source, base


@pytest.fixture
def catalog_controller(tmp_path):
    controller = build_controller(tmp_path)
    root = tmp_path / "EVE"
    server = root / "c_eve_sharedcache_tq_tranquility"
    # Keep non-default mutation sentinels without seeding profiles — catalog
    # diagnostics and identity refusals must not consult local settings files.
    controller._settings["eve_settings"].update(
        root=str(root),
        server=str(server),
        profile=str(server / "settings_Source"),
        account_names={"10": "Synthetic source", "20": "Synthetic recipient"},
        account_characters={"10": ["11"], "20": ["30", "31"]},
    )
    return controller


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


@pytest.mark.parametrize("failure", ["none", "manifest", "artifact"])
def test_catalog_reads_are_read_only_and_project_errors(
    setup, catalog_fixture, monkeypatch, failure
):
    controller, _, base = setup
    entry, text, directory = catalog_fixture
    # A catalog read must not touch even an existing authorized offer.
    offered = review(controller, base)
    assert offered["ok"], offered
    previous_offer = controller._setup_review
    before = copy.deepcopy(controller._settings)

    def forbidden(*args, **kwargs):
        pytest.fail("catalog browsing invoked review/mutation/port authority")

    for name in ("setup_review", "setup_create", "_eve_identity_hold"):
        monkeypatch.setattr(controller, name, forbidden)
    controller._ports = replace(
        controller._ports,
        **{field.name: forbidden for field in fields(controller._ports)},
    )

    class NoLock:
        def acquire(self, *args, **kwargs):
            forbidden()

        def __enter__(self):
            forbidden()

    monkeypatch.setattr(controller, "_eve_mutation", NoLock())
    if failure == "manifest":
        (directory / "catalog.json").unlink()
    elif failure == "artifact":
        (directory / "synthetic-fleet-r1.json").unlink()
    api = api_mod.Api.__new__(api_mod.Api)
    api._profiles = controller
    listing = api.eve_settings_setup_catalog()
    loaded = api.eve_settings_setup_catalog_entry(
        entry["id"], entry["revision"], entry["sha256"]
    )
    assert set(listing) == {"ok", "entries", "error"}
    assert set(loaded) == {"ok", "entry", "text", "summary", "error"}
    if failure == "manifest":
        assert listing == {"ok": False, "entries": [], "error": listing["error"]}
        assert "catalog.json" in listing["error"]
    else:
        assert listing == {"ok": True, "entries": [entry], "error": ""}
    if failure == "none":
        assert loaded["ok"] and loaded["error"] == ""
        assert loaded["entry"] == entry and loaded["text"] == text
        assert loaded["summary"]["counts"]["tabs"] == 8
    else:
        assert loaded == {
            "ok": False,
            "entry": {},
            "text": "",
            "summary": {},
            "error": loaded["error"],
        }
        assert (
            "catalog.json" in loaded["error"]
            if failure == "manifest"
            else "synthetic-fleet-r1.json" in loaded["error"]
        )
    assert controller._setup_review is previous_offer
    assert controller._settings == before


@pytest.mark.parametrize(
    "facade,adapter,args,empty",
    [
        ("setup_catalog", "list_entries", (), {"entries": []}),
        (
            "setup_catalog_entry",
            "read_entry",
            ("synthetic-fleet", 1, "a" * 64),
            {"entry": {}, "text": "", "summary": {}},
        ),
    ],
)
@pytest.mark.parametrize(
    "cause_type,code,winerror,diagnostic",
    [
        (FileNotFoundError, errno.ENOENT, None, "I/O failure: FileNotFoundError"),
        (PermissionError, errno.EACCES, None, "I/O failure: PermissionError"),
        (PermissionError, errno.EACCES, 32, "I/O failure: PermissionError"),
        (OSError, None, None, "I/O failure: OSError"),
        (None, None, None, "refused (cause=none)"),
        (ValueError, None, None, "refused (cause=ValueError)"),
    ],
    ids=["missing", "permission", "sharing", "no-codes", "no-cause", "decoder"],
)
def test_catalog_diagnostics_are_safe_and_read_only(
    catalog_controller,
    monkeypatch,
    caplog,
    facade,
    adapter,
    args,
    empty,
    cause_type,
    code,
    winerror,
    diagnostic,
):
    controller = catalog_controller
    before = copy.deepcopy(controller._settings)
    previous_offer = controller._setup_review
    private_path = r"C:\invented-private\pilot\notice.txt"
    private_body = "Invented private notice and setup body"
    cause = None
    if cause_type is not None:
        cause = (
            cause_type(code, private_body, private_path)
            if issubclass(cause_type, OSError)
            else cause_type(private_body + private_path)
        )
        if winerror is not None:
            # Linux does not populate the Windows-only field itself.
            cause.winerror = winerror
    safe_text = (
        "Cannot read bundled catalog.json. Check the Wingman installation."
        if isinstance(cause, OSError)
        else "Catalog entry has missing or unknown fields."
    )
    failure = setup_catalog.SetupCatalogError(safe_text)

    def refuse(*_args):
        raise failure from cause

    def forbidden(*_args, **_kwargs):
        pytest.fail("catalog diagnostics invoked authority ports")

    monkeypatch.setattr(setup_catalog, adapter, refuse)
    controller._ports = replace(
        controller._ports,
        **{field.name: forbidden for field in fields(controller._ports)},
    )
    api = api_mod.Api.__new__(api_mod.Api)
    api._profiles = controller
    with caplog.at_level(logging.WARNING, logger="wingman.evesettings.controller"):
        result = getattr(api, "eve_settings_" + facade)(*args)

    assert result == {"ok": False, **empty, "error": safe_text}
    assert failure.__cause__ is cause
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert facade in record.getMessage()
    assert diagnostic in record.getMessage()
    if isinstance(cause, OSError):
        assert f"errno={code}" in record.getMessage()
        assert f"winerror={winerror}" in record.getMessage()
    else:
        assert "I/O" not in record.getMessage()
        assert "errno=" not in record.getMessage()
        assert "winerror=" not in record.getMessage()
    assert record.exc_info is None and record.stack_info is None
    assert private_path not in caplog.text
    assert private_body not in caplog.text
    assert "notice.txt" not in caplog.text
    assert controller._setup_review is previous_offer
    assert controller._settings == before


@pytest.mark.parametrize(
    "args",
    [
        (None, 1, "a" * 64),
        ("../outside", 1, "a" * 64),
        ("synthetic-fleet", True, "a" * 64),
        ("synthetic-fleet", 1, None),
    ],
)
def test_catalog_bridge_arguments_refuse_at_reader_boundary(
    catalog_controller, monkeypatch, args
):
    from wingman import paths

    controller = catalog_controller
    monkeypatch.setattr(
        paths, "setup_presets_dir", lambda: pytest.fail("invalid identity reached I/O")
    )
    api = api_mod.Api.__new__(api_mod.Api)
    api._profiles = controller
    result = api.eve_settings_setup_catalog_entry(*args)
    assert result == {
        "ok": False,
        "entry": {},
        "text": "",
        "summary": {},
        "error": result["error"],
    }
    assert result["error"]


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
    assert Path(offer.selection_context.profile) == source.profile
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
def test_review_refuses_selected_file_missing_from_captured_manifest(
    setup, monkeypatch, which
):
    controller, _, base = setup
    selected = base.account_path if which == "account" else base.character_path
    before = {p: p.read_bytes() for p in base.profile.iterdir()}
    real_capture = setup_profile.capture_manifest

    def capture_without_selected(plan):
        selected.unlink()
        try:
            manifest = real_capture(plan)
        finally:
            selected.write_bytes(before[selected])
        assert selected.name not in {row.name for row in manifest.files}
        return manifest

    monkeypatch.setattr(setup_profile, "capture_manifest", capture_without_selected)
    monkeypatch.setattr(
        codec,
        "read_snapshot",
        lambda *a, **kw: pytest.fail("selected manifest membership must precede reads"),
    )
    reply = review(controller, base)
    assert not reply["ok"] and reply["error_code"] == "stale_review"
    assert reply["error"] and not reply["review_id"]
    assert controller._setup_review is None
    assert {p: p.read_bytes() for p in base.profile.iterdir()} == before


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


@pytest.mark.parametrize(
    "raw",
    [b"\xff", b"a" * (2 * 1024 * 1024 + 1)],
    ids=["legacy-encoding", "oversize-by-one"],
)
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
        account_names={"10": "Synthetic source", "20": "Synthetic recipient"},
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


def files_under(root):
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def queue_create(controller, base):
    reply = review(controller, base)
    assert reply["ok"], reply
    offer = controller._setup_review
    queued = QueuedThreads()
    controller._ports = replace(controller._ports, spawn=queued.spawn)
    assert controller.setup_create(offer.review_id, "create-1") == {
        "accepted": True,
        "error": None,
    }
    assert controller._setup_review is None
    assert controller._eve_mutation.locked()
    assert controller._done_pushes == []
    return offer, queued


def assert_create_done(controller, offer, code="", *, published=False):
    assert len(controller._done_pushes) == 1
    done = controller._done_pushes[0]
    assert set(done) == {
        "ok",
        "operation",
        "request_id",
        "review_id",
        "published",
        "path",
        "selection_persisted",
        "error_code",
        "error",
        "warning",
    }
    assert done["operation"] == "ui_setup_create"
    assert done["review_id"] == offer.review_id
    assert done["request_id"] == "create-1"
    assert done["ok"] is done["published"] is published
    assert done["path"] == (str(offer.plan.destination) if published else "")
    assert done["error_code"] == code
    assert bool(done["error"]) is bool(code)
    if not published:
        assert done["selection_persisted"] is False
        assert done["warning"] == ""
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()
    assert not list(offer.plan.server.glob(".wingman-profile-copy-*"))
    return done


@pytest.mark.parametrize("request_id", [None, True, 12, {}, "", "x" * 129])
def test_create_invalid_request_does_not_consume_offer(setup, request_id):
    controller, _, base = setup
    assert review(controller, base)["ok"]
    offer = controller._setup_review
    before = copy.deepcopy(controller._settings)
    result = controller.setup_create(offer.review_id, request_id)
    assert set(result) == {"accepted", "error"}
    assert not result["accepted"] and result["error"]
    assert controller._setup_review is offer
    assert controller._done_pushes == []
    assert controller._settings == before
    assert not controller._eve_mutation.locked()


@pytest.mark.parametrize(
    "state", ["absent", "wrong", "nontext", "discarded", "superseded", "invalid-review"]
)
def test_create_needs_matching_current_unconsumed_offer(setup, state):
    controller, _, base = setup
    first = review(controller, base)
    rid = first["review_id"]
    if state == "absent":
        controller._setup_review = None
    elif state == "wrong":
        rid = "unknown"
    elif state == "nontext":
        rid = []
    elif state == "discarded":
        assert controller.setup_discard(rid)
    elif state == "superseded":
        assert review(controller, base)["ok"]
    else:
        assert not review(controller, base, "bad")["ok"]
    current = controller._setup_review
    result = controller.setup_create(rid, "create-1")
    assert not result["accepted"] and result["error"]
    assert controller._setup_review is current
    assert controller._done_pushes == []
    assert not controller._eve_mutation.locked()


@pytest.mark.parametrize("state", ["busy", "identification"])
def test_create_never_queues_behind_mutation_or_identification(setup, state):
    controller, _, base = setup
    assert review(controller, base)["ok"]
    offer = controller._setup_review
    if state == "busy":
        controller._eve_mutation.acquire()
    else:
        controller._eve_identification = object()
    try:
        result = controller.setup_create(offer.review_id, "create-1")
        assert not result["accepted"] and result["error"]
        assert controller._setup_review is offer
        assert controller._done_pushes == controller._alerts == []
    finally:
        if state == "busy":
            controller._eve_mutation.release()
        controller._eve_identification = None
    assert controller.setup_create(offer.review_id, "create-1")["accepted"]
    assert_create_done(controller, offer, published=True)


def change_authority(controller, base, change):
    section = controller._settings["eve_settings"]
    if change == "selection":
        section["profile"] = str(base.profile)
    elif change == "unknown-context":
        section["server"] = str(base.root / "unknown")
    elif change == "missing-selection":
        section["profile"] = str(base.server / "settings_Gone")
    elif change == "generation":
        controller.identification_cancel()
    elif change == "association":
        section["account_characters"].pop("20")
    elif change == "ambiguous":
        section["account_characters"]["99"] = ["30"]
    elif change == "deleted":
        controller._eve_deleted.add(("tranquility", 30))
    elif change in ("account", "character", "unselected", "prefs", "yaml"):
        path = {
            "account": base.account_path,
            "character": base.character_path,
            "unselected": base.profile / "core_char_99.dat",
            "prefs": base.profile / "prefs.ini",
            "yaml": base.profile / "core_public__.yaml",
        }[change]
        path.write_bytes(b"external-change")
    elif change == "remove-unselected":
        (base.profile / "core_char_99.dat").unlink()
    elif change == "destination-file":
        (base.server / "settings_Imported").write_bytes(b"external destination")
    elif change == "remove-account":
        base.account_path.unlink()
    elif change == "remove-character":
        base.character_path.unlink()
    elif change in ("remove-prefs", "remove-yaml"):
        (
            base.profile
            / ("prefs.ini" if change == "remove-prefs" else "core_public__.yaml")
        ).unlink()
    elif change in ("collision", "case-collision"):
        dest = base.server / (
            "settings_Imported" if change == "collision" else "settings_IMPORTED"
        )
        dest.mkdir()
        (dest / "keep.txt").write_bytes(b"external")
    else:
        raise AssertionError(change)


CREATE_CHANGES = [
    ("selection", "stale_review"),
    ("unknown-context", "stale_review"),
    ("missing-selection", "stale_review"),
    ("generation", "stale_review"),
    ("association", "stale_review"),
    ("ambiguous", "stale_review"),
    ("deleted", "stale_review"),
    ("account", "stale_review"),
    ("character", "stale_review"),
    ("unselected", "stale_review"),
    ("remove-unselected", "stale_review"),
    ("destination-file", "destination_exists"),
    ("prefs", "stale_review"),
    ("yaml", "stale_review"),
    ("remove-account", "stale_review"),
    ("remove-character", "stale_review"),
    ("remove-prefs", "missing_local_preferences"),
    ("remove-yaml", "missing_local_preferences"),
    ("collision", "destination_exists"),
    ("case-collision", "destination_exists"),
]


@pytest.mark.parametrize("change,code", CREATE_CHANGES)
@pytest.mark.parametrize("when", ["admission", "worker", "publication"])
def test_create_revalidates_authority_and_complete_base(
    setup, monkeypatch, change, code, when
):
    controller, _, base = setup
    if change == "remove-unselected":
        (base.profile / "core_char_99.dat").write_bytes(b"unselected recipient")
    if when == "admission":
        assert review(controller, base)["ok"]
        offer = controller._setup_review
        change_authority(controller, base, change)
        before = files_under(base.root)
        result = controller.setup_create(offer.review_id, "create-1")
        assert not result["accepted"] and result["error"]
        assert controller._done_pushes == []
        assert not controller._eve_mutation.locked()
    else:
        offer, queued = queue_create(controller, base)
        if when == "worker":
            change_authority(controller, base, change)
            before = files_under(base.root)
        else:
            real_stage = setup_profile.stage_setup
            before = None

            @contextlib.contextmanager
            def stage(*args, **kwargs):
                nonlocal before
                with real_stage(*args, **kwargs) as staged:
                    change_authority(controller, base, change)
                    before = {
                        p: data
                        for p, data in files_under(base.root).items()
                        if staged.path not in p.parents
                    }
                    yield staged

            monkeypatch.setattr(setup_profile, "stage_setup", stage)
        queued.run_next()
        assert_create_done(controller, offer, code)
        assert not controller.setup_create(offer.review_id, "replay")["accepted"]
    assert files_under(base.root) == before


@pytest.mark.parametrize("when", ["admission", "worker", "publication"])
@pytest.mark.parametrize(
    "refusal", ["EVE is running.", "Could not verify EVE is closed.", "exception", ""]
)
def test_create_requires_positive_closed_at_every_boundary(
    setup, monkeypatch, when, refusal
):
    controller, _, base = setup

    def probe():
        if refusal == "exception":
            raise OSError("probe unavailable")
        return refusal

    if when == "admission":
        assert review(controller, base)["ok"]
        controller._ports = replace(controller._ports, profile_copy_refusal=probe)
        assert not controller.setup_create(
            controller._setup_review.review_id, "create-1"
        )["accepted"]
        assert controller._done_pushes == []
        assert not controller._eve_mutation.locked()
        return
    offer, queued = queue_create(controller, base)
    before = files_under(base.root)
    if when == "worker":
        controller._ports = replace(controller._ports, profile_copy_refusal=probe)
    else:
        real_stage = setup_profile.stage_setup

        @contextlib.contextmanager
        def stage(*args, **kwargs):
            with real_stage(*args, **kwargs) as staged:
                controller._ports = replace(
                    controller._ports, profile_copy_refusal=probe
                )
                yield staged

        monkeypatch.setattr(setup_profile, "stage_setup", stage)
    queued.run_next()
    assert_create_done(controller, offer, "eve_not_closed")
    assert files_under(base.root) == before


def test_create_is_new_only_correlated_and_single_use_even_before_start_reply(
    setup, monkeypatch
):
    controller, source, base = setup
    (base.profile / "core_user_99.dat").write_bytes(b"untouched account")
    (base.profile / "core_char_99.dat").write_bytes(b"untouched character")
    (base.profile / "cache.txt").write_bytes(b"not copied")
    before = files_under(base.root)
    settings_before = copy.deepcopy(controller._settings)
    offer, queued = queue_create(controller, base)
    assert Path(offer.selection_context.profile) == source.profile
    assert offer.plan.source == base.profile
    assert controller._settings == settings_before
    assert not controller.setup_create(offer.review_id, "double")["accepted"]
    assert not controller.setup_discard(offer.review_id)
    assert not review(controller, base)["ok"]

    def forbidden(*args, **kwargs):
        pytest.fail("new-only setup must not back up, prune or confirm")

    controller._ports = replace(
        controller._ports, backup_root=forbidden, confirm=forbidden
    )
    monkeypatch.setattr(controller, "_eve_prune", forbidden)
    parsed_values = []
    real_parse = setup_sharing.parse_text

    def parse(text):
        assert text == offer.text
        parsed = real_parse(text)
        parsed_values.append(parsed)
        return parsed

    monkeypatch.setattr(setup_sharing, "parse_text", parse)
    real_publish = profilecopy.publish_new

    def publish(staged):
        assert controller._settings == settings_before
        return real_publish(staged)

    monkeypatch.setattr(profilecopy, "publish_new", publish)
    queued.run_next()
    done = assert_create_done(controller, offer, published=True)
    assert done["selection_persisted"] and not done["warning"]
    assert len(parsed_values) == 1
    assert controller._settings["eve_settings"]["profile"] == str(
        offer.plan.destination
    )
    assert {p: p.read_bytes() for p in before} == before
    dest = offer.plan.destination
    assert {p.name for p in dest.iterdir()} == {
        "core_user_20.dat",
        "core_char_30.dat",
        "core_user_99.dat",
        "core_char_99.dat",
        "prefs.ini",
        "core_public__.yaml",
    }
    for path in base.profile.iterdir():
        if path.name == "cache.txt":
            continue
        copied = dest / path.name
        assert (copied.read_bytes() != path.read_bytes()) is (
            path in (base.account_path, base.character_path)
        )
    assert not controller.setup_create(offer.review_id, "replay")["accepted"]
    assert len(controller._done_pushes) == 1
    assert review(controller, base, destination_name="Next")["ok"]


@pytest.mark.parametrize("phase", ["spawn", "start"])
@pytest.mark.parametrize(
    "change", [None, "generation", "selection", "association", "prefs", "collision"]
)
def test_create_start_failure_restores_only_still_valid_offer(setup, phase, change):
    controller, _, base = setup
    assert review(controller, base)["ok"]
    offer = controller._setup_review
    original_spawn = controller._ports.spawn

    def fail():
        if change:
            change_authority(controller, base, change)
        raise RuntimeError("start failed")

    class Handle:
        def start(self):
            fail()

    def spawn(**kwargs):
        assert controller._setup_review is None
        if phase == "spawn":
            fail()
        return Handle()

    controller._ports = replace(controller._ports, spawn=spawn)
    result = controller.setup_create(offer.review_id, "create-1")
    assert not result["accepted"] and result["error"]
    assert (controller._setup_review is offer) is (change is None)
    assert controller._done_pushes == []
    assert not controller._eve_mutation.locked()
    if change is None:
        controller._ports = replace(controller._ports, spawn=original_spawn)
        assert controller.setup_create(offer.review_id, "create-1")["accepted"]
        assert_create_done(controller, offer, published=True)


@pytest.mark.parametrize("raise_after", [False, True])
def test_create_inline_completion_cannot_restore_or_double_release(setup, raise_after):
    controller, _, base = setup
    assert review(controller, base)["ok"]
    offer = controller._setup_review
    done_port = controller._ports.publish_done

    def completed(payload):
        done_port(payload)
        assert not controller._eve_mutation.locked()
        assert review(controller, base, destination_name="Next")["ok"]

    def spawn(*, target, args, daemon):
        class Handle:
            def start(self):
                target(*args)
                assert controller._done_pushes[0]["published"]
                if raise_after:
                    raise RuntimeError("handle failed after inline completion")

        return Handle()

    controller._ports = replace(controller._ports, spawn=spawn, publish_done=completed)
    assert controller.setup_create(offer.review_id, "create-1")["accepted"]
    assert_create_done(controller, offer, published=True)
    assert controller._setup_review.review_id != offer.review_id
    assert controller._setup_review.plan.destination_name == "Next"


@pytest.mark.parametrize("filename", ["core_user_20.dat", "core_char_30.dat"])
@pytest.mark.parametrize("phase", ["read", "write"])
def test_create_codec_failure_never_publishes_partial_profile(
    setup, monkeypatch, filename, phase
):
    controller, _, base = setup
    offer, queued = queue_create(controller, base)
    before = files_under(base.root)
    method = "read_snapshot" if phase == "read" else "write_document"
    original = getattr(codec, method)

    def fail(path, *args, **kwargs):
        if Path(path).name == filename:
            raise codec.CodecError(f"{filename} {phase} failed")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(codec, method, fail)
        queued.run_next()
    done = assert_create_done(controller, offer, "create_failed")
    assert filename in done["error"]
    assert files_under(base.root) == before
    assert review(controller, base)["ok"]


@pytest.mark.parametrize("filename", ["core_user_20.dat", "core_char_30.dat"])
def test_create_rejects_selected_files_absent_from_manifest_before_codec_reads(
    setup, monkeypatch, filename
):
    controller, _, base = setup
    offer, _queued = queue_create(controller, base)
    malformed = replace(
        offer,
        manifest=replace(
            offer.manifest,
            files=tuple(row for row in offer.manifest.files if row.name != filename),
        ),
    )
    # Exercise the private worker's own check, independently of admission.
    monkeypatch.setattr(
        codec,
        "read_snapshot",
        lambda *a, **kw: pytest.fail("missing membership before read"),
    )
    controller._eve_setup_create_worker(malformed, "create-1")
    assert_create_done(controller, offer, "stale_review")


@pytest.mark.parametrize(
    "effect",
    ["selection-false", "selection-raise", "selection-io", "status", "cleanup"],
)
def test_create_publication_survives_housekeeping_failures(setup, monkeypatch, effect):
    controller, _, base = setup
    offer, queued = queue_create(controller, base)
    before = files_under(base.root)

    def fail(*args, **kwargs):
        raise OSError(f"{effect} failed")

    if effect == "selection-false":
        monkeypatch.setattr(controller, "_eve_select_created_profile", lambda *a: False)
    elif effect == "selection-raise":
        monkeypatch.setattr(controller, "_eve_select_created_profile", fail)
    elif effect == "selection-io":
        controller._ports = replace(controller._ports, update_settings=fail)
    elif effect == "status":
        controller._ports = replace(controller._ports, status=fail)
    else:
        real_stage = setup_profile.stage_setup

        @contextlib.contextmanager
        def stage(*args, **kwargs):
            with real_stage(*args, **kwargs) as staged:
                yield staged
            fail()

        monkeypatch.setattr(setup_profile, "stage_setup", stage)
    queued.run_next()
    done = assert_create_done(controller, offer, published=True)
    assert done["warning"]
    assert done["selection_persisted"] is (effect == "status")
    assert {p: p.read_bytes() for p in before} == before
    assert offer.plan.destination.is_dir()
    assert not controller.setup_create(offer.review_id, "replay")["accepted"]
    assert review(controller, base, destination_name="Next")["ok"]


@pytest.mark.parametrize("when", ["admission", "publication", "restoration"])
@pytest.mark.parametrize(
    "change,code",
    [
        ("selection", "stale_review"),
        ("association", "stale_review"),
        ("generation", "stale_review"),
        ("prefs", "stale_review"),
        ("collision", "destination_exists"),
    ],
)
def test_create_does_not_trust_authority_from_before_slow_closed_probe(
    setup, monkeypatch, when, change, code
):
    controller, _, base = setup
    if when == "publication":
        offer, queued = queue_create(controller, base)
        real_stage = setup_profile.stage_setup

        @contextlib.contextmanager
        def stage(*args, **kwargs):
            with real_stage(*args, **kwargs) as staged:
                controller._ports = replace(
                    controller._ports, profile_copy_refusal=probe
                )
                yield staged

        monkeypatch.setattr(setup_profile, "stage_setup", stage)
    else:
        assert review(controller, base)["ok"]
        offer = controller._setup_review

    def probe():
        change_authority(controller, base, change)

    if when == "publication":
        queued.run_next()
        assert_create_done(controller, offer, code)
    else:
        if when == "admission":
            controller._ports = replace(controller._ports, profile_copy_refusal=probe)
        else:

            def spawn(**kwargs):
                controller._ports = replace(
                    controller._ports, profile_copy_refusal=probe
                )
                raise RuntimeError("start failed")

            controller._ports = replace(controller._ports, spawn=spawn)
        result = controller.setup_create(offer.review_id, "create-1")
        assert not result["accepted"]
        assert not controller._eve_mutation.locked()
        assert controller._done_pushes == []
        if when == "restoration":
            assert controller._setup_review is None


@pytest.mark.parametrize("change", ["generation", "deleted", "discovery-generation"])
def test_create_rechecks_authority_after_final_manifest_hashing(
    setup, monkeypatch, change
):
    controller, _, base = setup
    offer, queued = queue_create(controller, base)
    real_stage = setup_profile.stage_setup
    real_manifest = setup_profile.require_manifest
    real_found = controller._setup_found
    final_probe_done = False
    cancel_during_discovery = False

    def probe():
        nonlocal final_probe_done
        final_probe_done = True

    @contextlib.contextmanager
    def stage(*args, **kwargs):
        with real_stage(*args, **kwargs) as staged:
            controller._ports = replace(controller._ports, profile_copy_refusal=probe)
            yield staged

    def manifest(*args):
        nonlocal cancel_during_discovery
        real_manifest(*args)
        if final_probe_done:
            if change == "discovery-generation":
                cancel_during_discovery = True
            else:
                change_authority(controller, base, change)

    def found(*args):
        nonlocal cancel_during_discovery
        result = real_found(*args)
        if cancel_during_discovery:
            cancel_during_discovery = False
            controller.identification_cancel()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(setup_profile, "stage_setup", stage)
        patch.setattr(setup_profile, "require_manifest", manifest)
        patch.setattr(controller, "_setup_found", found)
        queued.run_next()
    assert_create_done(controller, offer, "stale_review")
    assert not offer.plan.destination.exists()
    assert controller._setup_review is None
    if change == "discovery-generation":
        assert not cancel_during_discovery
        assert review(controller, base)["ok"]


@pytest.mark.parametrize("when", ["admission", "restoration"])
def test_create_late_deletion_during_manifest_cannot_consume_or_restore_offer(
    setup, monkeypatch, when
):
    controller, _, base = setup
    assert review(controller, base)["ok"]
    offer = controller._setup_review
    real_manifest = setup_profile.require_manifest

    def manifest(*args):
        real_manifest(*args)
        change_authority(controller, base, "deleted")

    if when == "admission":
        monkeypatch.setattr(setup_profile, "require_manifest", manifest)
    else:

        def spawn(**kwargs):
            monkeypatch.setattr(setup_profile, "require_manifest", manifest)
            raise RuntimeError("start failed")

        controller._ports = replace(controller._ports, spawn=spawn)
    result = controller.setup_create(offer.review_id, "create-1")
    assert not result["accepted"]
    assert controller._done_pushes == []
    assert not controller._eve_mutation.locked()
    if when == "restoration":
        assert controller._setup_review is None


@pytest.mark.parametrize(
    "failure,code",
    [
        (codec.ContentChangedError("revision changed"), "stale_review"),
        (codec.CodecError("codec failed"), "create_failed"),
        (OSError("copy failed"), "create_failed"),
        (FileExistsError("destination raced"), "destination_exists"),
        (setup_model.SetupError("affected_stack", "stack appeared"), "affected_stack"),
    ],
)
def test_create_preserves_boundary_error_codes_and_failure_context(
    setup, monkeypatch, failure, code
):
    controller, _, base = setup
    offer, queued = queue_create(controller, base)
    before = files_under(base.root)

    def fail(*args, **kwargs):
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(setup_profile, "stage_setup", fail)
        queued.run_next()
    done = assert_create_done(controller, offer, code)
    assert str(failure) in done["error"]
    assert files_under(base.root) == before
    assert review(controller, base)["ok"]


@pytest.mark.parametrize("phase", ["encode", "publish"])
def test_create_external_writer_during_staging_or_final_publish_is_not_overwritten(
    setup, monkeypatch, phase
):
    controller, _, base = setup
    offer, queued = queue_create(controller, base)
    if phase == "encode":
        original = codec.write_document

        def write(*args, **kwargs):
            result = original(*args, **kwargs)
            (base.profile / "prefs.ini").write_bytes(b"external preference")
            return result

        monkeypatch.setattr(codec, "write_document", write)
    else:
        original = profilecopy.publish_new

        def publish(staged):
            offer.plan.destination.mkdir()
            (offer.plan.destination / "keep.txt").write_bytes(b"external destination")
            return original(staged)

        monkeypatch.setattr(profilecopy, "publish_new", publish)
    queued.run_next()
    assert_create_done(
        controller,
        offer,
        "create_failed" if phase == "encode" else "destination_exists",
    )
    if phase == "encode":
        assert (base.profile / "prefs.ini").read_bytes() == b"external preference"
        assert not offer.plan.destination.exists()
    else:
        assert {p.name: p.read_bytes() for p in offer.plan.destination.iterdir()} == {
            "keep.txt": b"external destination"
        }


@pytest.mark.parametrize("when", ["admission", "worker"])
def test_create_missing_codec_is_a_setup_refusal(setup, monkeypatch, when):
    controller, _, base = setup
    if when == "admission":
        assert review(controller, base)["ok"]
        offer = controller._setup_review
    else:
        offer, queued = queue_create(controller, base)
    monkeypatch.setattr(codec, "codec_available", lambda: False)
    if when == "admission":
        assert not controller.setup_create(offer.review_id, "create-1")["accepted"]
        assert controller._setup_review is offer
        assert not controller._eve_mutation.locked()
    else:
        queued.run_next()
        assert_create_done(controller, offer, "unsupported_setup")


@pytest.mark.parametrize("terminal", ["start-abort", "worker-abort", "done-port"])
def test_create_terminal_exits_release_mutation_without_replay(
    setup, monkeypatch, terminal
):
    controller, _, base = setup
    assert review(controller, base)["ok"]
    offer = controller._setup_review

    def abort(*args, **kwargs):
        raise KeyboardInterrupt()

    if terminal == "start-abort":
        controller._ports = replace(controller._ports, spawn=abort)
        with pytest.raises(KeyboardInterrupt):
            controller.setup_create(offer.review_id, "create-1")
        assert controller._setup_review is offer
        assert controller._done_pushes == []
    else:
        queued = QueuedThreads()
        controller._ports = replace(controller._ports, spawn=queued.spawn)
        assert controller.setup_create(offer.review_id, "create-1")["accepted"]
        if terminal == "worker-abort":
            monkeypatch.setattr(setup_profile, "stage_setup", abort)
            with pytest.raises(KeyboardInterrupt):
                queued.run_next()
        else:

            def done(payload):
                controller._done_pushes.append(payload)
                raise RuntimeError("completion transport unavailable")

            controller._ports = replace(controller._ports, publish_done=done)
            with pytest.raises(RuntimeError, match="completion transport"):
                queued.run_next()
        assert len(controller._done_pushes) == 1
        if terminal == "worker-abort":
            assert controller._done_pushes[0]["error_code"] == "create_failed"
            assert controller._done_pushes[0]["error"]
        assert not controller.setup_create(offer.review_id, "replay")["accepted"]
    assert controller._eve_mutation.acquire(blocking=False)
    controller._eve_mutation.release()


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("native", [False, True], ids=["classic", "native-keep"])
def test_create_real_native_transport_profile_from_distinct_synthetic_pair(
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
        account_names={"10": "Synthetic source", "20": "Synthetic recipient"},
        account_characters={"10": ["11"], "20": ["30"]},
    )
    text = (
        (Path(__file__).parent / "fixtures/ui_setup/native-complete.yaml").read_text(
            encoding="utf-8"
        )
        if native
        else export(controller, source)["text"]
    )
    before = files_under(base.root)
    if native:
        refused = review(controller, base, text)
        assert not refused["ok"] and refused["needs_label_choice"]
    assert review(controller, base, text, keep_ship_labels=native)["ok"]
    offer = controller._setup_review
    assert controller.setup_create(offer.review_id, "create-1")["accepted"]
    done = assert_create_done(controller, offer, published=True)
    assert done["selection_persisted"] and not done["warning"]
    created = offer.plan.destination
    assert {p: p.read_bytes() for p in before} == before
    assert {p.name for p in created.iterdir()} == {
        "core_user_20.dat",
        "core_char_30.dat",
        "core_public__.yaml",
        "prefs.ini",
    }
    account = codec.read_document(created / base.account_path.name)
    character = codec.read_document(created / base.character_path.name)
    original_account = codec.read_document(base.account_path)
    original_character = codec.read_document(base.character_path)
    assert account != original_account
    if native:
        assert value(account, "overview", "tabsByWindowInstanceID") == [list(range(8))]
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
    for name in ("prefs.ini", "core_public__.yaml"):
        assert (created / name).read_bytes() == before[base.profile / name]


@pytest.mark.parametrize("request_id", ["1", "x" * 128])
def test_create_api_completion_uses_client_correlation_and_existing_handler(
    setup, tmp_path, request_id
):
    original, _, base = setup
    api, _window = fakes.build_api(tmp_path, settings=original._settings)
    api._spawn = original._ports.spawn
    api._eve_profile_copy_refusal = lambda: None
    sent = fakes.record_pushes(api)
    reviewed = api.eve_settings_setup_review(
        setup_sharing.export_text(wire()),
        str(base.profile),
        str(base.account_path),
        str(base.character_path),
        "Imported",
    )
    assert reviewed["ok"], reviewed
    result = api.eve_settings_setup_create(reviewed["review_id"], request_id)
    assert result == {"accepted": True, "error": None}
    assert fakes.payloads(sent, "onEveSettingsDone") == [
        {
            "ok": True,
            "operation": "ui_setup_create",
            "request_id": request_id,
            "review_id": reviewed["review_id"],
            "published": True,
            "path": str(base.server / "settings_Imported"),
            "selection_persisted": True,
            "error_code": "",
            "error": "",
            "warning": "",
        }
    ]
    assert not api.eve_settings_setup_create(reviewed["review_id"], request_id)[
        "accepted"
    ]
    assert len(fakes.payloads(sent, "onEveSettingsDone")) == 1


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
