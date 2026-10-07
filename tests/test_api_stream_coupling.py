"""Bridge slice of #320: the armed row's read, the quiet-period write,
and the two semantic pushes.

The controller owns the decisions; this file owns the boundary. The push
literals live here (ui/api.py), where test_bridge_contract's sweep can
see them; the page owns their rendering. None controller (a hand-built
Api) means the inert payload off the bridge thread, never an exception.
"""

from tests.test_api import make_api, pushes
from wingman import settings


def test_state_read_without_a_controller_is_inert_not_fatal(tmp_path):
    api = make_api(tmp_path)
    assert api._stream_coupling is None
    assert api.stream_coupling_state() == {
        "state": "inert",
        "chord_display": "",
        "chord_sendable": False,
        "quiet_s": 300,
        "latched": [],
        "latched_remaining_s": 0,
        "last_fired_character": None,
        "last_fired_display": None,
    }


class FakeCoupling:
    def __init__(self, payload):
        self._payload = payload

    def state_payload(self):
        return self._payload


ARMED = {
    "state": "armed",
    "chord_display": "Ctrl+Alt+D",
    "chord_sendable": True,
    "quiet_s": 300,
    "latched": [],
    "latched_remaining_s": 0,
    "last_fired_character": None,
    "last_fired_display": None,
}


def test_state_read_passes_the_controller_payload_through(tmp_path):
    api = make_api(tmp_path)
    api._stream_coupling = FakeCoupling(ARMED)
    assert api.stream_coupling_state() == ARMED


def test_state_push_is_deduped_against_the_last_payload(tmp_path):
    """The worker publishes on every combat observation and the tick
    publishes every poll; an unchanged row must not cross the bridge
    again. The countdown during an episode changes per second and stays
    honest exactly because the dedup compares payloads, not routes."""
    api = make_api(tmp_path)
    api._push_stream_coupling_state(ARMED)
    api._push_stream_coupling_state(ARMED)  # same row: no second push
    held = dict(ARMED, state="held", latched=["Kuan Dai"], latched_remaining_s=295)
    api._push_stream_coupling_state(held)
    names = [handler for handler, _ in pushes(api._window)]
    assert names.count("onStreamCouplingState") == 2


def test_fired_push_carries_the_moment(tmp_path):
    api = make_api(tmp_path)
    api._publish_stream_coupling_fired({"character": "Kuan Dai", "display": "12:41"})
    fired = [
        payload
        for handler, payload in pushes(api._window)
        if handler == "onStreamCouplingFired"
    ]
    assert fired == [{"character": "Kuan Dai", "display": "12:41"}]


def test_tick_pushes_the_re_arm_without_a_double(tmp_path):
    api = make_api(tmp_path)
    api._stream_coupling = FakeCoupling(ARMED)
    api._push_stream_coupling_tick()
    api._push_stream_coupling_tick()  # unchanged row: no push
    names = [handler for handler, _ in pushes(api._window)]
    assert names.count("onStreamCouplingState") == 1


def test_tick_is_safe_without_a_controller(tmp_path):
    api = make_api(tmp_path)
    api._push_stream_coupling_tick()


# ---- the quiet-period write --------------------------------------------


def test_quiet_set_persists_a_numeric_string(tmp_path):
    api = make_api(tmp_path)
    result = api.stream_quiet_set("120")
    assert result == {
        "applied": True,
        "persisted": True,
        "error": None,
        "quiet_s": 120,
    }
    assert api._state.settings["preview"]["alerts"]["stream_coupling"]["quiet_s"] == 120


def test_quiet_set_accepts_an_int_and_clamps_into_the_range(tmp_path):
    api = make_api(tmp_path)
    assert api.stream_quiet_set(5000)["quiet_s"] == 900
    assert api.stream_quiet_set(5)["quiet_s"] == 60
    # The clamped value is what the field shows next -- visible, not silent.
    assert api._state.settings["preview"]["alerts"]["stream_coupling"]["quiet_s"] == 60


def test_quiet_set_refuses_non_numbers_without_persisting(tmp_path):
    api = make_api(tmp_path)
    for junk in ("abc", "", None, 17.5, True):
        result = api.stream_quiet_set(junk)
        assert result["applied"] is False
        assert "60 and 900" in result["error"]
    # Nothing was written, so the normalized document keeps the default.
    coupling = settings.validated_preview(api._state.settings.get("preview", {}))[
        "alerts"
    ]["stream_coupling"]
    assert coupling["quiet_s"] == 300


def test_quiet_set_refreshes_the_row_after_the_write(tmp_path):
    api = make_api(tmp_path)
    api._stream_coupling = FakeCoupling(ARMED)
    api.stream_quiet_set("120")
    names = [handler for handler, _ in pushes(api._window)]
    assert "onStreamCouplingState" in names


# ---- the wiring (lexical, the house's way for __main__) -----------------


def test_main_wires_the_trigger_into_the_policy_funnel():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "wingman" / "__main__.py"
    ).read_text(encoding="utf-8")
    assert "build_stream_coupling_controller(" in source
    # The policy gets the trigger; the Api gets the controller; the
    # worker closes on every exit path.
    assert "stream_coupling=stream_coupling" in source
    assert "stream_coupling.observe_combat" in source
    assert '_teardown_step("stream coupling", stream_coupling.close)' in source
    assert "api._push_stream_coupling_tick()" in source


def test_the_coupling_reads_the_committed_projection_not_the_raw_document():
    """A worker decision mid-settings-update must never see a half-swapped
    section: build_stream_coupling_controller binds the committed reader,
    whose .get hands back detached copies under the save lock."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "wingman" / "__main__.py"
    ).read_text(encoding="utf-8")
    body = source.split("def build_stream_coupling_controller(", 1)[1]
    body = body.split("\ndef ", 1)[0]
    assert "committed_preview(state.settings)" in body
    assert "state.settings.get" not in body
