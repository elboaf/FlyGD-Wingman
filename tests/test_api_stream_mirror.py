"""Bridge slice of #317: the card's methods and the status push.

The card is a READ-then-push surface, exactly like the alerts card: the
page fetches `stream_mirror_state` on entering the Streaming section (a
push at launch would fire into a window that may not exist yet), and the
poll tick pushes `onMirrorStatus` so an out-of-band death is reflected
without the page asking. Bridge discipline: every push name is a literal
test_bridge_contract can see; None supervisor means "unavailable" payload,
never an exception off the bridge thread.
"""

from tests.test_api import make_api
from wingman import settings


class FakeSupervisor:
    def __init__(self, running=False, error=None, exe=None):
        self._running = running
        self.started = 0
        self.stopped = 0
        self.last_error = error
        # The ceremony's registration path (#321): the real supervisor
        # exposes the exe paths.mirror_exe() resolved at launch.
        self.exe_path = exe

    def start(self):
        self.started += 1
        self._running = True
        return True

    def stop(self, timeout=5.0):
        self.stopped += 1
        self._running = False

    def is_running(self):
        return self._running

    def status(self, enabled):
        from wingman.mirrorsupervisor import MirrorStatus

        if not enabled:
            return MirrorStatus(state="off")
        if self._running:
            return MirrorStatus(state="running")
        return MirrorStatus(state="stopped", last_error=self.last_error)


def api_with_mirror(tmp_path, supervisor, coupling=None):
    api = make_api(tmp_path)
    api._state.mirror_supervisor = supervisor
    with settings.update(api._state.settings) as document:
        preview = document.setdefault(
            "preview", settings.validated_preview({"enabled": True})
        )
        preview["enabled"] = True
        preview["alerts"]["stream_coupling"] = settings.validated_preview(
            {
                "enabled": True,
                "alerts": {"stream_coupling": coupling or {"mirror_on": True}},
            }
        )["alerts"]["stream_coupling"]
    return api


def test_state_read_reflects_a_running_mirror(tmp_path):
    api = api_with_mirror(
        tmp_path, FakeSupervisor(running=True, exe="C:\\x\\wingman-mirror.exe")
    )
    state = api.stream_mirror_state()
    assert state["available"] is True
    assert state["running"] is True
    assert state["state"] == "running"
    assert state["mirror_on"] is True
    # The card's registration path (#321): the supervisor's own resolution,
    # because that is the exe Wingman would actually supervise.
    assert state["exe_path"] == "C:\\x\\wingman-mirror.exe"


def test_state_read_reports_stopped_with_the_supervisor_error(tmp_path):
    api = api_with_mirror(
        tmp_path, FakeSupervisor(running=False, error="The stream mirror is missing.")
    )
    state = api.stream_mirror_state()
    assert state["running"] is False
    assert state["state"] == "stopped"
    assert "missing" in state["error"]


def test_state_read_without_a_supervisor_is_unavailable_not_fatal(tmp_path):
    """Off-Windows (or pre-construction): the card must render its
    unavailable row, not throw off the bridge thread. The consent fields
    ride the same payload either way (#319) -- settings state, not
    process state."""
    api = make_api(tmp_path)
    assert api._state.mirror_supervisor is None
    state = api.stream_mirror_state()
    assert state == {
        "available": False,
        "running": False,
        "state": "unavailable",
        "error": None,
        "mirror_on": False,
        "exe_path": None,
        "chord": "",
        "chord_display": "",
    }


def test_start_and_stop_round_trip_through_the_supervisor(tmp_path):
    sup = FakeSupervisor()
    api = api_with_mirror(tmp_path, sup)

    result = api.stream_mirror_start()
    assert result["ok"] is True and result["running"] is True
    assert sup.started == 1

    result = api.stream_mirror_stop()
    assert result["ok"] is True and result["running"] is False
    assert sup.stopped == 1


def test_start_flips_mirror_on_and_stop_flips_it_off(tmp_path):
    """The card button IS the mirror_on toggle: sticky on-demand means the
    setting persists what the user last asked, restored at next launch."""
    sup = FakeSupervisor()
    api = api_with_mirror(tmp_path, sup, coupling={"mirror_on": False})

    api.stream_mirror_start()
    assert (
        api._state.settings["preview"]["alerts"]["stream_coupling"]["mirror_on"] is True
    )

    api.stream_mirror_stop()
    assert (
        api._state.settings["preview"]["alerts"]["stream_coupling"]["mirror_on"]
        is False
    )


def test_start_failure_returns_ok_false_with_the_error(tmp_path):
    sup = FakeSupervisor()
    sup.last_error = "The stream mirror is missing from this installation."

    def fail_start():
        return False

    sup.start = fail_start
    api = api_with_mirror(tmp_path, sup)

    result = api.stream_mirror_start()
    assert result["ok"] is False
    assert "missing" in result["error"]


def test_start_without_a_supervisor_says_unavailable(tmp_path):
    api = make_api(tmp_path)
    result = api.stream_mirror_start()
    assert result["ok"] is False
    assert "unavailable" in result["error"]


def test_mirror_status_push_carries_the_state(tmp_path):
    sup = FakeSupervisor(running=True)
    api = api_with_mirror(tmp_path, sup)

    api._push_mirror_status()

    pushes = [
        (handler, payload)
        for handler, payload in _recorded_pushes(api)
        if handler == "onMirrorStatus"
    ]
    assert pushes, "no onMirrorStatus push recorded"
    payload = pushes[-1][1]
    assert payload["state"] == "running"
    assert payload["running"] is True


def _recorded_pushes(api):
    """The FakeWindow records evaluated JS; decode the mirror pushes."""
    from tests.test_api import pushes

    return pushes(api._window)


def test_ensure_mirror_if_enabled_restarts_only_when_mirror_on(tmp_path):
    calls = []

    class Recovering(FakeSupervisor):
        def ensure_running(self):
            calls.append(1)
            return True

    sup = Recovering(running=False)
    api = api_with_mirror(tmp_path, sup, coupling={"mirror_on": True})
    api.ensure_mirror_if_enabled()
    assert calls == [1]

    api = api_with_mirror(
        tmp_path, Recovering(running=False), coupling={"mirror_on": False}
    )
    api.ensure_mirror_if_enabled()
    assert calls == [1]  # unchanged: no ask, no restart


def test_ensure_mirror_if_enabled_is_safe_without_a_supervisor(tmp_path):
    api = make_api(tmp_path)
    api.ensure_mirror_if_enabled()
