"""`Api`'s Fittings bridge methods: thin delegation and safe fallbacks.

Task 6 added `Api.fittings_state()` as an always-"unavailable" stub ahead of
a controller. Task 8 wired the private `_fittings` dependency slot without
touching the public method. This file is what Task 9 replaces both with:
every method here does the minimum work of validating/coercing bridge
arguments, delegating to `self._fittings` (or `self._authority`), and
falling back to a safe, stable shape when the dependency is absent --
"unavailable-controller fallbacks" from the SDD brief.

Controller-level query/curation behavior (workspace filtering, paging,
metadata edits, and so on) is covered in tests/test_fittings_wiring.py; this
file only proves the bridge calls through correctly and degrades safely.
"""

import threading
import time
from unittest.mock import Mock

from tests.test_api import make_api


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ---- the private dependency slot (Task 8, unchanged) ----------------------


def test_fittings_controller_is_kept_in_a_private_dependency_slot(tmp_path):
    marker = object()
    api = make_api(tmp_path, fittings=marker)

    assert api._fittings is marker
    assert "fittings" not in vars(api)


# ---- fittings_state: thin delegate and unavailable fallback --------------


def test_fittings_state_is_a_thin_delegate(tmp_path):
    fittings = Mock()
    api = make_api(tmp_path, fittings=fittings)

    result = api.fittings_state({"page": 1})

    assert result == fittings.workspace.return_value
    fittings.workspace.assert_called_once_with({"page": 1})


def test_fittings_state_takes_an_optional_filters_argument(tmp_path):
    """fittings.js may ask with no argument on a route re-entry guard
    failure or a defensive retry; the method must not require one."""
    import inspect

    from wingman.ui.api import Api

    parameters = inspect.signature(Api.fittings_state).parameters
    assert list(parameters) == ["self", "filters"]
    assert parameters["filters"].default is None


def test_fittings_state_answers_unavailable_with_no_controller(tmp_path):
    api = make_api(tmp_path)

    payload = api.fittings_state({"page": 1})

    assert payload["available"] is False
    assert payload["warnings"] == ["The EVE fitting library is not available yet."]


def test_fittings_state_unavailable_fallback_does_not_touch_a_controller(tmp_path):
    """A caller that hands over a broken/absent dependency must get the
    safe fallback rather than an AttributeError reaching the page."""
    api = make_api(tmp_path, fittings=None)

    assert api.fittings_state(None)["available"] is False


# ---- fittings_detail ------------------------------------------------------


def test_fittings_detail_is_a_thin_delegate(tmp_path):
    fittings = Mock()
    api = make_api(tmp_path, fittings=fittings)

    result = api.fittings_detail("entry-1")

    assert result == fittings.detail.return_value
    fittings.detail.assert_called_once_with("entry-1")


def test_fittings_detail_answers_none_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_detail("entry-1") is None


# ---- fittings_refresh: fire-and-forget worker ----------------------------


def test_fittings_refresh_uses_the_injected_worker_factory(tmp_path):
    from tests.test_api import pushes

    fittings = Mock()
    fittings.refresh.return_value = {"ok": True}
    constructed = []

    class ImmediateWorker:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            self._target = kwargs["target"]
            self._args = kwargs["args"]

        def start(self):
            self._target(*self._args)

    api = make_api(tmp_path, fittings=fittings, spawn=ImmediateWorker)

    assert api.fittings_refresh([42]) is True
    assert len(constructed) == 1
    fittings.refresh.assert_called_once_with([42])
    assert pushes(api._window) == [("onFittingsChanged", {"reason": "refresh"})]


def test_fittings_refresh_construction_failure_clears_optimistic_state(tmp_path):
    from tests.test_api import pushes

    fittings = Mock()
    attempts = []

    def fail_spawn(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("cannot construct worker")

    api = make_api(tmp_path, fittings=fittings, spawn=fail_spawn)

    assert api.fittings_refresh([42]) is False
    assert len(attempts) == 1
    fittings.refresh.assert_not_called()
    assert pushes(api._window) == [("onFittingsChanged", {"reason": "refresh"})]


def test_fittings_refresh_start_failure_clears_optimistic_state(tmp_path):
    from tests.test_api import pushes

    fittings = Mock()
    starts = []

    class StartFailureWorker:
        def start(self):
            starts.append(True)
            raise RuntimeError("cannot start worker")

    api = make_api(
        tmp_path, fittings=fittings, spawn=lambda **_kwargs: StartFailureWorker()
    )

    assert api.fittings_refresh([42]) is False
    assert starts == [True]
    fittings.refresh.assert_not_called()
    assert pushes(api._window) == [("onFittingsChanged", {"reason": "refresh"})]


def test_fittings_refresh_spawns_a_worker_and_returns_immediately(tmp_path):
    started = threading.Event()
    release = threading.Event()

    class SlowFittings:
        def refresh(self, character_ids):
            started.set()
            assert release.wait(2)
            return {"ok": True}

    api = make_api(tmp_path, fittings=SlowFittings())

    result = api.fittings_refresh([42])

    assert result is True
    assert started.wait(1), "fittings_refresh must not block the caller"
    release.set()


def test_fittings_refresh_pushes_a_completion_notice(tmp_path):
    fittings = Mock()
    fittings.refresh.return_value = {"ok": True}
    api = make_api(tmp_path, fittings=fittings)

    api.fittings_refresh([42])

    assert _wait_for(lambda: bool(api._window.evaluated))
    assert "onFittingsChanged" in api._window.evaluated[-1]
    fittings.refresh.assert_called_once_with([42])


def test_fittings_refresh_surfaces_aggregate_refusals_before_change_notice(tmp_path):
    from tests.test_api import pushes

    cases = (
        {
            "ok": False,
            "busy": True,
            "batch_id": "",
            "characters": [],
            "error": "A fitting refresh is already in progress.",
        },
        {
            "ok": False,
            "busy": False,
            "batch_id": "",
            "characters": [],
            "error": "The fitting subsystem is shutting down.",
        },
        {
            "ok": False,
            "busy": False,
            "batch_id": "batch-1",
            "characters": [
                {
                    "character_id": 42,
                    "ok": False,
                    "error": "Unknown EVE character.",
                }
            ],
            "error": "Unknown EVE character.",
        },
    )

    for result in cases:
        fittings = Mock()
        fittings.refresh.return_value = result
        api = make_api(tmp_path, fittings=fittings)

        api._fittings_refresh_worker([42])

        assert pushes(api._window) == [
            (
                "onFittingsProgress",
                {
                    "kind": "refresh",
                    "phase": "complete",
                    "completed": len(result["characters"]),
                    "total": len(result["characters"]),
                    "busy": result["busy"],
                    "error": result["error"],
                },
            ),
            ("onFittingsChanged", {"reason": "refresh"}),
        ]


def test_fittings_refresh_coerces_a_non_list_argument_to_none(tmp_path):
    fittings = Mock()
    fittings.refresh.return_value = {"ok": True}
    api = make_api(tmp_path, fittings=fittings)

    api.fittings_refresh("not-a-list")

    assert _wait_for(lambda: fittings.refresh.called)
    fittings.refresh.assert_called_once_with(None)


def test_fittings_refresh_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_refresh([42]) is False


# ---- character access now lives in Settings ------------------------------


def test_fittings_no_longer_exposes_character_auth_or_forget_bridge_methods(tmp_path):
    from wingman.ui.api import Api

    api = make_api(tmp_path)

    for name in (
        "fittings_enable_character",
        "fittings_cancel_auth",
        "fittings_forget_character",
    ):
        assert getattr(Api, name, None) is None
        assert getattr(api, name, None) is None


# ---- additive copy: preflight / worker start / cancellation --------------


def test_fittings_preflight_copy_delegates_selected_ids_targets_and_names(tmp_path):
    fittings = Mock()
    fittings.preflight_copy.return_value = {"accepted": True, "ticket_id": "ticket"}
    api = make_api(tmp_path, fittings=fittings)
    names = {"fit-1:42": "Alternate"}

    result = api.fittings_preflight_copy(["fit-1"], [42], names)

    assert result == {"accepted": True, "ticket_id": "ticket"}
    fittings.preflight_copy.assert_called_once_with(["fit-1"], [42], names)


def test_fittings_preflight_copy_has_a_safe_unavailable_fallback(tmp_path):
    api = make_api(tmp_path)

    result = api.fittings_preflight_copy(["fit-1"], [42], {})

    assert result["accepted"] is False
    assert result["ticket_id"] == ""
    assert result["error"]


def test_fittings_start_copy_uses_the_injected_worker_factory(tmp_path):
    fittings = Mock()
    fittings.start_copy.return_value = {
        "status": "invalid_ticket",
        "operation_id": "",
        "results": [],
        "write_count": 0,
    }
    constructed = []

    class ImmediateWorker:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            self._target = kwargs["target"]
            self._args = kwargs["args"]

        def start(self):
            self._target(*self._args)

    api = make_api(tmp_path, fittings=fittings, spawn=ImmediateWorker)

    assert api.fittings_start_copy("ticket-1") is True
    assert len(constructed) == 1
    fittings.start_copy.assert_called_once_with("ticket-1")


def test_fittings_start_copy_construction_failure_completes_optimistic_copy(tmp_path):
    from tests.test_api import pushes

    fittings = Mock()
    attempts = []

    def fail_spawn(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("cannot construct worker")

    api = make_api(tmp_path, fittings=fittings, spawn=fail_spawn)

    assert api.fittings_start_copy("ticket-1") is False
    assert len(attempts) == 1
    fittings.start_copy.assert_not_called()
    assert pushes(api._window) == [
        (
            "onFittingsProgress",
            {
                "kind": "copy",
                "phase": "complete",
                "operation_id": "",
                "completed": 0,
                "total": 0,
                "result": {
                    "status": "failed",
                    "operation_id": "",
                    "results": [],
                    "write_count": 0,
                },
            },
        )
    ]


def test_fittings_start_copy_start_failure_completes_optimistic_copy(tmp_path):
    from tests.test_api import pushes

    fittings = Mock()
    starts = []

    class StartFailureWorker:
        def start(self):
            starts.append(True)
            raise RuntimeError("cannot start worker")

    api = make_api(
        tmp_path, fittings=fittings, spawn=lambda **_kwargs: StartFailureWorker()
    )

    assert api.fittings_start_copy("ticket-1") is False
    assert starts == [True]
    fittings.start_copy.assert_not_called()
    assert pushes(api._window) == [
        (
            "onFittingsProgress",
            {
                "kind": "copy",
                "phase": "complete",
                "operation_id": "",
                "completed": 0,
                "total": 0,
                "result": {
                    "status": "failed",
                    "operation_id": "",
                    "results": [],
                    "write_count": 0,
                },
            },
        )
    ]


def test_fittings_start_copy_runs_on_a_worker(tmp_path):
    started = threading.Event()
    release = threading.Event()

    class SlowFittings:
        def start_copy(self, ticket_id):
            assert ticket_id == "ticket-1"
            started.set()
            assert release.wait(2)

    api = make_api(tmp_path, fittings=SlowFittings())

    assert api.fittings_start_copy("ticket-1") is True
    assert started.wait(1), "the bridge must return while copy runs"
    release.set()


def test_fittings_start_copy_pushes_an_early_controller_refusal(tmp_path):
    from tests.test_api import pushes

    fittings = Mock()
    fittings.start_copy.return_value = {
        "status": "invalid_ticket",
        "operation_id": "",
        "results": [],
        "write_count": 0,
    }
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_start_copy("expired-ticket") is True
    assert _wait_for(lambda: bool(api._window.evaluated))
    assert pushes(api._window) == [
        (
            "onFittingsProgress",
            {
                "kind": "copy",
                "phase": "complete",
                "operation_id": "",
                "completed": 0,
                "total": 0,
                "result": fittings.start_copy.return_value,
            },
        )
    ]


def test_fittings_start_copy_rejects_empty_or_unavailable_ticket(tmp_path):
    fittings = Mock()
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_start_copy("") is False
    assert make_api(tmp_path).fittings_start_copy("ticket") is False
    fittings.start_copy.assert_not_called()


def test_fittings_cancel_copy_delegates(tmp_path):
    fittings = Mock()
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_cancel_copy() is True
    fittings.cancel_copy.assert_called_once_with()


def test_fittings_cancel_copy_is_safe_when_unavailable(tmp_path):
    assert make_api(tmp_path).fittings_cancel_copy() is True


# ---- local curation: thin delegates and unavailable fallbacks ------------


def test_fittings_create_collection_delegates(tmp_path):
    fittings = Mock()
    fittings.create_collection.return_value = "new-id"
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_create_collection("Alliance") == "new-id"
    fittings.create_collection.assert_called_once_with("Alliance")


def test_fittings_create_collection_answers_empty_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_create_collection("Alliance") == ""


def test_fittings_rename_collection_delegates(tmp_path):
    fittings = Mock()
    fittings.rename_collection.return_value = True
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_rename_collection("c1", "New Name") is True
    fittings.rename_collection.assert_called_once_with("c1", "New Name")


def test_fittings_rename_collection_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_rename_collection("c1", "New Name") is False


def test_fittings_delete_collection_delegates(tmp_path):
    fittings = Mock()
    fittings.delete_collection.return_value = True
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_delete_collection("c1") is True
    fittings.delete_collection.assert_called_once_with("c1")


def test_fittings_delete_collection_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_delete_collection("c1") is False


def test_fittings_update_metadata_delegates(tmp_path):
    fittings = Mock()
    fittings.update_metadata.return_value = True
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_update_metadata("e1", "Name", "Description") is True
    fittings.update_metadata.assert_called_once_with("e1", "Name", "Description")


def test_fittings_update_metadata_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_update_metadata("e1", "Name", "Description") is False


def test_fittings_set_membership_delegates(tmp_path):
    fittings = Mock()
    fittings.set_membership.return_value = True
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_set_membership("e1", "c1", True) is True
    fittings.set_membership.assert_called_once_with("e1", "c1", True)


def test_fittings_set_membership_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_set_membership("e1", "c1", True) is False


def test_fittings_set_supersession_delegates(tmp_path):
    fittings = Mock()
    fittings.set_supersession.return_value = True
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_set_supersession("e1", "e2") is True
    fittings.set_supersession.assert_called_once_with("e1", "e2")


def test_fittings_set_supersession_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_set_supersession("e1", "e2") is False


def test_fittings_delete_entry_delegates(tmp_path):
    fittings = Mock()
    fittings.delete_entry.return_value = True
    api = make_api(tmp_path, fittings=fittings)

    assert api.fittings_delete_entry("e1") is True
    fittings.delete_entry.assert_called_once_with("e1")


def test_fittings_delete_entry_answers_false_with_no_controller(tmp_path):
    api = make_api(tmp_path)
    assert api.fittings_delete_entry("e1") is False


# ---- literal push adapters ------------------------------------------------


def test_push_fittings_changed_uses_the_literal_handler_name(tmp_path):
    from tests.test_api import pushes

    api = make_api(tmp_path)

    api._push_fittings_changed({"reason": "refresh"})

    assert pushes(api._window) == [("onFittingsChanged", {"reason": "refresh"})]


def test_push_fittings_progress_uses_the_literal_handler_name(tmp_path):
    from tests.test_api import pushes

    api = make_api(tmp_path)

    api._push_fittings_progress({"completed": 1, "total": 2})

    assert pushes(api._window) == [("onFittingsProgress", {"completed": 1, "total": 2})]
