import json
import pathlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from wingman import evefittings
from wingman.evefittings import model
from wingman.evefittings.model import (
    CanonicalContent,
    CanonicalItem,
    Collection,
    LibraryEntry,
    RemoteFitting,
    SourceAlias,
    canonical_equal,
    canonicalize,
    deployment_template,
    fingerprint,
    new_library_entry,
    normalized_name_key,
    retain_aliases,
    validate_remote_snapshot,
    validate_supersession,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "evefittings"
NOW = datetime(2026, 9, 3, tzinfo=UTC)


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def remote(*, ship=100, fitting_id=1, name="Fit", description="", items=None):
    return {
        "fitting_id": fitting_id,
        "ship_type_id": ship,
        "name": name,
        "description": description,
        "items": items
        if items is not None
        else [{"flag": "HiSlot0", "quantity": 1, "type_id": 200}],
    }


def content_for(type_id, *, location="high", quantity=1, ship=100):
    return CanonicalContent(
        ship_type_id=ship,
        items=(CanonicalItem(location, type_id, quantity),),
    )


def entry(entry_id, content, *, superseded_by=None):
    source = validate_remote_snapshot(
        [
            remote(
                ship=content.ship_type_id,
                items=[
                    {
                        "flag": "HiSlot0",
                        "quantity": content.items[0].quantity,
                        "type_id": content.items[0].type_id,
                    }
                ],
            )
        ]
    )[0]
    return replace(
        new_library_entry(source, entry_id=entry_id, now=NOW),
        superseded_by=superseded_by,
    )


def test_numbered_slot_order_is_equivalent():
    left, right = validate_remote_snapshot(fixture("get-equivalent-slots.json"))

    assert canonicalize(left) == canonicalize(right)
    assert fingerprint(canonicalize(left)) == fingerprint(canonicalize(right))
    assert left.items != right.items


def test_canonicalization_normalizes_each_numbered_rack_but_not_bays():
    fitting = validate_remote_snapshot(
        [
            remote(
                items=[
                    {"flag": "HiSlot7", "quantity": 1, "type_id": 1},
                    {"flag": "MedSlot6", "quantity": 1, "type_id": 2},
                    {"flag": "LoSlot5", "quantity": 1, "type_id": 3},
                    {"flag": "RigSlot2", "quantity": 1, "type_id": 4},
                    {"flag": "SubSystemSlot3", "quantity": 1, "type_id": 5},
                    {"flag": "ServiceSlot7", "quantity": 1, "type_id": 6},
                    {"flag": "Cargo", "quantity": 1, "type_id": 7},
                    {"flag": "DroneBay", "quantity": 1, "type_id": 7},
                    {"flag": "FighterBay", "quantity": 1, "type_id": 7},
                ]
            )
        ]
    )[0]

    assert canonicalize(fitting).key() == (
        100,
        (
            ("Cargo", 7, 1),
            ("DroneBay", 7, 1),
            ("FighterBay", 7, 1),
            ("high", 1, 1),
            ("low", 3, 1),
            ("medium", 2, 1),
            ("rig", 4, 1),
            ("service", 6, 1),
            ("subsystem", 5, 1),
        ),
    )


def test_duplicate_canonical_rows_aggregate_and_sort_deterministically():
    first, second = validate_remote_snapshot(
        [
            remote(
                fitting_id=1,
                items=[
                    {"flag": "HiSlot7", "quantity": 2, "type_id": 300},
                    {"flag": "Cargo", "quantity": 4, "type_id": 400},
                    {"flag": "HiSlot0", "quantity": 3, "type_id": 300},
                ],
            ),
            remote(
                fitting_id=2,
                items=[
                    {"flag": "HiSlot2", "quantity": 5, "type_id": 300},
                    {"flag": "Cargo", "quantity": 4, "type_id": 400},
                ],
            ),
        ]
    )

    assert canonicalize(first) == canonicalize(second)
    assert canonicalize(first).key() == (
        100,
        (("Cargo", 400, 4), ("high", 300, 5)),
    )


@pytest.mark.parametrize(
    ("changed", "value"),
    [
        ("flag", "MedSlot0"),
        ("flag", "Cargo"),
        ("flag", "DroneBay"),
        ("flag", "FighterBay"),
        ("type_id", 201),
        ("quantity", 2),
    ],
)
def test_rack_bay_type_and_quantity_differences_remain_identity(changed, value):
    base = remote(items=[{"flag": "HiSlot0", "quantity": 1, "type_id": 200}])
    different = json.loads(json.dumps(base))
    different["fitting_id"] = 2
    different["items"][0][changed] = value
    left, right = validate_remote_snapshot([base, different])

    assert not canonical_equal(canonicalize(left), canonicalize(right))


def test_charges_and_scripts_remain_distinct_content_rows():
    module_only, with_charge, with_script = validate_remote_snapshot(
        [
            remote(fitting_id=1),
            remote(
                fitting_id=2,
                items=[
                    {"flag": "HiSlot0", "quantity": 1, "type_id": 200},
                    {"flag": "HiSlot0", "quantity": 20, "type_id": 201},
                ],
            ),
            remote(
                fitting_id=3,
                items=[
                    {"flag": "HiSlot0", "quantity": 1, "type_id": 200},
                    {"flag": "HiSlot0", "quantity": 1, "type_id": 202},
                ],
            ),
        ]
    )

    contents = {
        canonicalize(module_only),
        canonicalize(with_charge),
        canonicalize(with_script),
    }
    assert len(contents) == 3


def test_digest_match_still_compares_full_content(monkeypatch):
    monkeypatch.setattr(model, "_digest", lambda _: "collision")

    assert not canonical_equal(content_for(100), content_for(200))


def test_unknown_remote_flag_rejects_the_complete_snapshot():
    payload = [remote(fitting_id=1), remote(fitting_id=2)]
    payload[1]["items"][0]["flag"] = "FutureSlot0"

    with pytest.raises(ValueError, match="unknown fitting flag"):
        validate_remote_snapshot(payload)


def test_invalid_is_canonical_but_has_no_deployment_template():
    fitting = validate_remote_snapshot(fixture("get-invalid-flag.json"))[0]

    assert ("Invalid", 700011, 1) in canonicalize(fitting).key()[1]
    assert deployment_template(fitting) is None


def test_valid_deployment_template_retains_exact_numbered_flags():
    fitting = validate_remote_snapshot(fixture("get-equivalent-slots.json"))[1]

    template = deployment_template(fitting)

    assert template == fitting.items
    assert [item.flag for item in template] == [
        "HiSlot3",
        "HiSlot7",
        "MedSlot4",
        "LoSlot6",
    ]


def test_remote_validation_is_strict_about_shape_ids_quantities_and_bounds():
    bad_values = [True, 0, -1, "1", None]
    for value in bad_values:
        payload = [remote()]
        payload[0]["items"][0]["quantity"] = value
        with pytest.raises(ValueError):
            validate_remote_snapshot(payload)

    with pytest.raises(ValueError):
        validate_remote_snapshot([remote(name="")])
    with pytest.raises(ValueError):
        validate_remote_snapshot([remote(name="x" * 51)])
    with pytest.raises(ValueError):
        validate_remote_snapshot([remote(description="x" * 501)])
    with pytest.raises(ValueError):
        validate_remote_snapshot([remote(items=[])])
    with pytest.raises(ValueError):
        validate_remote_snapshot([remote()] * 501)


def test_remote_fitting_and_canonical_types_are_immutable():
    fitting = validate_remote_snapshot([remote()])[0]

    with pytest.raises(FrozenInstanceError):
        fitting.name = "Changed"
    with pytest.raises(FrozenInstanceError):
        canonicalize(fitting).ship_type_id = 999


def test_normalized_name_key_uses_nfc_and_unicode_casefold():
    assert normalized_name_key("Cafe\u0301 STRASSE") == normalized_name_key(
        "CAFÉ Straße"
    )


def test_new_library_entry_has_stable_id_and_separate_versioned_fingerprint():
    fitting = validate_remote_snapshot([remote(name="Observed")])[0]

    first = new_library_entry(fitting, entry_id="local-id", now=NOW)
    second = new_library_entry(
        fitting,
        entry_id="local-id",
        now=NOW,
        fingerprint_version=2,
    )

    assert first.id == second.id == "local-id"
    assert first.fingerprint_version == 1
    assert second.fingerprint_version == 2
    assert first.digest != second.digest
    assert first.source_template == fitting.items
    assert first.deployment_template == fitting.items
    assert first.aliases == (SourceAlias("Observed", "", fitting.items),)


def test_alias_retention_is_unique_bounded_deterministic_and_keeps_preferred():
    fitting = validate_remote_snapshot([remote()])[0]
    aliases = [SourceAlias(f"Alias {i:03}", str(i), fitting.items) for i in range(105)]
    preferred = SourceAlias("Preferred", "Description", fitting.items)
    forward = retain_aliases(
        [*aliases, preferred, aliases[0]],
        preferred_name=preferred.name,
        preferred_description=preferred.description,
    )
    backward = retain_aliases(
        [preferred, *reversed(aliases)],
        preferred_name=preferred.name,
        preferred_description=preferred.description,
    )

    assert len(forward) == 100
    assert forward == backward
    assert preferred in forward


def test_collections_have_stable_ids_and_membership_is_many_to_many():
    fitting = validate_remote_snapshot([remote()])[0]
    base = new_library_entry(fitting, entry_id="fit-1", now=NOW)
    filed = replace(base, collection_ids=("doctrine", "alliance"))

    assert Collection("doctrine", "Doctrine").id == "doctrine"
    assert filed.collection_ids == ("doctrine", "alliance")
    assert filed.is_unfiled is False
    assert base.is_unfiled is True


def test_supersession_requires_existing_same_hull_target():
    old = entry("old", content_for(200))
    same_hull = entry("new", content_for(201))
    other_hull = entry("other", content_for(202, ship=101))

    validate_supersession((old, same_hull), "old", "new")
    with pytest.raises(ValueError, match="same ship type"):
        validate_supersession((old, other_hull), "old", "other")
    with pytest.raises(ValueError, match="does not exist"):
        validate_supersession((old,), "old", "missing")


def test_supersession_rejects_self_edges_and_cycles():
    old = entry("old", content_for(200), superseded_by="new")
    new = entry("new", content_for(201))

    with pytest.raises(ValueError, match="itself"):
        validate_supersession((old, new), "old", "old")
    with pytest.raises(ValueError, match="cycle"):
        validate_supersession((old, new), "new", "old")


def test_package_exports_the_task_seven_domain_surface():
    expected = {
        "CanonicalContent",
        "FittingsState",
        "LibraryEntry",
        "Presence",
        "RemoteFitting",
        "WriteIntent",
        "canonical_equal",
        "canonicalize",
        "deployment_template",
        "fingerprint",
        "load_fittings",
        "normalized_name_key",
        "save_fittings",
        "validate_remote_snapshot",
        "validate_supersession",
    }

    assert expected <= set(evefittings.__all__)
    assert all(hasattr(evefittings, name) for name in expected)


def test_exported_domain_records_are_frozen():
    fitting = validate_remote_snapshot([remote()])[0]
    library = new_library_entry(fitting, entry_id="fit-1", now=NOW)

    assert isinstance(fitting, RemoteFitting)
    assert isinstance(library, LibraryEntry)
    with pytest.raises(FrozenInstanceError):
        library.preferred_name = "Changed"
