"""Approved expectations come from cases.json, never from the codec."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from wingman.evefittings import model

FIXTURES = Path(__file__).parent / "fixtures" / "evefittings" / "eft"
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))["cases"]
EVIDENCE = json.loads((FIXTURES / "esi-evidence.json").read_text(encoding="utf-8"))


@pytest.fixture
def codec():
    from wingman.evefittings import eft

    return eft


def snapshot(eft):
    records = {r["id"]: r["body_projection"] for r in EVIDENCE["records"]}
    types = []
    for key, raw in records.items():
        if not key.startswith("type-") or "type_id" not in raw:
            continue
        group = records[f"group-{raw['group_id']}"]
        types.append(
            eft.InventoryType(
                raw["type_id"],
                raw["name"],
                raw["group_id"],
                group["category_id"],
                raw["published"],
                frozenset(row["effect_id"] for row in raw["dogma_effects"]),
            )
        )
    types.sort(key=lambda row: row.type_id)
    return eft.InventorySnapshot(
        tuple(types),
        tuple(
            sorted((model.normalized_name_key(row.name), row.type_id) for row in types)
        ),
    )


def library(rows, *, ship=587, name="Saved fitting"):
    return model.new_library_entry(
        model.RemoteFitting(
            123,
            ship,
            name,
            "Private description",
            tuple(model.RemoteItem(**row) for row in rows),
        )
    )


def case_entry(case, rows):
    return library(rows, ship=case["ship_type_id"], name=case["name"])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_approved_import_matrix(codec, case):
    inventory = snapshot(codec)
    text = (FIXTURES / case["file"]).read_text(encoding="utf-8")
    approved = case["approved_import"]
    if not approved["ok"]:
        with pytest.raises(codec.EftError) as caught:
            codec.resolve_eft(codec.parse_eft(text), inventory)
        assert caught.value.code == approved["error"]["code"]
        assert caught.value.line_number == approved["error"]["line_number"]
        assert caught.value.message
        return
    candidate = codec.resolve_eft(codec.parse_eft(text), inventory)
    assert candidate.ship_type_id == case["ship_type_id"]
    assert candidate.name == case["name"]
    assert [asdict(row) for row in candidate.items] == approved["items"]
    assert [asdict(row) for row in candidate.warnings] == approved["warnings"]
    expected_ids = {case["ship_type_id"]} | {
        row["type_id"] for row in approved["items"]
    }
    assert candidate.verified_names == tuple(
        (row.type_id, row.name)
        for row in inventory.types
        if row.type_id in expected_ids
    )


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c["approved_export"]["normalized_candidate"]],
    ids=lambda c: c["id"],
)
def test_every_exportable_fixture_round_trips_full_content(codec, case):
    entry = case_entry(case, case["approved_import"]["items"])
    inventory = snapshot(codec)
    text = codec.render_eft(entry, inventory)
    candidate = codec.resolve_eft(codec.parse_eft(text), inventory)
    assert (
        model.canonicalize_items(candidate.ship_type_id, candidate.items)
        == entry.content
    )
    # Racks keep exact positions; nonrack stacks alone may aggregate.
    assert tuple(row for row in candidate.items if "Slot" in row.flag) == tuple(
        row for row in entry.deployment_template if "Slot" in row.flag
    )
    assert text.endswith("\n") and not text.endswith("\n\n") and "\r" not in text
    assert "Private description" not in text
    assert [asdict(row) for row in entry.deployment_template] == case[
        "approved_import"
    ]["items"]


@pytest.mark.parametrize(
    "case,alternative",
    [(c, a) for c in CASES for a in c["approved_export"]["original_alternatives"]],
    ids=lambda v: str(v.get("id", v.get("index"))),
)
def test_original_ambiguity_alternatives_are_not_relocated(codec, case, alternative):
    entry = case_entry(case, case["alternative_rows"][alternative["index"]])
    if alternative["ok"]:
        text = codec.render_eft(entry, snapshot(codec))
        candidate = codec.resolve_eft(codec.parse_eft(text), snapshot(codec))
        assert (
            model.canonicalize_items(candidate.ship_type_id, candidate.items)
            == entry.content
        )
    else:
        with pytest.raises(codec.EftError):
            codec.render_eft(entry, snapshot(codec))


def test_physical_lines_normalization_and_record_invariants(codec):
    parsed = codec.parse_eft(
        "\ufeff\r\n [ Rifter , Café,  fleet ] \r\n\t\r\n 200mm AutoCannon II, Republic Fleet EMP S /OFFLINE\t\r\n[Empty Low slot]\r\nHobgoblin II x5\r\n"
    )
    assert (parsed.ship_name, parsed.name, parsed.header_line_number) == (
        "Rifter",
        "Café,  fleet",
        2,
    )
    assert parsed.lines == (
        codec.ParsedLine(
            4, "module", "200mm AutoCannon II", 1, "Republic Fleet EMP S", True, None
        ),
        codec.ParsedLine(5, "empty", None, None, None, False, "low"),
        codec.ParsedLine(6, "quantity", "Hobgoblin II", 5, None, False, None),
    )
    result = codec.resolve_eft(parsed, snapshot(codec))
    assert [(w.code, w.line_number) for w in result.warnings] == [
        ("loaded_charge_omitted", 4),
        ("offline_omitted", 4),
        ("bay_convention", 6),
    ]
    assert 21898 not in dict(result.verified_names)


def test_tabs_surround_fields_without_becoming_name_content(codec):
    parsed = codec.parse_eft(
        "[\tRifter\t,\tFit\t]\n\t200mm AutoCannon II\t,\tRepublic Fleet EMP S\t /offline"
    )
    candidate = codec.resolve_eft(parsed, snapshot(codec))
    assert candidate.name == "Fit"
    assert candidate.items == (model.RemoteItem("HiSlot0", 2889, 1),)
    assert [warning.code for warning in candidate.warnings] == [
        "loaded_charge_omitted",
        "offline_omitted",
    ]


def test_unicode_field_edges_trim_without_collapsing_internal_spaces(codec):
    parsed = codec.parse_eft(
        "[\u00a0Rifter\u00a0,\u00a0 Fleet  fit \u00a0]\n\u00a0Damage Control II\u00a0"
    )
    assert (parsed.ship_name, parsed.name) == ("Rifter", "Fleet  fit")
    assert parsed.lines[0].type_name == "Damage Control II"


def test_casefold_nfc_only_not_fuzzy_or_whitespace_aliases(codec):
    inventory = snapshot(codec)
    renamed = tuple(
        replace(t, name="Café STRASSE") if t.type_id == 2048 else t
        for t in inventory.types
    )
    inventory = replace(
        inventory,
        types=renamed,
        name_bindings=tuple(
            sorted((model.normalized_name_key(t.name), t.type_id) for t in renamed)
        ),
    )
    candidate = codec.resolve_eft(
        codec.parse_eft("[ rifter , Fit]\nCafe\u0301 Straße"), inventory
    )
    assert candidate.items == (model.RemoteItem("LoSlot0", 2048, 1),)
    assert dict(candidate.verified_names)[2048] == "Café STRASSE"
    for name in ("Cafe STRASSE", "Café  STRASSE", "Damage Control II"):
        with pytest.raises(codec.EftError):
            codec.resolve_eft(codec.parse_eft("[Rifter, Fit]\n" + name), inventory)


def test_export_must_run_internal_resolution_even_when_template_matches(
    codec, monkeypatch
):
    entry = library([{"flag": "LoSlot0", "type_id": 2048, "quantity": 1}])
    inventory = snapshot(codec)
    missing_binding = replace(
        inventory,
        name_bindings=tuple(
            (key, value) for key, value in inventory.name_bindings if value != 2048
        ),
    )
    with pytest.raises(codec.EftError):
        codec.render_eft(entry, missing_binding)
    original = codec.resolve_eft

    def wrong_resolution(parsed, snapshot):
        candidate = original(parsed, snapshot)
        return replace(candidate, items=(model.RemoteItem("LoSlot0", 2048, 2),))

    monkeypatch.setattr(codec, "resolve_eft", wrong_resolution)
    with pytest.raises(codec.EftError):
        codec.render_eft(entry, inventory)


def test_rack_counters_ignore_sections_and_quantity_modules_are_cargo(codec):
    text = "[Rifter, Mixed]\n[Empty High slot]\nDamage Control II\n\n200mm AutoCannon II\n\nDamage Control II\n200mm AutoCannon II x3\nHobgoblin II x2\n\n\nHobgoblin II x5"
    candidate = codec.resolve_eft(codec.parse_eft(text), snapshot(codec))
    assert [row.key() for row in candidate.items] == [
        ("LoSlot0", 2048, 1),
        ("HiSlot1", 2889, 1),
        ("LoSlot1", 2048, 1),
        ("Cargo", 2889, 3),
        ("DroneBay", 2456, 2),
        ("DroneBay", 2456, 5),
    ]


@pytest.mark.parametrize(
    "rack,module,last",
    [
        ("Low", "Damage Control II", "LoSlot7"),
        ("Med", "1MN Afterburner II", "MedSlot7"),
        ("High", "200mm AutoCannon II", "HiSlot7"),
        ("Rig", "Small Projectile Burst Aerator I", "RigSlot2"),
        ("Subsystem", "Tengu Defensive - Covert Reconfiguration", "SubSystemSlot3"),
        ("Service", "Standup Market Hub I", "ServiceSlot7"),
    ],
)
def test_all_six_racks_preserve_leading_holes_and_refuse_overflow(
    codec, rack, module, last
):
    marker = f"[Empty {rack} slot]\n"
    text = "[Rifter, Holes]\n" + marker * int(last[-1]) + module + "\n"
    candidate = codec.resolve_eft(codec.parse_eft(text), snapshot(codec))
    assert candidate.items[0].flag == last
    entry = library([asdict(row) for row in candidate.items], name="Holes")
    assert codec.render_eft(entry, snapshot(codec)) == text.replace("\n", "\n\n", 1)
    with pytest.raises(codec.EftError) as caught:
        codec.resolve_eft(codec.parse_eft(text + marker), snapshot(codec))
    assert caught.value.code == "rack_overflow"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[Rifter, Empty]",
        "[Rifter, Empty]\n[Empty High slot]",
        "Rifter, Bad\nDamage Control II",
        "[, Fit]\nDamage Control II",
        "[Rifter, ]\nDamage Control II",
        "[Rifter, \u00a0]\nDamage Control II",
        "[Rifter, A]\nDamage Control II\x85",
        "[Rifter, Bad[Name]]\nDamage Control II",
        "[Rifter, " + "n" * 51 + "]\nDamage Control II",
        "[Rifter, A]\nDamage Control II\n[Rifter, B]",
        "[Rifter, A]\n[Empty Med Slot]",
        "[Rifter, A]\nDamage Control II /active",
        "[Rifter, A]\nDamage Control II\x00",
        "[Rifter, A]\nDamage\tControl II",
        "[Rifter, A]\n\ufeffDamage Control II",
        "[Rifter, A]\nDamage Control II, Republic Fleet EMP S, extra",
        "[Rifter, A]\nDamage Control II x2 /offline",
        "[Rifter, A]\nDamage Control II x2, Republic Fleet EMP S",
        "[Rifter, A]\n" + "x" * 257,
        "[Rifter, A]\n" + "\n" * 2048 + "Damage Control II",
        "[Rifter, A]\n" + "Republic Fleet EMP S x1\n" * 513,
        # Keep the payload out of Windows' size-limited PYTEST_CURRENT_TEST.
        pytest.param("[Rifter, A]\n" + "é" * 33000, id="oversized-utf8-input"),
        "[Rifter, A]\n\ud800",
    ],
)
def test_syntax_and_bounds_refuse_before_resolution(codec, text):
    with pytest.raises(codec.EftError):
        codec.parse_eft(text)


@pytest.mark.parametrize(
    "quantity",
    ["0", "-1", "+1", "1.5", "\u0661", "", "2147483648", "9" * 5000, "1 extra"],
)
def test_quantity_refusals_are_line_specific(codec, quantity):
    with pytest.raises(codec.EftError) as caught:
        codec.parse_eft("[Rifter, Fit]\n\nRepublic Fleet EMP S x" + quantity)
    assert (caught.value.code, caught.value.line_number) == ("invalid_quantity", 3)


def test_duplicate_quantity_overflow_is_pre_network_and_boundary_is_exact(codec):
    base = "[Rifter, Fit]\nRepublic Fleet EMP S x2147483647"
    parsed = codec.parse_eft(base)
    assert codec.resolve_eft(parsed, snapshot(codec)).items[0].quantity == 2147483647
    with pytest.raises(codec.EftError) as caught:
        codec.parse_eft(base + "\nrepublic fleet emp s x1")
    assert (caught.value.code, caught.value.line_number) == ("invalid_quantity", 3)
    text = "[Rifter, Fit]\n" + "Republic Fleet EMP S x1\n" * 512
    assert len(codec.resolve_eft(codec.parse_eft(text), snapshot(codec)).items) == 512


@pytest.mark.parametrize(
    "type_id,change",
    [
        (587, {"category_id": 7}),
        (587, {"published": False}),
        (2048, {"published": False}),
        (2048, {"category_id": 20}),
        (2048, {"dogma_effect_ids": frozenset()}),
        (2048, {"dogma_effect_ids": frozenset({11, 12})}),
    ],
)
def test_metadata_category_and_exact_one_slot_effect(codec, type_id, change):
    inventory = snapshot(codec)
    inventory = replace(
        inventory,
        types=tuple(
            replace(t, **change) if t.type_id == type_id else t for t in inventory.types
        ),
    )
    with pytest.raises(codec.EftError):
        codec.resolve_eft(
            codec.parse_eft("[Rifter, Fit]\nDamage Control II"), inventory
        )


def test_inline_noncharge_and_quantity_implants_refuse(codec):
    with pytest.raises(codec.EftError):
        codec.resolve_eft(
            codec.parse_eft("[Rifter, Fit]\n200mm AutoCannon II, Damage Control II"),
            snapshot(codec),
        )
    inventory = snapshot(codec)
    inventory = replace(
        inventory,
        types=tuple(
            replace(t, category_id=20) if t.type_id == 2048 else t
            for t in inventory.types
        ),
    )
    with pytest.raises(codec.EftError):
        codec.resolve_eft(
            codec.parse_eft("[Rifter, Fit]\nDamage Control II x1"), inventory
        )


@pytest.mark.parametrize(
    "rows",
    [
        [{"flag": "LoSlot0", "type_id": 2048, "quantity": 2}],
        [{"flag": "HiSlot0", "type_id": 2048, "quantity": 1}],
        [{"flag": "LoSlot0", "type_id": 2048, "quantity": 1}] * 2,
        [{"flag": "Invalid", "type_id": 2048, "quantity": 1}],
        [{"flag": "DroneBay", "type_id": 21898, "quantity": 1}],
        [
            {"flag": "Cargo", "type_id": 2456, "quantity": 1},
            {"flag": "DroneBay", "type_id": 2456, "quantity": 1},
        ],
        [{"flag": "Cargo", "type_id": 21898, "quantity": 2147483648}],
        [{"flag": "Cargo", "type_id": 21898, "quantity": 2147483647}] * 2,
        [],
    ],
)
def test_unrepresentable_templates_refuse(codec, rows):
    with pytest.raises(codec.EftError):
        codec.render_eft(library(rows), snapshot(codec))


def test_export_checks_full_canonical_equality_not_digest(codec, monkeypatch):
    entry = library([{"flag": "LoSlot0", "type_id": 2048, "quantity": 1}])
    monkeypatch.setattr(model, "_digest", lambda _: "collision")
    changed = replace(
        entry,
        content=model.CanonicalContent(587, (model.CanonicalItem("low", 2048, 2),)),
    )
    with pytest.raises(codec.EftError):
        codec.render_eft(changed, snapshot(codec))
    with pytest.raises(codec.EftError):
        codec.render_eft(replace(entry, deployment_template=None), snapshot(codec))
    with pytest.raises(codec.EftError):
        codec.render_eft(replace(entry, preferred_name="Bad\nname"), snapshot(codec))


def test_export_deterministic_sections_sorting_and_aggregation(codec):
    rows = [
        {"flag": "Cargo", "type_id": 21898, "quantity": 2},
        {"flag": "FighterBay", "type_id": 23059, "quantity": 9},
        {"flag": "HiSlot2", "type_id": 2889, "quantity": 1},
        {"flag": "DroneBay", "type_id": 2456, "quantity": 5},
        {"flag": "LoSlot0", "type_id": 2048, "quantity": 1},
        {"flag": "Cargo", "type_id": 2048, "quantity": 3},
        {"flag": "Cargo", "type_id": 21898, "quantity": 7},
    ]
    assert codec.render_eft(library(rows), snapshot(codec)) == (
        "[Rifter, Saved fitting]\n\nDamage Control II\n\n"
        "[Empty High slot]\n[Empty High slot]\n200mm AutoCannon II\n\n\n"
        "Hobgoblin II x5\n\nFirbolg I x9\n\n\nDamage Control II x3\nRepublic Fleet EMP S x9\n"
    )
