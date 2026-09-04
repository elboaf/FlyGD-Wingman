import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from wingman.evefittings import contracts, model, store
from wingman.evefittings.model import (
    CharacterSnapshot,
    Collection,
    FittingsState,
    Presence,
    SourceAlias,
    WriteIntent,
    new_library_entry,
    validate_remote_snapshot,
)
from wingman.evefittings.store import load_fittings, save_fittings

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def remote(*, fitting_id=10, ship_type_id=100, name="Fit", flag="HiSlot0"):
    return validate_remote_snapshot(
        [
            {
                "fitting_id": fitting_id,
                "ship_type_id": ship_type_id,
                "name": name,
                "description": f"Description for {name}",
                "items": [{"flag": flag, "quantity": 1, "type_id": 200}],
            }
        ]
    )[0]


def library_entry(*, entry_id="local-fit", fitting=None):
    return new_library_entry(fitting or remote(), entry_id=entry_id, now=NOW)


def presence(entry=None):
    entry = entry or library_entry()
    return Presence(
        character_id=42,
        remote_fitting_id=10,
        library_entry_id=entry.id,
        source_name="Observed",
        source_description="Observed description",
        source_template=entry.source_template,
        first_seen_utc=NOW - timedelta(days=2),
        discovered_batch_id="batch-20260901",
        last_confirmed_utc=NOW,
    )


def intent(
    status="unknown",
    *,
    operation_id="operation-1",
    entry=None,
    created_utc=NOW,
):
    entry = entry or library_entry()
    return WriteIntent(
        operation_id=operation_id,
        character_id=42,
        library_entry_id=entry.id,
        content=entry.content,
        status=status,
        created_utc=created_utc,
        sent_utc=created_utc if status != "planned" else None,
        completed_utc=created_utc if status in {"success", "failed"} else None,
        remote_fitting_id=99 if status == "success" else None,
        error="rejected" if status == "failed" else "",
    )


def assert_round_trip_closed(tmp_path, state):
    path = tmp_path / "recovered-round-trip.json"
    save_fittings(path, state)
    reloaded, warnings = load_fittings(path)
    assert reloaded == state
    assert warnings == ()


def full_state(*, intent_status="unknown"):
    entry = library_entry()
    return FittingsState(
        entries=(replace(entry, collection_ids=("alliance",)),),
        collections=(Collection("alliance", "Alliance"),),
        presences=(presence(entry),),
        snapshots=(
            CharacterSnapshot(
                character_id=42,
                fetched_utc=NOW,
                etag='"etag-value"',
                error="",
            ),
        ),
        intents=(intent(intent_status, entry=entry),),
    )


def test_round_trip_preserves_stable_ids_templates_aliases_and_collections(tmp_path):
    path = tmp_path / "eve_fittings.json"
    original = full_state()

    save_fittings(path, original)
    loaded, warnings = load_fittings(path)

    assert loaded == original
    assert warnings == ()
    assert loaded.entries[0].id == "local-fit"
    assert loaded.entries[0].source_template == original.entries[0].source_template
    assert (
        loaded.entries[0].deployment_template == original.entries[0].deployment_template
    )
    assert loaded.entries[0].aliases == original.entries[0].aliases
    assert loaded.entries[0].collection_ids == ("alliance",)
    assert loaded.entries[0].is_unfiled is False


def test_round_trip_preserves_invalid_source_without_deployment_template(tmp_path):
    path = tmp_path / "eve_fittings.json"
    entry = library_entry(fitting=remote(flag="Invalid"))
    assert entry.deployment_template is None

    save_fittings(path, FittingsState(entries=(entry,)))
    loaded, warnings = load_fittings(path)

    assert warnings == ()
    assert loaded.entries[0].source_template[0].flag == "Invalid"
    assert loaded.entries[0].deployment_template is None


def test_load_does_not_recompute_versioned_fingerprint_identity(tmp_path):
    path = tmp_path / "eve_fittings.json"
    entry = replace(library_entry(), fingerprint_version=77, digest="legacy-digest")
    save_fittings(path, FittingsState(entries=(entry,)))

    loaded, _ = load_fittings(path)

    assert loaded.entries[0].id == entry.id
    assert loaded.entries[0].fingerprint_version == 77
    assert loaded.entries[0].digest == "legacy-digest"


def test_presence_retains_discovery_and_confirmation_facts(tmp_path):
    path = tmp_path / "eve_fittings.json"
    original = full_state()

    save_fittings(path, original)
    loaded, _ = load_fittings(path)

    assert loaded.presences[0].first_seen_utc == NOW - timedelta(days=2)
    assert loaded.presences[0].discovered_batch_id == "batch-20260901"
    assert loaded.presences[0].last_confirmed_utc == NOW


def test_snapshot_round_trip_preserves_authoritative_content_time(tmp_path):
    path = tmp_path / "eve_fittings.json"
    content_utc = NOW - timedelta(minutes=5)
    original = replace(
        full_state(),
        snapshots=(replace(full_state().snapshots[0], content_utc=content_utc),),
    )

    save_fittings(path, original)
    document = json.loads(path.read_text(encoding="utf-8"))
    loaded, warnings = load_fittings(path)

    assert document["snapshots"][0]["content_utc"] == content_utc.isoformat()
    assert loaded.snapshots[0].content_utc == content_utc
    assert warnings == ()


def test_legacy_snapshot_without_content_time_falls_back_to_fetch_time(tmp_path):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["snapshots"][0].pop("content_utc", None)
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert loaded.snapshots[0].content_utc == loaded.snapshots[0].fetched_utc
    assert warnings == ()


def test_inconsistent_content_time_loads_conservatively_and_remains_resavable(
    tmp_path,
):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["snapshots"][0]["content_utc"] = (NOW + timedelta(minutes=5)).isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, _warnings = load_fittings(path)

    snapshot = loaded.snapshots[0]
    assert snapshot.content_utc == snapshot.fetched_utc == NOW
    save_fittings(path, loaded)
    assert load_fittings(path)[0] == loaded


def test_content_time_without_fetch_time_loads_as_unfetched_and_resavable(tmp_path):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["snapshots"][0]["fetched_utc"] = ""
    document["snapshots"][0]["content_utc"] = NOW.isoformat()
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, _warnings = load_fittings(path)

    snapshot = loaded.snapshots[0]
    assert snapshot.fetched_utc is None
    assert snapshot.content_utc is None
    save_fittings(path, loaded)
    assert load_fittings(path)[0] == loaded


def test_authoritative_snapshot_and_unresolved_intent_are_separate_overlays(tmp_path):
    path = tmp_path / "eve_fittings.json"
    original = full_state()

    save_fittings(path, original)
    document = json.loads(path.read_text(encoding="utf-8"))
    loaded, _ = load_fittings(path)

    assert set(document) >= {"presences", "snapshots", "intents"}
    assert loaded.presences == original.presences
    assert loaded.snapshots == original.snapshots
    assert loaded.intents == original.intents


def test_startup_converts_in_flight_to_unknown(tmp_path):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state(intent_status="in_flight"))

    loaded, _ = load_fittings(path)

    assert loaded.intents[0].status == "unknown"
    assert loaded.intents[0].completed_utc is None


def test_completed_history_prunes_oldest_first_but_unresolved_never_prunes(tmp_path):
    path = tmp_path / "eve_fittings.json"
    entry = library_entry()
    completed = tuple(
        intent(
            "failed",
            operation_id=f"completed-{index}",
            entry=entry,
            created_utc=NOW + timedelta(seconds=index),
        )
        for index in range(205)
    )
    unresolved = tuple(
        intent(
            "unknown",
            operation_id=f"unknown-{index}",
            entry=entry,
            created_utc=NOW + timedelta(seconds=1000 + index),
        )
        for index in range(205)
    )

    save_fittings(
        path,
        FittingsState(entries=(entry,), intents=(*completed, *unresolved)),
    )
    loaded, _ = load_fittings(path)

    completed_ids = [
        item.operation_id for item in loaded.intents if not item.unresolved
    ]
    unresolved_ids = [item.operation_id for item in loaded.intents if item.unresolved]
    assert completed_ids == [f"completed-{index}" for index in range(5, 205)]
    assert unresolved_ids == [f"unknown-{index}" for index in range(205)]


def test_save_builds_the_supersession_index_once(tmp_path, monkeypatch):
    path = tmp_path / "eve_fittings.json"
    entries = tuple(library_entry(entry_id=f"fit-{index}") for index in range(300))
    entries = tuple(
        replace(
            entry,
            superseded_by=entries[index + 1].id if index + 1 < len(entries) else None,
        )
        for index, entry in enumerate(entries)
    )
    original_index = model._index_entries
    index_calls = 0

    def counted_index(rows):
        nonlocal index_calls
        index_calls += 1
        return original_index(rows)

    monkeypatch.setattr(model, "_index_entries", counted_index)

    save_fittings(path, FittingsState(entries=entries))

    assert index_calls == 1


def test_save_validates_parsed_aliases_without_round_trip_serialization(
    tmp_path, monkeypatch
):
    path = tmp_path / "eve_fittings.json"
    original_alias_to_dict = store._alias_to_dict
    alias_serializations = 0

    def counted_alias_to_dict(alias):
        nonlocal alias_serializations
        alias_serializations += 1
        return original_alias_to_dict(alias)

    monkeypatch.setattr(store, "_alias_to_dict", counted_alias_to_dict)

    save_fittings(path, full_state())

    assert alias_serializations == 1


def test_save_refuses_library_and_collection_growth_without_replacing_primary(tmp_path):
    path = tmp_path / "eve_fittings.json"
    original = full_state()
    save_fittings(path, original)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="library entries"):
        save_fittings(
            path,
            FittingsState(
                entries=tuple(
                    library_entry(entry_id=f"fit-{index}")
                    for index in range(contracts.MAX_LIBRARY_ENTRIES + 1)
                )
            ),
        )
    assert path.read_bytes() == before

    with pytest.raises(ValueError, match="collections"):
        save_fittings(
            path,
            replace(
                original,
                collections=tuple(
                    Collection(f"collection-{index}", f"Collection {index}")
                    for index in range(contracts.MAX_COLLECTIONS + 1)
                ),
            ),
        )
    assert path.read_bytes() == before


def test_save_refuses_alias_growth_instead_of_evicting_curated_state(tmp_path):
    path = tmp_path / "eve_fittings.json"
    base = library_entry()
    aliases = tuple(
        SourceAlias(f"Alias {index}", "", base.source_template)
        for index in range(contracts.MAX_ALIASES_PER_ENTRY + 1)
    )

    with pytest.raises(ValueError, match="aliases"):
        save_fittings(path, FittingsState(entries=(replace(base, aliases=aliases),)))
    assert not path.exists()


def test_save_refuses_encoded_state_over_file_bound_before_rotating_primary(
    tmp_path, monkeypatch
):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, FittingsState())
    before = path.read_bytes()
    monkeypatch.setattr(contracts, "MAX_STATE_BYTES", len(before) + 1)

    with pytest.raises(ValueError, match="state limit"):
        save_fittings(path, full_state())

    assert path.read_bytes() == before
    assert not path.with_name(path.name + ".bak").exists()


def test_recovery_writeback_failure_still_returns_loaded_backup(tmp_path, monkeypatch):
    path = tmp_path / "eve_fittings.json"
    expected = full_state()
    save_fittings(path, expected)
    document = json.loads(path.read_text(encoding="utf-8"))
    compact = json.dumps(document, separators=(",", ":"))
    path.with_name(path.name + ".bak").write_text(compact, encoding="utf-8")
    path.unlink()
    monkeypatch.setattr(contracts, "MAX_STATE_BYTES", len(compact.encode("utf-8")))

    loaded, warnings = load_fittings(path)

    assert loaded == expected
    assert any("could not be saved" in warning for warning in warnings)


def test_save_rejects_terminal_intent_content_that_does_not_match_its_entry(
    tmp_path,
):
    path = tmp_path / "eve_fittings.json"
    entry = library_entry()
    different = library_entry(entry_id="different", fitting=remote(ship_type_id=101))
    mismatched = replace(intent("failed", entry=entry), content=different.content)

    with pytest.raises(ValueError, match="intent content"):
        save_fittings(path, FittingsState(entries=(entry,), intents=(mismatched,)))


@pytest.mark.parametrize("status", ["in_flight", "unknown"])
@pytest.mark.parametrize("damage", ["missing", "mismatched"])
def test_tolerant_recovery_preserves_and_resaves_unresolved_orphan_intents(
    tmp_path, status, damage
):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state(intent_status=status))
    document = json.loads(path.read_text(encoding="utf-8"))
    if damage == "missing":
        document["entries"][0] = {"id": "broken"}
    else:
        document["intents"][0]["content"]["ship_type_id"] = 101
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert len(loaded.intents) == 1
    assert loaded.intents[0].status == "unknown"
    assert loaded.intents[0].content.ship_type_id == (
        101 if damage == "mismatched" else 100
    )
    assert any("unresolved" in warning and damage in warning for warning in warnings)
    assert_round_trip_closed(tmp_path, loaded)


@pytest.mark.parametrize("status", ["success", "failed"])
@pytest.mark.parametrize("damage", ["missing", "mismatched"])
def test_tolerant_recovery_drops_terminal_orphan_history_with_warning(
    tmp_path, status, damage
):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state(intent_status=status))
    document = json.loads(path.read_text(encoding="utf-8"))
    if damage == "missing":
        document["entries"][0] = {"id": "broken"}
    else:
        document["intents"][0]["content"]["ship_type_id"] = 101
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert loaded.intents == ()
    assert any("terminal" in warning and damage in warning for warning in warnings)
    assert_round_trip_closed(tmp_path, loaded)


def test_orphan_normalization_keeps_distinct_character_content_safety_keys(tmp_path):
    path = tmp_path / "eve_fittings.json"
    first = library_entry(entry_id="first")
    second = library_entry(entry_id="second", fitting=remote(ship_type_id=101))
    intents = (
        intent("unknown", operation_id="same-operation", entry=first),
        intent("unknown", operation_id="same-operation", entry=second),
    )
    save_fittings(path, FittingsState(entries=(first, second), intents=intents))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["entries"] = [{"broken": True}, {"broken": True}]
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert len(loaded.intents) == 2
    assert {item.content for item in loaded.intents} == {first.content, second.content}
    assert warnings
    assert_round_trip_closed(tmp_path, loaded)


def test_save_allows_unresolved_intent_to_outlive_its_library_entry(tmp_path):
    path = tmp_path / "eve_fittings.json"
    unresolved = intent("unknown")

    save_fittings(path, FittingsState(intents=(unresolved,)))
    loaded, warnings = load_fittings(path)

    assert loaded.intents == (replace(unresolved, library_entry_id=""),)
    assert warnings == ()


@pytest.mark.parametrize(
    "damage",
    [
        "invalid_entry",
        "invalid_collection",
        "invalid_presence",
        "invalid_snapshot",
        "invalid_intent",
        "duplicate_entry",
        "duplicate_collection",
        "duplicate_presence",
        "duplicate_snapshot",
        "duplicate_intent",
        "invalid_alias",
        "unaggregated_intent_content",
    ],
)
def test_every_tolerant_row_recovery_is_round_trip_closed(tmp_path, damage):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state())
    document = json.loads(path.read_text(encoding="utf-8"))
    target = damage.removeprefix("invalid_").removeprefix("duplicate_")
    collection_name = {
        "entry": "entries",
        "collection": "collections",
        "presence": "presences",
        "snapshot": "snapshots",
        "intent": "intents",
    }.get(target)
    if damage == "invalid_alias":
        document["entries"][0]["aliases"].append({"name": "broken"})
    elif damage == "unaggregated_intent_content":
        duplicate = document["intents"][0]["content"]["items"][0].copy()
        duplicate["quantity"] = 2
        document["intents"][0]["content"]["items"].append(duplicate)
    elif damage.startswith("invalid_"):
        document[collection_name].append({"broken": True})
    else:
        document[collection_name].append(document[collection_name][0].copy())
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert warnings
    assert_round_trip_closed(tmp_path, loaded)


def test_syntactically_valid_local_corruption_drops_only_bad_rows_with_warning(
    tmp_path,
):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["entries"].append({"id": "broken"})
    document["presences"].append({"character_id": True})
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert [entry.id for entry in loaded.entries] == ["local-fit"]
    assert loaded.presences == full_state().presences
    assert any("entry" in warning and "dropped" in warning for warning in warnings)
    assert any("presence" in warning and "dropped" in warning for warning in warnings)
    assert_round_trip_closed(tmp_path, loaded)


def test_local_alias_overflow_is_trimmed_deterministically_with_warning(tmp_path):
    path = tmp_path / "eve_fittings.json"
    save_fittings(path, full_state())
    document = json.loads(path.read_text(encoding="utf-8"))
    template = document["entries"][0]["aliases"][0]["source_template"]
    document["entries"][0]["aliases"] = [
        {"name": f"Alias {index:03}", "description": "", "source_template": template}
        for index in reversed(range(105))
    ]
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert len(loaded.entries[0].aliases) == contracts.MAX_ALIASES_PER_ENTRY
    assert loaded.entries[0].aliases[0].name == "Alias 000"
    assert loaded.entries[0].aliases[-1].name == "Alias 099"
    assert any("aliases" in warning and "retained" in warning for warning in warnings)
    assert_round_trip_closed(tmp_path, loaded)


def test_dangling_collections_and_invalid_supersession_are_recovered_locally(tmp_path):
    path = tmp_path / "eve_fittings.json"
    old = library_entry(entry_id="old")
    new = library_entry(entry_id="new")
    save_fittings(path, FittingsState(entries=(old, new)))
    document = json.loads(path.read_text(encoding="utf-8"))
    document["entries"][0]["collection_ids"] = ["missing"]
    document["entries"][0]["superseded_by"] = "new"
    document["entries"][1]["superseded_by"] = "old"
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert loaded.entries[0].collection_ids == ()
    assert all(entry.superseded_by is None for entry in loaded.entries)
    assert any("collection" in warning for warning in warnings)
    assert any("supersession" in warning for warning in warnings)
    assert_round_trip_closed(tmp_path, loaded)


def test_corrupt_primary_is_preserved_and_recovered_from_backup(tmp_path):
    path = tmp_path / "eve_fittings.json"
    expected = full_state()
    save_fittings(path, expected)
    save_fittings(path, expected)
    path.write_text("not json", encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert loaded == expected
    assert any("recovered" in warning.lower() for warning in warnings)
    assert list(tmp_path.glob("eve_fittings.json.corrupt-*"))
    assert json.loads(path.read_text(encoding="utf-8"))["entries"]


@pytest.mark.parametrize("primary_state", ["missing", "corrupt"])
def test_backup_read_retries_once_after_transient_oserror(
    tmp_path, monkeypatch, primary_state
):
    path = tmp_path / "eve_fittings.json"
    backup = path.with_name(path.name + ".bak")
    backup.write_text("{}", encoding="utf-8")
    if primary_state == "corrupt":
        path.write_text("not json", encoding="utf-8")
    expected = full_state()
    original_read = store._read_document
    backup_attempts = []
    sleeps = []

    def flaky_read(candidate):
        if candidate == backup:
            backup_attempts.append(candidate)
            if len(backup_attempts) == 1:
                raise PermissionError("temporarily shared")
            return expected, ()
        return original_read(candidate)

    monkeypatch.setattr(store, "_read_document", flaky_read)
    monkeypatch.setattr(store.time, "sleep", sleeps.append)

    loaded, warnings = load_fittings(path)

    assert loaded == expected
    assert len(backup_attempts) == 2
    assert sleeps == [0.05]
    assert any("recovered" in warning.lower() for warning in warnings)


@pytest.mark.parametrize("primary_state", ["missing", "corrupt"])
def test_backup_read_stops_after_one_retry(tmp_path, monkeypatch, primary_state):
    path = tmp_path / "eve_fittings.json"
    backup = path.with_name(path.name + ".bak")
    backup.write_text("{}", encoding="utf-8")
    if primary_state == "corrupt":
        path.write_text("not json", encoding="utf-8")
    original_read = store._read_document
    backup_attempts = []
    sleeps = []

    def blocked_read(candidate):
        if candidate == backup:
            backup_attempts.append(candidate)
            raise PermissionError("still shared")
        return original_read(candidate)

    monkeypatch.setattr(store, "_read_document", blocked_read)
    monkeypatch.setattr(store.time, "sleep", sleeps.append)

    loaded, warnings = load_fittings(path)

    assert loaded == FittingsState()
    assert len(backup_attempts) == 2
    assert sleeps == [0.05]
    assert warnings


def test_missing_primary_is_recovered_from_backup(tmp_path):
    path = tmp_path / "eve_fittings.json"
    expected = full_state()
    save_fittings(path, expected)
    save_fittings(path, expected)
    path.unlink()

    loaded, warnings = load_fittings(path)

    assert loaded == expected
    assert path.exists()
    assert any("missing" in warning.lower() for warning in warnings)


def test_inaccessible_backup_is_not_mistaken_for_first_launch(tmp_path, monkeypatch):
    path = tmp_path / "eve_fittings.json"
    backup = path.with_name(path.name + ".bak")
    backup.write_text("{}", encoding="utf-8")
    original_stat = type(path).stat

    def fail_backup_stat(candidate, *args, **kwargs):
        if candidate == backup:
            raise PermissionError("backup denied")
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(type(path), "stat", fail_backup_stat)

    loaded, warnings = load_fittings(path)

    assert loaded == FittingsState()
    assert any("could not be read" in warning for warning in warnings)


def test_oversized_primary_uses_corruption_recovery_without_reading_it(
    tmp_path, monkeypatch
):
    path = tmp_path / "eve_fittings.json"
    expected = full_state()
    save_fittings(path, expected)
    save_fittings(path, expected)
    backup_size = path.with_name(path.name + ".bak").stat().st_size
    monkeypatch.setattr(contracts, "MAX_STATE_BYTES", backup_size + 100)
    path.write_bytes(b"x" * (backup_size + 101))

    loaded, warnings = load_fittings(path)

    assert loaded == expected
    assert any("recovered" in warning.lower() for warning in warnings)


def test_unrecoverable_corrupt_state_returns_empty_and_preserves_evidence(tmp_path):
    path = tmp_path / "eve_fittings.json"
    path.write_text("bad primary", encoding="utf-8")
    path.with_name(path.name + ".bak").write_text("bad backup", encoding="utf-8")

    loaded, warnings = load_fittings(path)

    assert loaded == FittingsState()
    assert warnings
    assert list(tmp_path.glob("eve_fittings.json.corrupt-*"))


def test_save_rejects_presence_referencing_a_missing_entry(tmp_path):
    path = tmp_path / "eve_fittings.json"

    with pytest.raises(ValueError, match="missing library entry"):
        save_fittings(path, FittingsState(presences=(presence(),)))


def test_state_is_immutable(tmp_path):
    state = full_state()

    with pytest.raises(FrozenInstanceError):
        state.entries = ()
