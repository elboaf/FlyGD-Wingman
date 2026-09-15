"""Strict authority lookup with complete, explicitly authored I/O shapes.

Task 1 retained projections, not full response bodies. Boundary fixtures below
keep every captured metadata field and supply authored descriptions/attributes,
physical values and group memberships to exercise the full ESI object shape.
Those additions are test data, not a claim they were captured from ESI.
"""

import copy
import io
import json
import urllib.error

import pytest

from tests.test_evefittings_eft import CASES, EVIDENCE, FIXTURES, library
from wingman.eveesi import EsiClient, EsiResponse


@pytest.fixture
def resolver_module():
    from wingman.evefittings import inventory

    return inventory


class PublicInventory:
    """ESI-shaped responses; only the read-only public seam is doubled."""

    def __init__(self):
        records = {
            r["id"]: copy.deepcopy(r["body_projection"]) for r in EVIDENCE["records"]
        }
        self.types = {
            r["type_id"]: r
            for k, r in records.items()
            if k.startswith("type-") and "type_id" in r
        }
        self.groups = {
            r["group_id"]: r for k, r in records.items() if k.startswith("group-")
        }
        for raw in self.types.values():
            raw.update(
                description="Authored boundary fixture, not captured prose.",
                dogma_attributes=[{"attribute_id": 9, "value": 1.0}],
                graphic_id=1,
                icon_id=1,
                market_group_id=1,
                mass=1.0,
                packaged_volume=raw["volume"],
                portion_size=1,
                radius=1.0,
            )
        for raw in self.groups.values():
            raw.setdefault(
                "types",
                [
                    t["type_id"]
                    for t in self.types.values()
                    if t["group_id"] == raw["group_id"]
                ],
            )
        self.calls = []
        self.mutate = lambda path, data: data
        self.after_call = lambda: None
        self.status = 200

    def _reply(self, method, path, data):
        data = self.mutate(path, copy.deepcopy(data))
        self.after_call()
        return EsiResponse(
            self.status,
            data,
            "service unavailable" if self.status != 200 else "",
            '"fixture"',
            method,
            path,
        )

    def post(self, path, body, *, token=None):
        assert token is None
        assert isinstance(body, list) and 0 < len(body) <= 1000
        self.calls.append(("POST", path, list(body)))
        if path == "/universe/ids":
            assert all(isinstance(name, str) for name in body)
            requested = {name.strip().casefold() for name in body}
            data = {
                "inventory_types": [
                    {"id": t["type_id"], "name": t["name"]}
                    for t in reversed(tuple(self.types.values()))
                    if t["name"].casefold() in requested
                ],
                "characters": [{"id": 90000001, "name": "Authored Pilot"}],
                "corporations": [{"id": 98000001, "name": "Authored Corporation"}],
                "alliances": [],
                "constellations": [],
                "factions": [],
                "regions": [],
                "stations": [],
                "systems": [],
            }
        else:
            assert path == "/universe/names"
            assert all(type(type_id) is int for type_id in body)
            data = [
                {"category": "inventory_type", "id": t, "name": self.types[t]["name"]}
                for t in reversed(body)
            ]
        return self._reply("POST", path, data)

    def get(self, path, *, token=None):
        assert token is None
        self.calls.append(("GET", path, None))
        parts = path.split("/")
        assert parts[1] == "universe" and parts[2] in {"types", "groups"}
        source = self.types if parts[2] == "types" else self.groups
        return self._reply("GET", path, source[int(parts[3])])


def setup(
    module,
    text="[Rifter, Private name]\n200mm AutoCannon II, Republic Fleet EMP S /offline",
):
    from wingman.evefittings.eft import parse_eft

    client = PublicInventory()
    return (
        client,
        module.InventoryResolver(client, stopping=lambda: False),
        parse_eft(text),
    )


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["approved_import"]["ok"]], ids=lambda c: c["id"]
)
def test_fixture_lookup_to_candidate_is_complete_and_detached(resolver_module, case):
    from dataclasses import asdict

    from wingman.evefittings.eft import parse_eft, resolve_eft

    client = PublicInventory()
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    parsed = parse_eft((FIXTURES / case["file"]).read_text(encoding="utf-8"))
    inventory = resolver.for_import(parsed)
    candidate = resolve_eft(parsed, inventory)
    assert [asdict(row) for row in candidate.items] == case["approved_import"]["items"]
    assert [asdict(row) for row in candidate.warnings] == case["approved_import"][
        "warnings"
    ]
    before = repr(inventory)
    for raw in client.types.values():
        raw["name"] = "Changed externally"
        raw["dogma_effects"].clear()
    assert repr(inventory) == before
    assert inventory.types == tuple(sorted(inventory.types, key=lambda t: t.type_id))
    assert inventory.name_bindings == tuple(sorted(set(inventory.name_bindings)))


def test_only_parsed_inventory_names_are_sent_and_cache_is_shared_with_export(
    resolver_module,
):
    from wingman.evefittings.eft import resolve_eft

    client, resolver, parsed = setup(resolver_module)
    inventory = resolver.for_import(parsed)
    assert {row.type_id for row in inventory.types} == {587, 2889, 21898}
    assert client.calls[0] == (
        "POST",
        "/universe/ids",
        ["Rifter", "200mm AutoCannon II", "Republic Fleet EMP S"],
    )
    assert all("Private name" not in str(call) for call in client.calls)
    assert 12 in next(t for t in inventory.types if t.type_id == 2889).dogma_effect_ids
    before = len(client.calls)
    assert resolver.for_import(parsed) == inventory
    entry = library([{"flag": "HiSlot0", "type_id": 2889, "quantity": 1}])
    exported = resolver.for_export(entry)
    assert {t.type_id for t in exported.types} == {587, 2889}
    assert len(client.calls) == before
    assert resolve_eft(parsed, inventory).items[0].type_id == 2889


def test_export_resolves_only_stored_ids_with_verified_names(resolver_module):
    from wingman.evefittings.eft import render_eft

    client = PublicInventory()
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    entry = library(
        [{"flag": "LoSlot0", "type_id": 2048, "quantity": 1}], name="Private saved name"
    )
    inventory = resolver.for_export(entry)
    assert client.calls[0] == ("POST", "/universe/names", [587, 2048])
    assert (
        render_eft(entry, inventory)
        == "[Rifter, Private saved name]\n\nDamage Control II\n"
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"inventory_types": None},
        {"inventory_types": [{}]},
        {"inventory_types": [{"id": True, "name": "Rifter"}]},
        {"inventory_types": [{"id": 0, "name": "Rifter"}]},
        {"inventory_types": [{"id": "587", "name": "Rifter"}]},
        {"inventory_types": [{"id": 587, "name": "Another hull"}]},
        {
            "inventory_types": [
                {"id": 587, "name": "Rifter"},
                {"id": 999, "name": "RIFTER"},
            ]
        },
        {
            "inventory_types": [
                {"id": 587, "name": "Rifter"},
                {"id": 587, "name": "Rifter"},
            ]
        },
        {"inventory_types": [{"id": 587, "name": "Rifter"}]},
    ],
)
def test_ids_malformed_partial_conflicting_and_unrequested_refuse(
    resolver_module, payload
):
    from wingman.evefittings.eft import EftError

    client, resolver, parsed = setup(resolver_module)
    client.mutate = lambda path, data: payload if path == "/universe/ids" else data
    with pytest.raises(EftError):
        resolver.for_import(parsed)
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("type_id", True),
        ("type_id", 2048),
        ("group_id", False),
        ("group_id", 0),
        ("name", "Wrong"),
        ("name", ""),
        ("name", "x" * 257),
        ("name", "Rifter\n"),
        ("published", 1),
        ("published", False),
        ("dogma_effects", None),
        ("dogma_effects", [{}]),
        ("dogma_effects", [{"effect_id": True, "is_default": False}]),
        ("dogma_effects", [{"effect_id": 11, "is_default": 1}]),
    ],
)
def test_type_response_strict_validation(resolver_module, field, value):
    from wingman.evefittings.eft import EftError

    client, resolver, parsed = setup(resolver_module)
    client.types[587][field] = value
    # The lookup name is independently returned, not built from the bad type response.
    original = client.post

    def post(path, body, *, token=None):
        saved = client.types[587]
        client.types[587] = {**saved, "type_id": 587, "name": "Rifter"}
        try:
            return original(path, body, token=token)
        finally:
            client.types[587] = saved

    client.post = post
    with pytest.raises(EftError):
        resolver.for_import(parsed)


@pytest.mark.parametrize(
    "field", ["type_id", "group_id", "name", "published", "dogma_effects"]
)
def test_missing_type_metadata_refuses(resolver_module, field):
    from wingman.evefittings.eft import EftError

    client, resolver, parsed = setup(resolver_module)

    def mutate(path, data):
        if path == "/universe/types/587":
            del data[field]
        return data

    client.mutate = mutate
    with pytest.raises(EftError):
        resolver.for_import(parsed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("group_id", True),
        ("group_id", 26),
        ("category_id", True),
        ("category_id", 0),
        ("published", False),
        ("published", 1),
    ],
)
def test_group_metadata_cannot_supply_false_authority(resolver_module, field, value):
    from wingman.evefittings.eft import EftError

    client, resolver, parsed = setup(resolver_module)
    client.groups[25][field] = value
    with pytest.raises(EftError):
        resolver.for_import(parsed)


@pytest.mark.parametrize(
    "change",
    [
        lambda rows: rows[:-1],
        lambda rows: [{**rows[0], "category": "character"}, *rows[1:]],
        lambda rows: [{**rows[0], "id": True}, *rows[1:]],
        lambda rows: [{**rows[0], "name": "Other name"}, *rows[1:]],
        lambda rows: [*rows, rows[0]],
        lambda rows: [
            *rows,
            {"id": 999, "name": "Injected", "category": "inventory_type"},
        ],
        lambda rows: {},
    ],
)
def test_export_names_response_requires_exact_inventory_association(
    resolver_module, change
):
    from wingman.evefittings.eft import EftError

    client = PublicInventory()
    client.mutate = lambda path, data: (
        change(data) if path == "/universe/names" else data
    )
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    with pytest.raises(EftError):
        resolver.for_export(
            library([{"flag": "LoSlot0", "type_id": 2048, "quantity": 1}])
        )


@pytest.mark.parametrize("status", [304, 400, 404, 429, 503])
def test_http_failure_does_not_produce_snapshot_or_negative_cache(
    resolver_module, status
):
    from wingman.evefittings.eft import EftError, resolve_eft

    client, resolver, parsed = setup(resolver_module)
    client.status = status
    with pytest.raises(EftError) as caught:
        resolver.for_import(parsed)
    assert str(status) in caught.value.message
    assert len(client.calls) == 1  # EsiClient, not resolver, owns retries.
    client.status = 200
    assert resolve_eft(parsed, resolver.for_import(parsed)).ship_type_id == 587


def test_stopping_before_after_requests_and_on_cached_path(resolver_module):
    from wingman.evefittings.eft import EftError, parse_eft

    client = PublicInventory()
    stopped = True
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: stopped)
    parsed = parse_eft("[Rifter, Fit]\nDamage Control II")
    with pytest.raises(EftError, match="stopp"):
        resolver.for_import(parsed)
    assert client.calls == []
    stopped = False

    def stop():
        nonlocal stopped
        stopped = True

    client.after_call = stop
    with pytest.raises(EftError, match="stopp"):
        resolver.for_import(parsed)
    assert len(client.calls) == 1
    stopped = False
    client.after_call = lambda: None
    snapshot = resolver.for_import(parsed)
    stopped = True
    with pytest.raises(EftError, match="stopp"):
        resolver.for_import(parsed)
    assert len(snapshot.types) == 2


def test_bounded_cache_eviction_keeps_retained_snapshot_and_groups_detached(
    resolver_module, monkeypatch
):
    from wingman.evefittings.eft import parse_eft, resolve_eft

    monkeypatch.setattr(resolver_module, "MAX_CACHED_TYPES", 2)
    monkeypatch.setattr(resolver_module, "MAX_CACHED_GROUPS", 2)
    client, resolver, parsed = setup(
        resolver_module, "[Rifter, Fit]\nDamage Control II"
    )
    retained = resolver.for_import(parsed)
    resolver.for_import(parse_eft("[Tengu, Other]\n1MN Afterburner II"))
    assert len(resolver._types) <= 2 and len(resolver._groups) <= 2
    assert [r.type_id for r in resolve_eft(parsed, retained).items] == [2048]
    before = len(client.calls)
    assert resolver.for_import(parsed) == retained
    assert len(client.calls) > before


def test_large_import_batches_include_inline_charges_without_truncation(
    resolver_module,
):
    from wingman.evefittings.eft import parse_eft

    client = PublicInventory()
    module = copy.deepcopy(client.types[2889])
    charge = copy.deepcopy(client.types[21898])
    lines = []
    for index in range(512):
        a, b = 100000 + index, 200000 + index
        client.types[a] = {**module, "type_id": a, "name": f"Authored Module {index}"}
        client.types[b] = {**charge, "type_id": b, "name": f"Authored Charge {index}"}
        lines.append(f"Authored Module {index}, Authored Charge {index}")
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    inventory = resolver.for_import(parse_eft("[Rifter, Batch]\n" + "\n".join(lines)))
    assert len(inventory.types) == len(inventory.name_bindings) == 1025
    batches = [body for method, path, body in client.calls if path == "/universe/ids"]
    assert [len(batch) for batch in batches] == [1000, 25]
    assert len({name for batch in batches for name in batch}) == 1025


@pytest.mark.parametrize("quantity", [True, 0, 2147483648])
def test_export_refuses_invalid_stored_bounds_before_network(resolver_module, quantity):
    from wingman.evefittings.eft import EftError

    client = PublicInventory()
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    entry = library([{"flag": "Cargo", "type_id": 21898, "quantity": quantity}])
    with pytest.raises(EftError):
        resolver.for_export(entry)
    assert client.calls == []


def test_unknown_inline_name_is_a_line_specific_error_not_a_warning(resolver_module):
    from wingman.evefittings.eft import EftError

    client, resolver, parsed = setup(
        resolver_module, "[Rifter, Fit]\n\n200mm AutoCannon II, Unknown authored charge"
    )
    with pytest.raises(EftError) as caught:
        resolver.for_import(parsed)
    assert (caught.value.code, caught.value.line_number) == ("unresolved_name", 3)
    assert len(client.calls) == 1


def test_resolver_normalizes_nfc_casefold_without_aliasing(resolver_module):
    from wingman.evefittings.eft import parse_eft, resolve_eft

    client, resolver, _ = setup(resolver_module)
    client.types[2048]["name"] = "Café STRASSE"
    parsed = parse_eft("[ rifter , Fit]\n Cafe\u0301 Straße ")
    inventory = resolver.for_import(parsed)
    assert inventory.name_bindings == (("café strasse", 2048), ("rifter", 587))
    assert resolve_eft(parsed, inventory).items[0].type_id == 2048
    assert client.calls[0][2] == ["rifter", "Café Straße"]


def test_snapshot_conflict_cannot_hide_after_cache_eviction(
    resolver_module, monkeypatch
):
    from wingman.evefittings.eft import EftError

    monkeypatch.setattr(resolver_module, "MAX_CACHED_TYPES", 1)
    client = PublicInventory()
    client.types[2048]["name"] = "Rifter"
    # Evict the first Rifter binding before fetching the second. The retained
    # request subset must still detect the conflict independently of the LRU.
    client.mutate = lambda path, data: (
        sorted(data, key=lambda row: {2048: 0, 21898: 1, 587: 2}[row["id"]])
        if path == "/universe/names"
        else data
    )
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    with pytest.raises(EftError, match="snapshot bindings"):
        resolver.for_export(
            library(
                [
                    {"flag": "LoSlot0", "type_id": 2048, "quantity": 1},
                    {"flag": "Cargo", "type_id": 21898, "quantity": 1},
                ]
            )
        )


@pytest.mark.parametrize(
    "effects",
    [
        [{"effect_id": 11, "is_default": False}] * 2,
        [{"effect_id": index + 1, "is_default": False} for index in range(4097)],
    ],
)
def test_duplicate_or_oversized_effect_arrays_are_not_cached(resolver_module, effects):
    from wingman.evefittings.eft import EftError

    client, resolver, parsed = setup(resolver_module)
    client.types[587]["dogma_effects"] = effects
    with pytest.raises(EftError):
        resolver.for_import(parsed)
    assert 587 not in resolver._types


def test_shared_transport_retry_and_malformed_json_are_real_boundary_behaviour(
    resolver_module,
):
    from wingman.evefittings.eft import EftError, parse_eft, resolve_eft

    public = PublicInventory()
    requests = []
    failures = [503, 503]

    class Reply(io.BytesIO):
        status = 200

        def __init__(self, data):
            super().__init__(data)
            self.headers = {"ETag": '"test"'}

    def transport(request, timeout):
        requests.append(request)
        assert request.get_header("Authorization") is None
        path = request.full_url.split("esi.evetech.net")[1]
        if failures:
            raise urllib.error.HTTPError(
                request.full_url,
                failures.pop(),
                "Unavailable",
                {},
                io.BytesIO(b'{"error":"unavailable"}'),
            )
        response = (
            public.post(path, json.loads(request.data))
            if request.data
            else public.get(path)
        )
        return Reply(json.dumps(response.data).encode())

    sleeps = []
    client = EsiClient(
        user_agent="Wingman-test", transport=transport, sleep=sleeps.append
    )
    resolver = resolver_module.InventoryResolver(client, stopping=lambda: False)
    parsed = parse_eft("[Rifter, Fit]\nDamage Control II")
    assert resolve_eft(parsed, resolver.for_import(parsed)).items[0].type_id == 2048
    assert (
        len(sleeps) == 2 and sum(request.method == "POST" for request in requests) == 3
    )
    bad = EsiClient(
        user_agent="Wingman-test",
        transport=lambda *a, **k: Reply(b"not json"),
        sleep=lambda _: None,
    )
    with pytest.raises(EftError):
        resolver_module.InventoryResolver(bad, stopping=lambda: False).for_import(
            parsed
        )
