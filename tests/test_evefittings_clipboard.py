"""Reviewed local clipboard operations at real controller/store/I/O boundaries."""

import threading
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from tests.test_evefittings_inventory import PublicInventory
from tests.test_evefittings_store import full_state
from wingman.eveauth.controller import AuthorityController
from wingman.eveauth.state import AuthorityState
from wingman.evefittings import contracts, inventory, model, names, store
from wingman.evefittings.controller import FittingsController

NOW = datetime(2026, 9, 14, tzinfo=UTC)
TEXT = "[Rifter, Pasted]\nDamage Control II\n"
WARNINGS_TEXT = (
    "[Rifter, Reviewed]\n\n"
    "200mm AutoCannon II, Republic Fleet EMP S /offline\n"
    "Hobgoblin II x5\nRepublic Fleet EMP S x100\n"
)


def entry(*, entry_id="seed", name="Pasted", flag="LoSlot0", type_id=2048):
    return model.new_library_entry(
        model.RemoteFitting(123, 587, name, "", (model.RemoteItem(flag, type_id, 1),)),
        entry_id=entry_id,
        now=NOW,
    )


def make_controller(tmp_path, *, initial=None, client=None, authority=None, **kwargs):
    state_path = tmp_path / "eve_fittings.json"
    if initial is not None:
        store.save_fittings(state_path, initial)
    authority = authority or AuthorityController(
        state_path=tmp_path / "authority.json",
        authority=AuthorityState([]),
        now=lambda: NOW,
    )
    client = client or PublicInventory()
    controller = FittingsController(
        state_path=state_path,
        names_path=tmp_path / "names.json",
        authority=authority,
        client=client,
        now=lambda: NOW,
        **kwargs,
    )
    return controller, client, state_path


def add(controller, text=TEXT):
    review = controller.review_eft(text)
    assert review["ok"], review
    return controller.import_eft(review["review_id"])


def test_new_import_is_local_only_exact_and_reloadable(tmp_path):
    original = full_state()
    controller, client, path = make_controller(tmp_path, initial=original)

    def outside_state_lock():
        assert not controller._lock._is_owned()

    client.after_call = outside_state_lock
    review = controller.review_eft(TEXT)
    assert review == {
        "ok": True,
        "review_id": review["review_id"],
        "name": "Pasted",
        "ship_name": "Rifter",
        "items": [
            {
                "flag": "LoSlot0",
                "location": "low",
                "type_id": 2048,
                "type_name": "Damage Control II",
                "quantity": 1,
            }
        ],
        "warnings": [],
        "existing_entry_id": "",
        "error": "",
    }
    assert review["review_id"]
    assert controller.state == original  # Review never writes the library.
    result = controller.import_eft(review["review_id"])
    assert result == {
        "applied": True,
        "persisted": True,
        "entry_id": result["entry_id"],
        "created": True,
        "error": "",
    }
    imported = controller.state.entries[-1]
    assert imported.content == model.CanonicalContent(
        587, (model.CanonicalItem("low", 2048, 1),)
    )
    assert imported.source_template == (model.RemoteItem("LoSlot0", 2048, 1),)
    assert imported.deployment_template == imported.source_template
    assert imported.preferred_name == "Pasted"
    assert imported.preferred_description == ""
    assert imported.aliases == (
        model.SourceAlias("Pasted", "", imported.source_template),
    )
    assert imported.collection_ids == () and imported.superseded_by is None
    assert imported.created_utc == imported.updated_utc == NOW
    assert replace(controller.state, entries=original.entries) == original
    assert store.load_fittings(path) == (controller.state, ())
    assert all(call[1].startswith("/universe/") for call in client.calls)
    assert all("Pasted" not in str(call) for call in client.calls)
    assert controller._authority.characters == ()


def test_repeated_import_keeps_id_and_does_not_require_another_save(tmp_path):
    saves = []

    def save(path, state):
        saves.append(state)
        store.save_fittings(path, state)

    controller, client, _ = make_controller(tmp_path, save_state=save)
    first = add(controller)
    before = controller.state
    review = controller.review_eft(TEXT)
    assert review["existing_entry_id"] == first["entry_id"]
    calls = len(client.calls)
    second = controller.import_eft(review["review_id"])
    assert second == {**first, "created": False}
    assert controller.state == before
    assert len(saves) == 1 and len(client.calls) == calls
    assert not controller.import_eft(review["review_id"])["applied"]


def test_alias_import_preserves_curated_metadata_templates_membership_and_supersession(
    tmp_path,
):
    seeded = entry(flag="LoSlot3", name="Original")
    target = entry(entry_id="successor", type_id=2889, flag="HiSlot0")
    curated = replace(
        seeded,
        preferred_name="Curated",
        preferred_description="Notes",
        collection_ids=("doctrine",),
        superseded_by=target.id,
    )
    initial = model.FittingsState(
        entries=(curated, target),
        collections=(model.Collection("doctrine", "Doctrine"),),
    )
    controller, _, path = make_controller(tmp_path, initial=initial)
    result = add(controller)
    assert result["entry_id"] == curated.id and not result["created"]
    actual = controller.state.entries[0]
    assert (
        replace(actual, aliases=curated.aliases, updated_utc=curated.updated_utc)
        == curated
    )
    assert (
        model.SourceAlias("Pasted", "", (model.RemoteItem("LoSlot0", 2048, 1),))
        in actual.aliases
    )
    assert store.load_fittings(path) == (controller.state, ())


@pytest.mark.parametrize("collision", [False, True])
def test_dedup_checks_full_content_and_retained_fingerprint_versions(
    tmp_path, monkeypatch, collision
):
    if collision:
        monkeypatch.setattr(model, "_digest", lambda _text: "collision")
    seed = entry(type_id=2889, flag="HiSlot0") if collision else entry()
    seed = replace(
        seed, fingerprint_version=77, digest=model.fingerprint(seed.content, version=77)
    )
    controller, _, _ = make_controller(
        tmp_path, initial=model.FittingsState(entries=(seed,))
    )
    result = add(controller)
    assert result["created"] is collision
    assert len(controller.state.entries) == (2 if collision else 1)
    if not collision:
        assert controller.state.entries[0] == seed


def test_import_deduplicates_content_that_arrived_after_review(tmp_path):
    from tests.test_evefittings_lifecycle import _authority
    from wingman.eveesi import EsiResponse

    class RefreshInventory(PublicInventory):
        def get(self, path, *, token=None, etag=None):
            if path == "/characters/42/fittings":
                assert token == "access-42"
                return EsiResponse(
                    200,
                    [
                        {
                            "fitting_id": 10,
                            "ship_type_id": 587,
                            "name": "Remote",
                            "description": "Remote notes",
                            "items": [
                                {"flag": "LoSlot2", "type_id": 2048, "quantity": 1}
                            ],
                        }
                    ],
                    "",
                    "",
                    "GET",
                    path,
                )
            return super().get(path, token=token)

    controller, _, _ = make_controller(
        tmp_path, client=RefreshInventory(), authority=_authority(tmp_path)
    )
    review = controller.review_eft(TEXT)
    assert controller.refresh([42])["ok"]
    before = controller.state
    result = controller.import_eft(review["review_id"])
    assert result["entry_id"] == before.entries[0].id and not result["created"]
    assert controller.state.presences == before.presences
    assert controller.state.snapshots == before.snapshots
    assert controller.state.intents == before.intents
    assert controller.state.entries[0].preferred_name == "Remote"


@pytest.mark.parametrize("initial_kind", ["new", "duplicate", "alias"])
@pytest.mark.parametrize("cache_save_fails", [False, True])
def test_verified_names_precede_notification_and_receipt_even_on_noop_and_cache_failure(
    tmp_path, monkeypatch, initial_kind, cache_save_fails
):
    seed = entry(name="Different" if initial_kind == "alias" else "Pasted")
    initial = None if initial_kind == "new" else model.FittingsState(entries=(seed,))
    if cache_save_fails:

        def fail(*_args):
            raise OSError("cosmetic disk failure")

        monkeypatch.setattr(names, "save", fail)
    observed = []
    controller, _, path = make_controller(tmp_path, initial=initial)

    def changed(payload):
        observed.append(
            (payload, controller.workspace(), controller.detail(payload["entry_id"]))
        )

    controller._changed = changed
    result = add(controller)
    assert result["applied"] and result["persisted"]
    assert observed
    for _, workspace, detail in observed:
        assert workspace["rows"][0]["ship_name"] == "Rifter"
        assert detail["ship_name"] == "Rifter"
        assert detail["items"][0]["type_name"] == "Damage Control II"
        assert workspace["characters"] == []
    assert (
        controller.detail(result["entry_id"])["items"][0]["type_name"]
        == "Damage Control II"
    )
    assert store.load_fittings(path) == (controller.state, ())


def test_verified_names_replace_stale_labels_even_when_display_cache_is_full(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(names, "MAX_ENTRIES", 2)
    cache = names.TypeNameCache({587: "Stale hull", 1: "Unrelated"})
    names.save(tmp_path / "names.json", cache)
    controller, _, _ = make_controller(tmp_path)
    result = add(controller)
    detail = controller.detail(result["entry_id"])
    assert detail["ship_name"] == "Rifter"
    assert detail["items"][0]["type_name"] == "Damage Control II"
    reloaded, warnings = names.load(tmp_path / "names.json")
    assert not warnings
    assert reloaded.type_names() == {587: "Rifter", 2048: "Damage Control II"}


def test_ticket_retains_warnings_and_names_after_resolver_eviction(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(inventory, "MAX_CACHED_TYPES", 2)
    seed = entry(entry_id="export-source")
    controller, client, _ = make_controller(
        tmp_path, initial=model.FittingsState(entries=(seed,))
    )
    review = controller.review_eft(WARNINGS_TEXT)
    ticket = controller._eft_review
    assert [(w["code"], w["line_number"]) for w in review["warnings"]] == [
        ("loaded_charge_omitted", 3),
        ("offline_omitted", 3),
        ("bay_convention", 4),
    ]
    assert all(w["message"] for w in review["warnings"])
    assert [row["type_id"] for row in review["items"]] == [2889, 2456, 21898]
    # Public export shares the resolver and evicts metadata without replacing Review.
    assert controller.export_eft(seed.id)["ok"]
    calls = len(client.calls)
    review["items"].clear()
    original_warning = ticket.candidate.warnings[0].message
    review["warnings"][0]["message"] = "browser tampering"
    assert ticket.candidate.warnings[0].message == original_warning
    with pytest.raises(FrozenInstanceError):
        ticket.candidate = None
    result = controller.import_eft(review["review_id"])
    assert result["created"] and len(client.calls) == calls
    detail = controller.detail(result["entry_id"])
    assert detail["ship_name"] == "Rifter"
    assert {row["type_name"] for row in detail["items"]} == {
        "200mm AutoCannon II",
        "Hobgoblin II",
        "Republic Fleet EMP S",
    }
    assert [(row["location"], row["quantity"]) for row in detail["items"]] == [
        ("Cargo", 100),
        ("DroneBay", 5),
        ("high", 1),
    ]


@pytest.mark.parametrize("name", ["Pasted", "Alias"])
def test_full_library_still_accepts_existing_content(tmp_path, monkeypatch, name):
    seed = entry()
    controller, _, path = make_controller(
        tmp_path, initial=model.FittingsState(entries=(seed,))
    )
    monkeypatch.setattr(contracts, "MAX_LIBRARY_ENTRIES", 1)
    result = add(controller, TEXT.replace("Pasted", name))
    assert (
        result["persisted"] and not result["created"] and result["entry_id"] == seed.id
    )
    assert len(controller.state.entries) == 1
    assert name in [alias.name for alias in controller.state.entries[0].aliases]
    assert store.load_fittings(path) == (controller.state, ())


@pytest.mark.parametrize("failure", ["disk", "validation", "full"])
def test_persistence_refusal_never_publishes_partial_import(
    tmp_path, monkeypatch, failure
):
    original = model.FittingsState(entries=(entry(type_id=2889, flag="HiSlot0"),))
    saved = []

    def save(path, state):
        saved.append(state)
        if failure == "disk":
            raise OSError("disk")
        if failure == "validation":
            raise ValueError("file size limit")
        store.save_fittings(path, state)

    controller, _, path = make_controller(tmp_path, initial=original, save_state=save)
    if failure == "full":
        monkeypatch.setattr(contracts, "MAX_LIBRARY_ENTRIES", 1)
    result = add(controller)
    assert result == {
        "applied": False,
        "persisted": False,
        "entry_id": "",
        "created": False,
        "error": result["error"],
    }
    assert result["error"]
    assert controller.state == original and store.load_fittings(path) == (original, ())
    if failure == "full":
        assert saved == []


@pytest.mark.parametrize("initial_kind", ["new", "alias"])
def test_failed_save_keeps_review_for_same_id_retry(tmp_path, initial_kind):
    saved = []

    def save(path, state):
        saved.append(state)
        if len(saved) == 1:
            raise OSError("transient disk refusal")
        store.save_fittings(path, state)

    initial = (
        None
        if initial_kind == "new"
        else model.FittingsState(entries=(entry(name="Curated"),))
    )
    controller, client, path = make_controller(
        tmp_path, initial=initial, save_state=save
    )
    review = controller.review_eft(TEXT)
    calls = len(client.calls)
    before = controller.state
    first = controller.import_eft(review["review_id"])
    assert not first["applied"] and not first["persisted"]
    assert controller.state == before

    retry = controller.import_eft(review["review_id"])

    assert retry["applied"] and retry["persisted"]
    assert retry["created"] is (initial_kind == "new")
    assert len(saved) == 2 and len(client.calls) == calls
    assert store.load_fittings(path) == (controller.state, ())
    assert not controller.import_eft(review["review_id"])["applied"]


@pytest.mark.parametrize("replacement", ["invalid", TEXT.replace("Pasted", "New")])
def test_retry_never_restores_review_invalidated_during_failed_save(
    tmp_path, replacement
):
    retry_started, release_retry = threading.Event(), threading.Event()
    saved = []

    def save(_path, state):
        saved.append(state)
        if len(saved) == 2:
            retry_started.set()
            assert release_retry.wait(3)
        raise OSError("disk still unavailable")

    controller, _, _ = make_controller(tmp_path, save_state=save)
    review_id = controller.review_eft(TEXT)["review_id"]
    assert not controller.import_eft(review_id)["persisted"]
    results = []
    worker = threading.Thread(
        target=lambda: results.append(controller.import_eft(review_id))
    )
    worker.start()
    try:
        assert retry_started.wait(2), "the same review must reach the writer on retry"
        assert not controller.review_eft(replacement)["ok"]  # Busy still invalidates.
    finally:
        release_retry.set()
        worker.join(3)
    assert not worker.is_alive() and not results[0]["persisted"]
    assert not controller.import_eft(review_id)["applied"]
    assert len(saved) == 2 and controller.state.entries == ()


def test_store_file_size_limit_refuses_import_without_replacing_disk_or_memory(
    tmp_path, monkeypatch
):
    original = model.FittingsState(entries=(entry(type_id=2889, flag="HiSlot0"),))
    controller, _, path = make_controller(tmp_path, initial=original)
    before = path.read_bytes()
    monkeypatch.setattr(contracts, "MAX_STATE_BYTES", len(before))
    result = add(controller)
    assert not result["persisted"] and not result["applied"] and result["error"]
    assert controller.state == original
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "replacement", [None, "garbage", TEXT.replace("Pasted", "New review")]
)
def test_expired_or_replaced_review_cannot_commit(tmp_path, replacement):
    clock = [10.0]
    controller, _, _ = make_controller(tmp_path, monotonic=lambda: clock[0])
    review = controller.review_eft(TEXT)
    if replacement is None:
        clock[0] += 15 * 60
    else:
        controller.review_eft(replacement)
    assert not controller.import_eft(review["review_id"])["applied"]
    assert controller.state.entries == ()


@pytest.mark.parametrize(
    "text", [None, {}, "bad", "[Rifter, Name]\nUnknown inventory", "x" * 65537]
)
def test_review_refusal_has_no_actionable_partial_payload(tmp_path, text):
    controller, _, _ = make_controller(tmp_path)
    result = controller.review_eft(text)
    assert result == {
        "ok": False,
        "review_id": "",
        "name": "",
        "ship_name": "",
        "items": [],
        "warnings": [],
        "existing_entry_id": "",
        "error": result["error"],
    }
    assert result["error"] and controller.state.entries == ()


@pytest.mark.parametrize("review_id", [None, {}, "", "invented"])
def test_add_accepts_only_a_live_review_id(tmp_path, review_id):
    controller, _, _ = make_controller(tmp_path)
    assert not controller.import_eft(review_id)["applied"]
    assert controller.state.entries == ()


def test_export_uses_saved_preferred_name_and_has_no_library_side_effects(tmp_path):
    seed = replace(entry(name="Curated"), preferred_description="Private notes")
    controller, _, _ = make_controller(
        tmp_path, initial=model.FittingsState(entries=(seed,))
    )
    before = controller.state
    assert controller.export_eft(seed.id) == {
        "ok": True,
        "text": "[Rifter, Curated]\n\nDamage Control II\n",
        "error": "",
    }
    assert controller.state == before
    assert controller.export_eft("missing")["text"] == ""
    assert controller.export_eft({})["ok"] is False


@pytest.mark.parametrize("mutation", ["rename", "delete"])
def test_export_rechecks_source_after_public_resolution(tmp_path, mutation):
    seed = entry()
    client = PublicInventory()
    controller, _, _ = make_controller(
        tmp_path, client=client, initial=model.FittingsState(entries=(seed,))
    )
    changed = []

    def after_call():
        if changed:
            return
        changed.append(True)
        assert not controller._lock._is_owned()
        if mutation == "rename":
            assert controller.update_metadata(seed.id, "Renamed", "")
        else:
            assert controller.delete_entry(seed.id)

    client.after_call = after_call
    result = controller.export_eft(seed.id)
    assert result["ok"] is False and result["text"] == "" and result["error"]


class BlockingResolver:
    """Delayed external resolution that deliberately ignores the stop callback."""

    def __init__(self, *, client=None):
        self.real = inventory.InventoryResolver(
            client or PublicInventory(), stopping=lambda: False
        )
        self.started = threading.Event()
        self.release = threading.Event()

    def for_import(self, parsed):
        self.started.set()
        assert self.release.wait(3)
        return self.real.for_import(parsed)

    def for_export(self, entry):
        self.started.set()
        assert self.release.wait(3)
        return self.real.for_export(entry)


def test_busy_new_review_invalidates_even_an_inflight_review(tmp_path):
    resolver = BlockingResolver()
    controller, _, _ = make_controller(tmp_path, resolver=resolver)
    results = []
    thread = threading.Thread(
        target=lambda: results.append(controller.review_eft(TEXT))
    )
    thread.start()
    assert resolver.started.wait(2)
    try:
        assert not controller.review_eft("invalid new review")["ok"]
        assert not controller.import_eft("anything")["applied"]
        assert not controller.export_eft("anything")["ok"]
    finally:
        resolver.release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert not results[0]["ok"] and results[0]["review_id"] == ""
    assert controller.state.entries == ()


def test_busy_review_attempt_invalidates_ready_ticket_while_export_is_running(tmp_path):
    resolver = BlockingResolver()
    resolver.release.set()
    controller, _, _ = make_controller(
        tmp_path, resolver=resolver, initial=model.FittingsState(entries=(entry(),))
    )
    review = controller.review_eft(TEXT)
    resolver.release.clear()
    resolver.started.clear()
    results = []
    worker = threading.Thread(
        target=lambda: results.append(controller.export_eft("seed"))
    )
    worker.start()
    assert resolver.started.wait(2)
    try:
        assert not controller.review_eft("not valid")["ok"]
    finally:
        resolver.release.set()
        worker.join(3)
    assert results[0]["ok"] and not worker.is_alive()
    assert not controller.import_eft(review["review_id"])["applied"]
    assert len(controller.state.entries) == 1


def test_double_submission_during_save_is_refused_not_queued(tmp_path):
    started, release = threading.Event(), threading.Event()

    def save(path, state):
        started.set()
        assert release.wait(3)
        store.save_fittings(path, state)

    controller, _, _ = make_controller(tmp_path, save_state=save)
    review_id = controller.review_eft(TEXT)["review_id"]
    results = []
    thread = threading.Thread(
        target=lambda: results.append(controller.import_eft(review_id))
    )
    thread.start()
    assert started.wait(2)
    try:
        assert not controller.import_eft(review_id)["applied"]
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive() and results[0]["created"]
    assert len(controller.state.entries) == 1


@pytest.mark.parametrize("target_index", [99, 100, 199, 200])
@pytest.mark.parametrize("mutation", ["rename", "insert", "delete"])
def test_locate_projects_target_from_same_snapshot_across_page_boundaries(
    tmp_path, target_index, mutation
):
    from types import SimpleNamespace

    entries = tuple(
        entry(entry_id=f"fit-{i:03}", name=f"Fit {i:03}") for i in range(201)
    )
    target = entries[target_index]
    triggered = []

    class RacingAuthority:
        @property
        def characters(self):
            assert not controller._lock._is_owned()
            return (
                SimpleNamespace(
                    character_id=42, character_name="Pilot", persistence_error=""
                ),
            )

        def capability_status(self, character_id, capability):
            assert not controller._lock._is_owned()
            if not triggered:
                triggered.append(True)
                if mutation == "rename":
                    assert controller.update_metadata(target.id, "AAA", "")
                elif mutation == "insert":
                    assert add(controller, "[Rifter, AAA]\n1MN Afterburner II")[
                        "created"
                    ]
                else:
                    assert controller.delete_entry(target.id)
            return "missing"

    controller, _, _ = make_controller(
        tmp_path,
        initial=model.FittingsState(entries=entries),
        authority=RacingAuthority(),
    )
    result = controller.locate_entry(target.id)
    assert result["ok"] and result["entry_id"] == target.id and not result["error"]
    workspace = result["workspace"]
    assert triggered
    assert workspace["page"] == target_index // 100 + 1
    assert workspace["filters"] == {
        "collection_id": "all",
        "search": "",
        "ship_type_id": None,
    }
    assert workspace["total"] == 201
    row = next(row for row in workspace["rows"] if row["id"] == target.id)
    assert row["name"] == target.preferred_name
    assert workspace["rows"][0]["id"] == f"fit-{target_index // 100 * 100:03}"


@pytest.mark.parametrize("mutation", ["rename", "insert", "delete"])
def test_locate_does_not_calculate_page_before_authority_boundary_then_reread_state(
    tmp_path, mutation
):
    entries = tuple(
        entry(entry_id=f"fit-{i:03}", name=f"Fit {i:03}") for i in range(201)
    )
    target = entries[99 if mutation == "insert" else 100]
    triggered = []

    class RacingAuthority:
        @property
        def characters(self):
            assert not controller._lock._is_owned()
            if not triggered:
                triggered.append(True)
                if mutation == "rename":
                    assert controller.update_metadata(target.id, "AAA", "")
                elif mutation == "insert":
                    assert add(controller, "[Rifter, AAA]\n1MN Afterburner II")[
                        "created"
                    ]
                else:
                    assert controller.delete_entry(target.id)
            return ()

    controller, _, _ = make_controller(
        tmp_path,
        initial=model.FittingsState(entries=entries),
        authority=RacingAuthority(),
    )
    result = controller.locate_entry(target.id)
    assert triggered
    if mutation == "delete":
        assert not result["ok"] and result["workspace"] is None
    else:
        assert result["ok"]
        assert result["workspace"]["page"] == (2 if mutation == "insert" else 1)
        assert target.id in [row["id"] for row in result["workspace"]["rows"]]


@pytest.mark.parametrize("entry_id", [None, {}, "", "deleted"])
def test_locate_refusal_has_null_workspace(tmp_path, entry_id):
    controller, _, _ = make_controller(tmp_path)
    result = controller.locate_entry(entry_id)
    assert result == {
        "ok": False,
        "entry_id": "",
        "workspace": None,
        "error": result["error"],
    }
    assert result["error"]
