"""FittingsController's paged workspace/detail queries and local curation.

Task 9 replaces the Task 6 unavailable-state stub with real controller
delegation. This file is the controller-level half of that: the bridge-level
half (thin delegation, unavailable fallbacks, argument shapes) lives in
tests/test_api_fittings.py.

Search, collection selection, sorting, and pagination are backend queries --
the design doc is explicit the catalog may hold thousands of entries and the
route must never rebuild or send the full library. A summary row therefore
never carries the full detail a caller did not ask for, and every mutation
here notifies through the same `changed` callback the refresh path already
uses, so the page can re-query its current view rather than receive a
second, competing payload shape.
"""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from wingman.evefittings import contracts
from wingman.evefittings.controller import FittingsController
from wingman.evefittings.model import (
    Collection,
    Presence,
    new_library_entry,
    validate_remote_snapshot,
)
from wingman.evefittings.store import save_fittings

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _remote(*, fitting_id, ship_type_id, name, type_id):
    return validate_remote_snapshot(
        [
            {
                "fitting_id": fitting_id,
                "ship_type_id": ship_type_id,
                "name": name,
                "description": f"Description for {name}",
                "items": [{"flag": "HiSlot0", "quantity": 1, "type_id": type_id}],
            }
        ]
    )[0]


def make_entry(
    index,
    *,
    ship_type_id=100,
    name=None,
    collection_ids=(),
    superseded_by=None,
    entry_id=None,
):
    remote = _remote(
        fitting_id=index,
        ship_type_id=ship_type_id,
        name=name or f"Fit {index:03d}",
        type_id=200 + index,
    )
    entry = new_library_entry(remote, entry_id=entry_id or f"entry-{index}", now=NOW)
    return replace(
        entry, collection_ids=tuple(collection_ids), superseded_by=superseded_by
    )


def make_presence(entry, *, character_id=42, batch_id="batch-1", first_seen=NOW):
    return Presence(
        character_id=character_id,
        remote_fitting_id=1000 + character_id,
        library_entry_id=entry.id,
        source_name=entry.preferred_name,
        source_description=entry.preferred_description,
        source_template=entry.source_template,
        first_seen_utc=first_seen,
        discovered_batch_id=batch_id,
        last_confirmed_utc=first_seen,
    )


class FakeAuthority:
    def __init__(self, character_ids=(42, 43)):
        self._ids = tuple(character_ids)
        self.auth_in_progress = False
        self.persistence_errors = {}

    @property
    def characters(self):
        return tuple(
            SimpleNamespace(
                character_id=value,
                character_name=f"Pilot {value}",
                persistence_error=self.persistence_errors.get(value, ""),
            )
            for value in self._ids
        )

    def capability_status(self, character_id, capability):
        assert capability == "fittings"
        return "enabled" if character_id in self._ids else "missing"

    def character(self, character_id):
        if character_id not in self._ids:
            return None
        return SimpleNamespace(character_id=character_id, owner_hash="owner")


def make_controller(tmp_path, *, initial=None, changed=None, progress=None, alert=None):
    state_path = tmp_path / "eve_fittings.json"
    if initial is not None:
        save_fittings(state_path, initial)
    authority = FakeAuthority()
    ids = iter(f"created-{index}" for index in range(1000))
    controller = FittingsController(
        state_path=state_path,
        names_path=tmp_path / "eve_fitting_names.json",
        authority=authority,
        client=SimpleNamespace(get=None, post=None),
        now=lambda: NOW,
        changed=changed or (lambda payload: None),
        progress=progress or (lambda payload: None),
        alert=alert or (lambda kind, title, body: None),
        id_factory=lambda: next(ids),
    )
    return controller, authority


# ---- workspace: paging, filters, sorting -------------------------------


def test_workspace_returns_one_bounded_page(tmp_path):
    from wingman.evefittings.model import FittingsState

    entries = tuple(make_entry(i) for i in range(1, 251))
    controller, _authority = make_controller(
        tmp_path, initial=FittingsState(entries=entries)
    )
    payload = controller.workspace({"collection_id": "all", "page": 2})

    assert payload["available"] is True
    assert len(payload["rows"]) <= contracts.PAGE_SIZE
    assert "details" not in payload["rows"][0]
    assert payload["total"] == len(entries)
    assert payload["page"] == 2
    assert payload["page_size"] == contracts.PAGE_SIZE


def test_workspace_character_summary_includes_authority_persistence_error(tmp_path):
    controller, authority = make_controller(tmp_path)
    authority.persistence_errors[42] = "The refreshed EVE grant could not be saved."

    rows = {row["character_id"]: row for row in controller.workspace({})["characters"]}

    assert rows[42]["error"] == "The refreshed EVE grant could not be saved."


def test_workspace_filters_by_collection_all_unfiled_superseded_and_custom(tmp_path):
    from wingman.evefittings.model import FittingsState

    filed = make_entry(1, name="Filed Fit", collection_ids=("alliance",))
    unfiled = make_entry(2, name="Unfiled Fit")
    # Filed as well as superseded, so this scope's membership is isolated
    # from Unfiled's -- the two are orthogonal facts about an entry (a
    # superseded entry with no collection is legitimately both at once).
    superseded = make_entry(
        3, name="Old Fit", superseded_by=filed.id, collection_ids=("alliance",)
    )
    state = FittingsState(
        entries=(filed, unfiled, superseded),
        collections=(Collection(id="alliance", name="Alliance"),),
    )
    controller, _authority = make_controller(tmp_path, initial=state)

    all_ids = {
        row["id"] for row in controller.workspace({"collection_id": "all"})["rows"]
    }
    assert all_ids == {filed.id, unfiled.id, superseded.id}

    unfiled_ids = {
        row["id"] for row in controller.workspace({"collection_id": "unfiled"})["rows"]
    }
    assert unfiled_ids == {unfiled.id}

    superseded_ids = {
        row["id"]
        for row in controller.workspace({"collection_id": "superseded"})["rows"]
    }
    assert superseded_ids == {superseded.id}

    custom_ids = {
        row["id"] for row in controller.workspace({"collection_id": "alliance"})["rows"]
    }
    assert custom_ids == {filed.id, superseded.id}


def test_workspace_search_filters_by_name(tmp_path):
    from wingman.evefittings.model import FittingsState

    apple = make_entry(1, name="Apple Interceptor")
    banana = make_entry(2, name="Banana Cruiser")
    state = FittingsState(entries=(apple, banana))
    controller, _authority = make_controller(tmp_path, initial=state)

    rows = controller.workspace({"search": "apple"})["rows"]
    assert [row["id"] for row in rows] == [apple.id]

    rows = controller.workspace({"search": "CRUISER"})["rows"]
    assert [row["id"] for row in rows] == [banana.id]

    rows = controller.workspace({"search": "nonexistent"})["rows"]
    assert rows == []


def test_workspace_ship_filter(tmp_path):
    from wingman.evefittings.model import FittingsState

    rifter = make_entry(1, ship_type_id=100, name="A Rifter fit")
    merlin = make_entry(2, ship_type_id=200, name="A Merlin fit")
    state = FittingsState(entries=(rifter, merlin))
    controller, _authority = make_controller(tmp_path, initial=state)

    rows = controller.workspace({"ship_type_id": 100})["rows"]
    assert [row["id"] for row in rows] == [rifter.id]


def test_workspace_sorting_is_stable_and_casefolded(tmp_path):
    from wingman.evefittings.model import FittingsState

    zebra = make_entry(1, name="zebra", entry_id="z")
    alpha = make_entry(2, name="Alpha", entry_id="a")
    apple = make_entry(3, name="alpha", entry_id="b")
    state = FittingsState(entries=(zebra, alpha, apple))
    controller, _authority = make_controller(tmp_path, initial=state)

    rows = controller.workspace({})["rows"]
    # Case-insensitive name order; ties break on stable entry id.
    assert [row["id"] for row in rows] == ["a", "b", "z"]

    # Repeated calls agree -- nothing here depends on dict/set iteration order.
    rows_again = controller.workspace({})["rows"]
    assert [row["id"] for row in rows_again] == ["a", "b", "z"]


def test_workspace_reports_characters_and_refresh_state_without_auth_controls(tmp_path):
    controller, _authority = make_controller(tmp_path)
    payload = controller.workspace({})

    assert {row["character_id"] for row in payload["characters"]} == {42, 43}
    for row in payload["characters"]:
        assert row["status"] == "enabled"
    assert payload["refreshing"] is False
    assert "auth_configured" not in payload
    assert "auth_in_progress" not in payload


def test_workspace_defaults_are_forgiving_of_malformed_filters(tmp_path):
    controller, _authority = make_controller(tmp_path)

    payload = controller.workspace(None)
    assert payload["page"] == 1
    assert payload["filters"]["collection_id"] == "all"

    payload = controller.workspace({"page": "not-a-number", "ship_type_id": "nope"})
    assert payload["page"] == 1
    assert payload["filters"]["ship_type_id"] is None


# ---- detail -------------------------------------------------------------


def test_detail_returns_full_fitting_with_items_aliases_presences(tmp_path):
    from wingman.evefittings.model import FittingsState

    entry = make_entry(1, name="Detailed Fit")
    presence = make_presence(entry, character_id=42)
    state = FittingsState(entries=(entry,), presences=(presence,))
    controller, _authority = make_controller(tmp_path, initial=state)

    detail = controller.detail(entry.id)

    assert detail["id"] == entry.id
    assert detail["name"] == "Detailed Fit"
    assert detail["items"][0]["type_id"] == 201
    assert detail["aliases"][0]["name"] == "Detailed Fit"
    assert detail["presences"] == [
        {
            "character_id": 42,
            "character_name": "Pilot 42",
            "source_name": "Detailed Fit",
            "first_seen_utc": presence.first_seen_utc.isoformat(),
            "last_confirmed_utc": presence.last_confirmed_utc.isoformat(),
            "discovered_batch_id": "batch-1",
        }
    ]
    assert "rows" not in detail


def test_detail_returns_none_for_unknown_id(tmp_path):
    controller, _authority = make_controller(tmp_path)
    assert controller.detail("nonexistent") is None
    assert controller.detail("") is None
    assert controller.detail(None) is None


# ---- collections ---------------------------------------------------------


def test_create_rename_delete_collection_round_trip(tmp_path):
    changed = []
    controller, _authority = make_controller(
        tmp_path, changed=lambda payload: changed.append(payload)
    )

    collection_id = controller.create_collection("Alliance")
    assert collection_id
    assert changed[-1] == {"reason": "collection", "collection_id": collection_id}
    names = {c["name"] for c in controller.workspace({})["collections"]}
    assert "Alliance" in names

    assert controller.rename_collection(collection_id, "Alliance Ops") is True
    names = {c["name"] for c in controller.workspace({})["collections"]}
    assert "Alliance Ops" in names and "Alliance" not in names

    assert controller.delete_collection(collection_id) is True
    names = {c["name"] for c in controller.workspace({})["collections"]}
    assert "Alliance Ops" not in names


def test_create_collection_refuses_an_empty_or_oversized_name(tmp_path):
    alerts = []
    controller, _authority = make_controller(
        tmp_path, alert=lambda kind, title, body: alerts.append((kind, title, body))
    )

    assert controller.create_collection("") == ""
    assert controller.create_collection("x" * 500) == ""
    assert alerts, "an invalid name must alert rather than fail silently"


def test_delete_collection_removes_membership_but_not_the_fitting(tmp_path):

    controller, _authority = make_controller(tmp_path)
    collection_id = controller.create_collection("Alliance")
    entry = make_entry(1, name="Filed", collection_ids=(collection_id,))
    # Publish directly to attach a real entry to the freshly created collection.
    with controller._lock:
        candidate = replace(controller._state, entries=(entry,))
        controller._publish_locked(candidate)

    assert controller.delete_collection(collection_id) is True
    rows = controller.workspace({"collection_id": "all"})["rows"]
    assert [row["id"] for row in rows] == [entry.id]
    assert rows[0]["collection_ids"] == []


# ---- metadata / membership / supersession / delete ------------------------


def test_update_metadata_persists_and_validates_bounds(tmp_path):
    from wingman.evefittings.model import FittingsState

    entry = make_entry(1, name="Old Name")
    state = FittingsState(entries=(entry,))
    changed = []
    controller, _authority = make_controller(
        tmp_path, initial=state, changed=lambda payload: changed.append(payload)
    )

    assert controller.update_metadata(entry.id, "New Name", "New description") is True
    rows = controller.workspace({})["rows"]
    assert rows[0]["name"] == "New Name"
    assert changed[-1] == {"reason": "metadata", "entry_id": entry.id}

    assert controller.update_metadata(entry.id, "", "description") is False
    assert controller.update_metadata(entry.id, "x" * 100, "description") is False
    assert controller.update_metadata(entry.id, "Name", "x" * 1000) is False
    assert controller.update_metadata("nonexistent", "Name", "") is False


def test_set_membership_toggles_and_requires_existing_collection(tmp_path):
    from wingman.evefittings.model import FittingsState

    entry = make_entry(1)
    state = FittingsState(entries=(entry,))
    controller, _authority = make_controller(tmp_path, initial=state)
    collection_id = controller.create_collection("Alliance")

    assert controller.set_membership(entry.id, collection_id, True) is True
    rows = controller.workspace({"collection_id": collection_id})["rows"]
    assert [row["id"] for row in rows] == [entry.id]

    assert controller.set_membership(entry.id, collection_id, False) is True
    rows = controller.workspace({"collection_id": collection_id})["rows"]
    assert rows == []

    assert controller.set_membership(entry.id, "nonexistent-collection", True) is False
    assert controller.set_membership("nonexistent-entry", collection_id, True) is False


def test_set_supersession_validates_same_hull_and_acyclic(tmp_path):
    from wingman.evefittings.model import FittingsState

    old = make_entry(1, ship_type_id=100, name="Old", entry_id="old")
    new = make_entry(2, ship_type_id=100, name="New", entry_id="new")
    other_hull = make_entry(3, ship_type_id=200, name="Other hull", entry_id="other")
    state = FittingsState(entries=(old, new, other_hull))
    controller, _authority = make_controller(tmp_path, initial=state)

    assert controller.set_supersession("old", "new") is True
    rows = {row["id"]: row for row in controller.workspace({})["rows"]}
    assert rows["old"]["superseded_by"] == "new"

    # Different hull is refused.
    assert controller.set_supersession("new", "other") is False

    # A cycle is refused.
    assert controller.set_supersession("new", "old") is False

    # Clearing the edge is allowed.
    assert controller.set_supersession("old", None) is True
    rows = {row["id"]: row for row in controller.workspace({})["rows"]}
    assert rows["old"]["superseded_by"] is None


def test_delete_entry_refuses_while_present_and_succeeds_once_absent(tmp_path):
    from wingman.evefittings.model import FittingsState

    entry = make_entry(1, name="Present Fit")
    presence = make_presence(entry)
    state = FittingsState(entries=(entry,), presences=(presence,))
    alerts = []
    controller, _authority = make_controller(
        tmp_path, initial=state, alert=lambda kind, title, body: alerts.append(title)
    )

    assert controller.delete_entry(entry.id) is False
    assert alerts
    assert [row["id"] for row in controller.workspace({})["rows"]] == [entry.id]

    # Once the character no longer has it, deletion is explicit and succeeds.
    with controller._lock:
        controller._publish_locked(replace(controller._state, presences=()))
    assert controller.delete_entry(entry.id) is True
    assert controller.workspace({})["rows"] == []


def test_delete_entry_clears_supersession_edges_pointing_at_it(tmp_path):
    from wingman.evefittings.model import FittingsState

    old = make_entry(1, ship_type_id=100, name="Old", entry_id="old")
    new = make_entry(
        2, ship_type_id=100, name="New", entry_id="new", superseded_by="old"
    )
    state = FittingsState(entries=(old, new))
    controller, _authority = make_controller(tmp_path, initial=state)

    assert controller.delete_entry("old") is True
    rows = {row["id"]: row for row in controller.workspace({})["rows"]}
    assert rows["new"]["superseded_by"] is None


def test_delete_entry_unknown_id_is_a_no_op(tmp_path):
    controller, _authority = make_controller(tmp_path)
    assert controller.delete_entry("nonexistent") is False
    assert controller.delete_entry("") is False
    assert controller.delete_entry(None) is False


# ---- refresh progress producer -------------------------------------------


def test_refresh_reports_progress_per_character(tmp_path, monkeypatch):
    progress_calls = []
    controller, _authority = make_controller(
        tmp_path, progress=lambda payload: progress_calls.append(payload)
    )

    def fake_refresh_one(character_id, batch_id):
        return {
            "character_id": character_id,
            "ok": True,
            "not_modified": False,
            "error": "",
        }

    monkeypatch.setattr(controller, "_refresh_one", fake_refresh_one)

    controller.refresh([42, 43])

    assert [call["character_id"] for call in progress_calls] == [42, 43]
    assert [call["completed"] for call in progress_calls] == [1, 2]
    assert all(call["total"] == 2 for call in progress_calls)
    assert all(call["error"] == "" for call in progress_calls)


# ---- production wiring (__main__.build_fittings_controller) --------------


def test_production_builder_passes_bound_change_and_progress_callbacks(
    tmp_path, monkeypatch
):
    """Mirrors test_skills_wiring.py's own bound-method check: a name
    resolved lazily inside a lambda is not checked when the builder runs,
    so a wrong alias ships green and fails on a user's machine the first
    time a push happens."""
    from wingman import __main__ as main_mod

    class FakeAuthorityForMain:
        characters = ()
        auth_in_progress = False

        def capability_status(self, character_id, capability):
            return "missing"

    class FakeApi:
        def __init__(self):
            self._alert_calls = []

        def _alert(self, *args):
            self._alert_calls.append(args)

        def _push_fittings_changed(self, payload):
            pass

        def _push_fittings_progress(self, payload):
            pass

    monkeypatch.setattr(
        main_mod.paths, "eve_fittings_file", lambda: tmp_path / "eve_fittings.json"
    )
    monkeypatch.setattr(
        main_mod.paths,
        "eve_fittings_names_file",
        lambda: tmp_path / "eve_fitting_names.json",
    )

    api = FakeApi()
    controller = main_mod.build_fittings_controller(api, FakeAuthorityForMain())
    assert controller is not None
    assert controller._changed == api._push_fittings_changed
    assert controller._progress == api._push_fittings_progress
    assert controller._alert == api._alert


def test_workspace_ship_options_reflect_collection_scope_before_search(tmp_path):
    from wingman.evefittings.model import FittingsState

    filed = make_entry(1, ship_type_id=100, name="Filed Fit", collection_ids=("a",))
    unfiled = make_entry(2, ship_type_id=200, name="Unfiled Fit")
    state = FittingsState(
        entries=(filed, unfiled), collections=(Collection(id="a", name="Alliance"),)
    )
    controller, _authority = make_controller(tmp_path, initial=state)

    payload = controller.workspace({"collection_id": "a", "search": "nonexistent"})
    assert payload["rows"] == []
    assert [ship["type_id"] for ship in payload["ships"]] == [100]

    payload = controller.workspace({"collection_id": "all"})
    assert sorted(ship["type_id"] for ship in payload["ships"]) == [100, 200]
