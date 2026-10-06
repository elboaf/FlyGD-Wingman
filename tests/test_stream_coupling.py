"""The combat trigger (#320): chord spelling, episode latches, the send.

The controller is driven synchronously in most tests -- the injected
``spawn`` starts no thread and the tests call ``_process`` directly -- so
the latch and gate decisions are deterministic without sleeps. One test
uses the real worker thread, because "the send happens on the
controller's own worker thread, never the telemetry dispatcher" is an
acceptance criterion, not an implementation detail.
"""

import threading
import time

from wingman.alerts.streamcoupling import (
    ChordPlan,
    StreamCouplingController,
    StreamCouplingPorts,
    spell_chord,
)

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
VK_LWIN = 0x5B


class _NoThread:
    """A stand-in thread that never starts: sync tests drive _process
    themselves and close() becomes a no-op."""

    def start(self):
        pass

    def join(self, timeout=None):
        pass


class Harness:
    def __init__(self, coupling=None, spawn=None, **over):
        self.coupling = (
            dict(coupling) if coupling is not None else {"chord": "^!d", "quiet_s": 300}
        )
        self.mirror_running = True
        self.foreground = "eve.exe"
        self.sent = []
        self.pushes = []
        self.now = 1000.0
        kwargs = dict(
            coupling=lambda: self.coupling,
            mirror_running=lambda: self.mirror_running,
            foreground_process=lambda: self.foreground,
            char_vk=None,
            send=self._send,
            publish_state=lambda payload: self.pushes.append(
                ("onStreamCouplingState", payload)
            ),
            publish_fired=lambda payload: self.pushes.append(
                ("onStreamCouplingFired", payload)
            ),
        )
        kwargs.update(over)
        self.controller = StreamCouplingController(
            StreamCouplingPorts(**kwargs),
            clock=lambda: self.now,
            wall=lambda: 1759747260.0,
            spawn=spawn or (lambda **_kw: _NoThread()),
        )

    def _send(self, plan):
        self.sent.append((plan, threading.current_thread()))

    def observe(self, characters):
        self.controller._process(tuple(characters))

    def state(self):
        return self.controller.state_payload()


# ---- the spelling -------------------------------------------------------


def test_a_plain_chord_spells_modifiers_then_key():
    assert spell_chord("^!d") == ChordPlan((VK_CONTROL, VK_MENU), 0x44, False)


def test_modifier_order_is_press_order_not_notation_order():
    # "+^5" stores the same chord the capture would spell "^+5": the plan
    # presses Ctrl before Shift regardless of how the user typed it.
    assert spell_chord("+^5") == ChordPlan((VK_CONTROL, VK_SHIFT), 0x35, False)


def test_win_modifier_spells_to_lwin():
    assert spell_chord("#F5") == ChordPlan((VK_LWIN,), 0x74, False)


def test_position_tokens_resolve_through_the_gestures_table():
    assert spell_chord("^!Numpad3").vk == 0x63
    assert spell_chord("PgUp").vk == 0x21


def test_numpad_enter_is_the_extended_key():
    plan = spell_chord("^#NumpadEnter")
    assert plan == ChordPlan((VK_CONTROL, VK_LWIN), 0x0D, True)


def test_a_produced_character_resolves_through_the_layout():
    # The ADR 0002 direction: the stored chord holds what the layout
    # PRODUCED, so "d" on a Dvorak box means the physical key this
    # layout types "d" with (VK_H's position), not the US-layout guess.
    plan = spell_chord("^!d", char_vk=lambda char: (0x48, False))
    assert plan == ChordPlan((VK_CONTROL, VK_MENU), 0x48, False)


def test_a_layout_digit_unions_its_implied_shift():
    # On layouts where digits sit behind Shift (AZERTY's number row), a
    # stored "5" must replay with Shift or it types "è" -- the resolver's
    # shift flag unions into the modifier set.
    plan = spell_chord("^5", char_vk=lambda char: (0x35, True))
    assert plan == ChordPlan((VK_CONTROL, VK_SHIFT), 0x35, False)


def test_an_unresolvable_character_falls_back_to_the_table():
    # Without a resolver (Linux tests, a stripped build, a layout that
    # cannot place the character) ASCII letters still spell -- the
    # position table's answer is the same key on US-family layouts --
    # and anything neither can name refuses the whole plan.
    assert spell_chord("^!d", char_vk=None).vk == 0x44
    assert spell_chord("^!d", char_vk=lambda char: None).vk == 0x44
    assert spell_chord("^!@", char_vk=None) is None


def test_modifier_only_and_garbage_are_never_spellable():
    for text in ("", "^", "!", "nonsense", None, "^^"):
        assert spell_chord(text) is None


# ---- the guards ---------------------------------------------------------


def test_consent_refusal_no_chord_means_nothing_ever():
    h = Harness(coupling={"chord": "", "quiet_s": 300})
    h.observe(["Kuan Dai"])
    assert h.sent == []
    assert h.state()["state"] == "inert"


def test_the_first_gated_alert_fires_exactly_once():
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 5
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    assert h.state()["last_fired_character"] == "Kuan Dai"


def test_the_first_fire_disarms_all_characters():
    h = Harness()
    h.observe(["Kuan Dai"])
    h.now += 5
    h.observe(["xX_Sigma_Xx"])
    assert len(h.sent) == 1
    assert h.state()["state"] == "held"


def test_the_quiet_period_re_arms():
    h = Harness()
    h.observe(["Kuan Dai"])
    h.now += 300 + 1
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 2


def test_ongoing_combat_extends_the_hold():
    # The asymmetry argument: a fight's own alerts hold the process
    # disarmed, so fifteen minutes of combat produces one chord, never
    # the toggle-off.
    h = Harness()
    h.observe(["Kuan Dai"])
    for _ in range(18):
        h.now += 100
        h.observe(["xX_Sigma_Xx"])
        h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 300 + 1
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 2


def test_discord_foreground_refusal():
    h = Harness()
    h.foreground = "Discord.exe"
    h.observe(["Kuan Dai"])
    assert h.sent == []
    # The refusal does not consume the episode silently: the combat
    # alert still started the latch, and the row says held.
    assert h.state()["state"] == "held"


def test_an_unprovable_foreground_fails_closed():
    h = Harness()
    h.foreground = None
    h.observe(["Kuan Dai"])
    assert h.sent == []


def test_fire_anyway_with_no_eve_client_focused():
    h = Harness()
    h.foreground = "chrome.exe"
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1


def test_no_mirror_stands_by_instead_of_firing():
    # The spec's failure-modes line: the feature stays inert without a
    # mirror window to pin -- and a chord pressed with the mirror down
    # could toggle off a stream the user started by hand.
    h = Harness()
    h.mirror_running = False
    h.observe(["Kuan Dai"])
    assert h.sent == []
    assert h.state()["state"] == "standby"
    h.now += 60
    h.mirror_running = True
    h.observe(["Kuan Dai"])
    assert h.sent == []


def test_latches_are_maintained_even_while_inert():
    # Recording a keybind mid-fight must not fire into the fight that is
    # already running: the quiet period predates the consent.
    h = Harness(coupling={"chord": "", "quiet_s": 300})
    h.observe(["Kuan Dai"])
    h.now += 5
    h.coupling["chord"] = "^!d"
    h.observe(["Kuan Dai"])
    assert h.sent == []
    h.now += 300 + 1
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1


def test_the_quiet_period_is_read_live():
    h = Harness()
    h.observe(["Kuan Dai"])
    h.now += 61
    h.coupling["quiet_s"] = 60
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 2


def test_an_unspellable_chord_never_fires():
    h = Harness(coupling={"chord": "nonsense", "quiet_s": 300})
    h.observe(["Kuan Dai"])
    assert h.sent == []
    state = h.state()
    # The observation still latched the fight -- and chord_sendable is
    # what tells the user why nothing will ever fire on it.
    assert state["state"] == "held"
    assert state["chord_sendable"] is False


# ---- the row ------------------------------------------------------------


def test_the_state_row_carries_the_whole_shape():
    h = Harness()
    payload = h.state()
    assert payload == {
        "state": "armed",
        "chord_display": "Ctrl+Alt+D",
        "chord_sendable": True,
        "quiet_s": 300,
        "latched": [],
        "latched_remaining_s": 0,
        "last_fired_character": None,
        "last_fired_display": None,
    }


def test_the_held_row_names_the_latched_characters_and_time_left():
    h = Harness()
    h.observe(["Kuan Dai"])
    h.now += 5
    h.observe(["xX_Sigma_Xx"])
    payload = h.state()
    assert payload["state"] == "held"
    assert payload["latched"] == ["Kuan Dai", "xX_Sigma_Xx"]
    # The countdown is the LONGEST latch: Sigma's just started, so the
    # whole episode runs 300 more seconds before the process re-arms.
    assert payload["latched_remaining_s"] == 300


def test_the_row_says_who_fired_and_when():
    h = Harness()
    h.observe(["Kuan Dai"])
    payload = h.state()
    assert payload["last_fired_character"] == "Kuan Dai"
    assert payload["last_fired_display"]  # the page renders it verbatim


# ---- the thread discipline ---------------------------------------------


def test_the_send_runs_on_the_controller_worker_thread():
    h = Harness(spawn=threading.Thread)
    try:
        h.controller.observe_combat(["Kuan Dai"])
        deadline = time.monotonic() + 5
        while len(h.sent) == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(h.sent) == 1
        plan, sender = h.sent[0]
        # The dispatcher thread (here: the test's) never sends.
        assert sender is not threading.current_thread()
        assert sender.name == "stream-coupling"
        assert plan == ChordPlan((VK_CONTROL, VK_MENU), 0x44, False)
    finally:
        h.controller.close()


def test_observe_combat_is_total_against_junk():
    h = Harness()
    h.controller.observe_combat([None, 17, "", "Kuan Dai"])
    assert h.controller._queue.qsize() == 1


def test_close_is_idempotent_and_stops_the_worker():
    h = Harness(spawn=threading.Thread)
    thread = h.controller._thread
    h.controller.close()
    h.controller.close()  # the second close must be a no-op, not a join twice
    assert not thread.is_alive()
    h.controller.observe_combat(["Kuan Dai"])
    assert h.sent == []
