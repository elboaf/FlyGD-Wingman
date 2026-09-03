"""`Api.fittings_state`, the Task 6 unavailable-state stub.

The SDD ledger's ruling for this task: add a minimal `fittings_state` that
always answers "unavailable" so the route's one bridge call resolves to a
real method rather than throwing at the console with a dead route behind
it. There is deliberately no `_fittings` controller slot yet -- Task 8 adds
it, Task 9 replaces this stub with real delegation -- so this only has to
prove the method exists, is callable with no arguments, and answers a safe,
stable shape.
"""

from tests.test_api import make_api


def test_fittings_state_answers_unavailable(tmp_path):
    api = make_api(tmp_path)

    payload = api.fittings_state()

    assert payload["available"] is False
    assert payload["warnings"] == ["The EVE fitting library is not available yet."]


def test_fittings_state_takes_no_arguments(tmp_path):
    """The page calls this with nothing (see fittings.js): `WM.send(
    'fittings_state')` passes no arguments across the bridge, so a stub
    that requires one would fail on the very first route entry."""
    import inspect

    from wingman.ui.api import Api

    parameters = inspect.signature(Api.fittings_state).parameters
    assert list(parameters) == ["self"]


def test_fittings_state_is_stable_across_calls(tmp_path):
    """Nothing here is derived from mutable state yet, so two calls must
    agree -- a page that asks once (fittings.js's `asked` guard) and a
    harness or test that asks twice must see the same thing."""
    api = make_api(tmp_path)

    assert api.fittings_state() == api.fittings_state()
