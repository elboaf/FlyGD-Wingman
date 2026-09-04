import json

from wingman.eveesi import EsiResponse


def esi_response(status, data=None, error=""):
    return EsiResponse(status, data, error, "", "POST", "/universe/names")


class RecordingClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def post(self, path, body, *, token=None):
        self.calls.append((path, list(body), token))
        return self.replies.pop(0)


def test_package_exports_controller_and_type_name_cache():
    from wingman import evefittings

    assert evefittings.FittingsController is not None
    assert evefittings.TypeNameCache is not None
    assert {"FittingsController", "TypeNameCache"} <= set(evefittings.__all__)


def test_type_name_lookup_is_unauthenticated_deduplicated_and_batched():
    from wingman.evefittings.names import MAX_BATCH, TypeNameCache

    type_ids = [*range(1, MAX_BATCH * 2 + 2), 1, True, 0, "2"]
    client = RecordingClient(
        [
            esi_response(200, []),
            esi_response(200, []),
            esi_response(
                200,
                [
                    {
                        "category": "inventory_type",
                        "id": MAX_BATCH * 2 + 1,
                        "name": "Last Type",
                    }
                ],
            ),
        ]
    )
    cache = TypeNameCache()

    changed = cache.resolve_missing(type_ids, client)

    assert changed is True
    assert [len(call[1]) for call in client.calls] == [MAX_BATCH, MAX_BATCH, 1]
    assert all(call[0] == "/universe/names" for call in client.calls)
    assert all(call[2] is None for call in client.calls)
    assert cache.label(MAX_BATCH * 2 + 1) == "Last Type"


def test_unresolved_fallback_is_bounded_even_for_pathological_ids():
    from wingman.evefittings.names import MAX_NAME_CHARS, TypeNameCache

    label = TypeNameCache().label(10**1000)

    assert label.startswith("Type ")
    assert len(label) <= MAX_NAME_CHARS


def test_cache_save_load_and_unresolved_fallback(tmp_path):
    from wingman.evefittings.names import TypeNameCache, load, save

    path = tmp_path / "eve_fitting_names.json"
    cache = TypeNameCache({34: "Tritanium", 587: "Rifter"})

    save(path, cache)
    loaded, warnings = load(path)

    assert warnings == ()
    assert loaded.type_names() == {34: "Tritanium", 587: "Rifter"}
    assert loaded.label(12345) == "Type 12345"


def test_cache_is_bounded_and_rebuilds_from_invalid_or_oversized_state(
    tmp_path, monkeypatch
):
    from wingman.evefittings import names

    cache = names.TypeNameCache()
    monkeypatch.setattr(names, "MAX_ENTRIES", 2)

    added = cache.merge({1: "One", 2: "Two", 3: "Three"})

    assert added == 2
    path = tmp_path / "eve_fitting_names.json"
    path.write_text("not json", encoding="utf-8")
    loaded, warnings = names.load(path)
    assert loaded.type_names() == {}
    assert warnings

    path.write_bytes(b"x" * (names.MAX_CACHE_BYTES + 1))
    loaded, warnings = names.load(path)
    assert loaded.type_names() == {}
    assert any("limit" in warning for warning in warnings)


def test_malformed_cache_rows_are_rebuildable_not_construction_failures(tmp_path):
    from wingman.evefittings import names

    path = tmp_path / "eve_fitting_names.json"
    path.write_text(
        json.dumps(
            {
                "version": names.CACHE_VERSION,
                "entries": [
                    {"type_id": [], "name": "Broken"},
                    {"type_id": 34, "name": "Tritanium"},
                ],
            }
        ),
        encoding="utf-8",
    )

    cache, warnings = names.load(path)

    assert cache.type_names() == {34: "Tritanium"}
    assert warnings == ()


def test_lookup_accepts_only_requested_inventory_types_with_bounded_names():
    from wingman.evefittings.names import MAX_NAME_CHARS, TypeNameCache

    client = RecordingClient(
        [
            esi_response(
                200,
                [
                    {"category": "inventory_type", "id": 1, "name": "One"},
                    {"category": "character", "id": 2, "name": "Pilot"},
                    {"category": "inventory_type", "id": 999, "name": "Injected"},
                    {
                        "category": "inventory_type",
                        "id": 3,
                        "name": "x" * (MAX_NAME_CHARS + 1),
                    },
                    {"category": "inventory_type", "id": True, "name": "Bool"},
                ],
            )
        ]
    )
    cache = TypeNameCache()

    cache.resolve_missing([1, 2, 3], client)

    assert cache.type_names() == {1: "One"}


def test_failed_name_lookup_is_cosmetic_and_not_persisted_as_identity(tmp_path):
    from tests.test_evefittings_refresh import fitting, make_controller, response

    controller, authority, esi, state_path = make_controller(
        tmp_path, [response(200, [fitting()])]
    )
    esi.post_reply = esi_response(503, None, "offline")

    result = controller.refresh([42])

    assert result["ok"] is True
    assert state_path.exists()
    assert len(controller.state.entries) == 1
    assert controller.type_name(100) == "Type 100"
    assert controller.type_name(200) == "Type 200"
    assert authority.active_character is None


def test_malformed_name_response_cannot_fail_a_committed_import(tmp_path):
    from tests.test_evefittings_refresh import fitting, make_controller, response

    controller, _authority, esi, state_path = make_controller(
        tmp_path, [response(200, [fitting()])]
    )
    esi.post_reply = object()

    result = controller.refresh([42])

    assert result["ok"] is True
    assert state_path.exists()
    assert controller.type_name(100) == "Type 100"


def test_304_retries_missing_names_from_retained_authoritative_data(tmp_path):
    from tests.test_evefittings_refresh import fitting, make_controller, response

    controller, _authority, esi, _state_path = make_controller(
        tmp_path,
        [response(200, [fitting()], etag='"one"'), response(304)],
    )
    esi.post_reply = esi_response(503, None, "offline")
    assert controller.refresh([42])["ok"] is True
    assert controller.type_name(100) == "Type 100"
    initial_name_calls = len(esi.post_calls)
    esi.post_reply = esi_response(
        200,
        [
            {"category": "inventory_type", "id": 100, "name": "Hull"},
            {"category": "inventory_type", "id": 200, "name": "Module"},
        ],
    )

    assert controller.refresh([42])["ok"] is True

    assert len(esi.post_calls) == initial_name_calls + 1
    assert controller.type_name(100) == "Hull"
    assert controller.type_name(200) == "Module"


def test_names_arrive_after_snapshot_commit_and_emit_a_semantic_change(tmp_path):
    from tests.test_evefittings_refresh import FakeAuthority, FakeEsi, fitting, response
    from wingman.evefittings.controller import FittingsController
    from wingman.evefittings.store import save_fittings

    authority = FakeAuthority((42,))
    esi = FakeEsi([response(200, [fitting()])])
    esi.authority = authority
    esi.post_reply = esi_response(
        200,
        [
            {"category": "inventory_type", "id": 100, "name": "Hull"},
            {"category": "inventory_type", "id": 200, "name": "Module"},
        ],
    )
    changes = []
    state_path = tmp_path / "eve_fittings.json"
    saved_before_name_lookup = []

    def checked_save(path, state):
        save_fittings(path, state)
        saved_before_name_lookup.append(path.exists())

    controller = FittingsController(
        state_path=state_path,
        names_path=tmp_path / "eve_fitting_names.json",
        authority=authority,
        client=esi,
        changed=changes.append,
        save_state=checked_save,
    )
    authority.feature_lock = controller._lock

    assert controller.refresh([42])["ok"] is True

    assert saved_before_name_lookup == [True]
    assert authority.events == [("enter", 42), ("exit", 42)]
    assert controller.type_name(100) == "Hull"
    assert controller.type_name(200) == "Module"
    assert changes == [{"reason": "type_names", "type_ids": [100, 200]}]
    persisted = json.loads(
        (tmp_path / "eve_fitting_names.json").read_text(encoding="utf-8")
    )
    assert persisted["entries"]
    assert all(
        "name" not in item for item in json.loads(state_path.read_text())["entries"]
    )


def test_semantic_change_callback_failure_cannot_fail_a_committed_import(tmp_path):
    from tests.test_evefittings_refresh import FakeAuthority, FakeEsi, fitting, response
    from wingman.evefittings.controller import FittingsController

    authority = FakeAuthority((42,))
    esi = FakeEsi([response(200, [fitting()])])
    esi.authority = authority
    esi.post_reply = esi_response(
        200, [{"category": "inventory_type", "id": 100, "name": "Hull"}]
    )

    def broken_change(_payload):
        raise RuntimeError("page closed")

    controller = FittingsController(
        state_path=tmp_path / "eve_fittings.json",
        names_path=tmp_path / "eve_fitting_names.json",
        authority=authority,
        client=esi,
        changed=broken_change,
    )

    assert controller.refresh([42])["ok"] is True
    assert controller.type_name(100) == "Hull"
