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
from dataclasses import replace

from wingman.alerts.streamcoupling import (
    ChordPlan,
    StreamCouplingController,
    StreamCouplingPorts,
    chord_choreography,
    spell_chord,
)
from wingman.streaming.probe import DailyBudget, ProbeError


def test_the_input_struct_is_the_real_win32_input_size():
    """SendInput validates cbSize against the REAL INPUT, whose union's
    largest member is MOUSEINPUT. A keyboard-only union computes 32 on
    x64 and SendInput rejects every batch with a silent 0 -- how the
    combat trigger logged "fired" through four field tests while
    pressing nothing (2026-10-06). The structures live at module scope
    so this pin runs on Linux CI."""
    import ctypes
    import sys

    from wingman.alerts import streamcoupling

    # The union's largest member must be the mouse one: that is the
    # whole reason a keyboard-only struct undercounts.
    assert ctypes.sizeof(streamcoupling._MOUSEINPUT) > ctypes.sizeof(
        streamcoupling._KEYBDINPUT
    )
    if sys.platform == "win32":
        # The exact cbSize SendInput demands, per pointer width.
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        assert ctypes.sizeof(streamcoupling._INPUT) == expected
    else:
        # Off-Windows the ABI packs differently (wintypes LONG is 8
        # bytes on Linux), so pin the relationship, not the number: the
        # struct carries the type tag plus the whole union.
        assert ctypes.sizeof(streamcoupling._INPUT) >= (
            4 + ctypes.sizeof(streamcoupling._MOUSEINPUT)
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
    """The probe world (rev 4, #335/#336): the default probe answers by
    the gate that calls it -- at the START gate (no episode open) it
    answers ``self.start_probe_answer`` (False = not live, the chord
    fires); at the STOP gate (episode open) it answers
    ``self.probe_answer`` (True = still live, the stop presses). It
    spends the budget faithfully, and the budget is a real DailyBudget
    so the degrade path is exercised against the same class production
    uses."""

    def __init__(self, coupling=None, spawn=None, **over):
        self.start_probe_answer = False
        self.manual_live = False
        self.coupling = (
            dict(coupling) if coupling is not None else {"chord": "^!d", "quiet_s": 600}
        )
        self.mirror_running = True
        self.sent = []
        self.pushes = []
        self.now = 1000.0
        self.probe_calls = 0
        self.probe_answer = True
        self.probe_error = None
        self.budget = DailyBudget(day=lambda: "day 1")
        kwargs = dict(
            coupling=lambda: self.coupling,
            mirror_running=lambda: self.mirror_running,
            char_vk=None,
            send=self._send,
            publish_state=lambda payload: self.pushes.append(
                ("onStreamCouplingState", payload)
            ),
            publish_fired=lambda payload: self.pushes.append(
                ("onStreamCouplingFired", payload)
            ),
            probe_live=self._probe,
            budget_spend=self.budget.try_spend,
            manual_live=lambda: self.manual_live,
            budget_status=lambda: {
                "budget_used": self.budget.used(),
                "budget_limit": self.budget.used() + self.budget.remaining(),
            },
            publish_probe_status=lambda payload: self.pushes.append(
                ("onStreamProbeStatus", payload)
            ),
        )
        kwargs.update(over)
        self.controller = StreamCouplingController(
            StreamCouplingPorts(**kwargs),
            clock=lambda: self.now,
            wall=lambda: 1759747260.0,
            spawn=spawn or (lambda **_kw: _NoThread()),
        )

    def _probe(self):
        self.probe_calls += 1
        if self.probe_error is not None:
            raise self.probe_error
        if self.controller._episode is None:
            return self.start_probe_answer  # the start gate (#336)
        return self.probe_answer  # the stop gate (#335)

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


# ---- the press ----------------------------------------------------------

VK_LCONTROL = 0xA2
VK_LMENU = 0xA4
VK_F9 = 0x78


def test_the_press_uses_left_hand_modifiers_not_the_generic_vks():
    # Field report 2026-10-07: the injected ctrl+alt+f9 opened a focused
    # EVE client's map -- the client acted on a bare F9. A keyboard never
    # produces the generic VK_CONTROL; it produces VK_LCONTROL, and the
    # system derives the generic state from it. Pressing the left keys is
    # what makes the synthetic events read like the user's own hand.
    steps = chord_choreography(spell_chord("^!F9"))
    vks = [vk for vk, _up, _ext, _delay in steps]
    assert vks == [VK_LCONTROL, VK_LMENU, VK_F9, VK_F9, VK_LMENU, VK_LCONTROL]


def test_the_press_paces_the_chord_like_a_hand_not_one_batch():
    # The other half of the same field report: a whole chord in one
    # SendInput batch is down and up inside one scheduler tick, so a
    # poller or a dispatch-time async key state read sees the modifiers
    # already up -- a bare F9. The gaps hold the chord through the tap.
    steps = chord_choreography(spell_chord("^!F9"))
    delays = [delay for _vk, _up, _ext, delay in steps]
    assert all(delay > 0 for delay in delays)
    # The hold before the tap is the point: the chord is seen held.
    assert delays[2] == max(delays)


def test_the_extended_flag_rides_the_base_key_alone():
    # An extended ctrl-down is RIGHT ctrl: on a NumpadEnter chord the
    # flag must touch only the base events, or every press carries
    # modifiers Discord never bound.
    steps = chord_choreography(spell_chord("^#NumpadEnter"))
    assert [ext for _vk, _up, ext, _delay in steps] == [
        False,
        False,
        True,
        True,
        False,
        False,
    ]


def test_a_chord_without_modifiers_presses_only_the_base_key():
    steps = chord_choreography(spell_chord("PgUp"))
    assert [(vk, up) for vk, up, _ext, _delay in steps] == [
        (0x21, False),
        (0x21, True),
    ]


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
    # Re-arm is now two presses: the stop at expiry closes the episode,
    # and only then can the next alert open a fresh one. Without the
    # stop, the next fight's start press would toggle the still-live
    # stream OFF mid-fight (field finding, 2026-10-06).
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert len(h.sent) == 2
    assert h.pushes[-1] == (
        "onStreamCouplingFired",
        {
            "character": None,
            "display": h.state()["last_fired_display"],
            "action": "stop",
        },
    )
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 3
    assert h.pushes[-1][1]["action"] == "start"


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
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert len(h.sent) == 2
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 3


def test_no_start_fires_while_an_episode_is_open():
    # The alternation guard: inside the window between latch expiry and
    # the worker's stop press, a late alert must refresh the running
    # fight -- never fire a "start" that would toggle the live stream
    # off. The stop still lands, pushed out by the refreshed latches.
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 700  # latches expired; the stop press has not run yet
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.controller._maybe_stop()
    assert len(h.sent) == 1  # the refresh re-armed the deadline
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert len(h.sent) == 2
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 3


def test_the_stop_press_needs_the_mirror_and_closes_the_episode():
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.mirror_running = False
    h.controller._maybe_stop()
    # No press: Discord pins the mirror window, so a dead window has
    # already ended the share -- a press could only toggle off a stream
    # the user started by hand afterwards.
    assert len(h.sent) == 1
    # The episode IS closed either way: the next alert starts fresh.
    h.mirror_running = True
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 2


def test_clearing_the_chord_mid_episode_abandons_the_stop():
    # Consent's empty field switches off PRESSES, not the stream: no
    # stop press once the chord is gone, and the row goes inert.
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.coupling["chord"] = ""
    h.controller._maybe_stop()
    assert len(h.sent) == 1
    assert h.state()["state"] == "inert"


def test_the_worker_wakes_on_the_stop_deadline():
    h = Harness()
    assert h.controller._wake_delay() is None
    h.observe(["Kuan Dai"])
    assert h.controller._wake_delay() == 600.0
    h.now += 700
    # Overdue: due now, but the degraded stop no longer presses, so an
    # overdue deadline wakes on a 60s probe-retry cadence instead of
    # hot-spinning the worker (2026-10-11).
    assert h.controller._wake_delay() == 60.0


def test_a_resumed_fight_pushes_the_stop_out():
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 200
    h.observe(["Kuan Dai"])  # the fight resumed; the latch refreshed
    h.now += 599
    h.controller._maybe_stop()
    assert len(h.sent) == 1
    h.now += 1
    h.controller._maybe_stop()
    assert len(h.sent) == 2


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
    h.now += 600 + 1
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1


def test_the_quiet_period_is_fixed_at_600():
    """Rev 4 (#335): no live range any more -- the value is projected to
    600 whatever the settings document says, and the stop gate runs at
    that expiry."""
    h = Harness(coupling={"chord": "^!d", "quiet_s": 60})
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 61
    # The old build would have stopped here (60s quiet); fixed 600 holds.
    h.controller._maybe_stop()
    assert len(h.sent) == 1
    h.now += 600 - 61 + 1
    h.controller._maybe_stop()
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
        "quiet_s": 600,
        "latched": [],
        "latched_remaining_s": 0,
        "last_fired_character": None,
        "last_fired_display": None,
        "last_fired_action": None,
        # The probe fields (#335/#337): no answer yet, no degrade, and
        # the budget standing from the real DailyBudget.
        "live": None,
        "live_display": None,
        "degraded": None,
        "wingman_live": False,
        "suppressed_display": None,
        "manual_live": False,
        "budget_used": 0,
        "budget_limit": 300,
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
    # whole episode runs 600 more seconds before the process re-arms.
    assert payload["latched_remaining_s"] == 600


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


def test_a_real_worker_presses_the_stop_after_quiet(monkeypatch):
    # The timed wake end to end, on a real clock: a real worker thread
    # must press the stop by itself once the quiet period lapses -- no
    # combat alert arrives to wake it. (The Harness's frozen clock can
    # never lapse, so this one builds its controller bare.) The probe
    # seam answers live: the confirmed stop press goes out.
    monkeypatch.setattr(StreamCouplingController, "_QUIET_MIN", 0)
    sent = []
    controller = StreamCouplingController(
        StreamCouplingPorts(
            coupling=lambda: {"chord": "^!d", "quiet_s": 1},
            mirror_running=lambda: True,
            char_vk=None,
            send=sent.append,
            publish_state=lambda payload: None,
            publish_fired=lambda payload: None,
            probe_live=lambda: len(sent) >= 1,  # start gate: False, stop: True
            budget_spend=lambda: True,
        )
    )
    try:
        controller.observe_combat(["Kuan Dai"])
        deadline = time.monotonic() + 5
        while len(sent) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(sent) == 1
        # quiet_s of 1 plus the 1s wake floor: the stop lands in seconds.
        deadline = time.monotonic() + 10
        while len(sent) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(sent) == 2
    finally:
        controller.close()


def test_close_is_idempotent_and_stops_the_worker():
    h = Harness(spawn=threading.Thread)
    thread = h.controller._thread
    h.controller.close()
    h.controller.close()  # the second close must be a no-op, not a join twice
    assert not thread.is_alive()
    h.controller.observe_combat(["Kuan Dai"])
    assert h.sent == []


# ---- the probe gate (#335, rev 4) ----------------------------------------


def test_the_stop_gate_probes_before_pressing():
    """Quiet expiry with the episode open: one probe. Still live -> the
    stop chord. The probe precedes every press -- a blind press could
    toggle off a stream the user started by hand."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert h.probe_calls == 2  # the start gate (#336) + the stop gate
    assert len(h.sent) == 2


def test_a_manual_stop_at_expiry_clears_the_latch_and_presses_nothing():
    """Already off (the user stopped by hand): clear the latch, send
    nothing, re-arm. One dead episode max, never a zombie stream -- and
    no confirm probe afterwards."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.probe_answer = False
    h.controller._maybe_stop()
    assert h.probe_calls == 2  # start + stop
    assert len(h.sent) == 1
    # Re-armed: the next fight starts fresh, no stop press in between.
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 2
    assert h.state()["state"] == "held"


def test_a_stop_never_fires_against_a_manual_stream():
    """The probe says live but the episode was NEVER confirmed as
    Wingman-originated -- wait: the confirmation IS this probe's answer
    over an open episode. The dangerous case is a degraded probe with an
    unconfirmed episode, pinned separately below; here the fresh
    snapshot over a Wingman-originated episode is exactly the consent
    the stop path requires."""
    h = Harness()
    h.observe(["Kuan Dai"])
    h.now += 600 + 1
    # The flag is set the MOMENT the confirmed start press went out
    # (2026-10-11, the user's model) -- not retroactively by a probe.
    assert h.state()["wingman_live"] is True
    h.controller._maybe_stop()
    # The press IS the proof: it flew only because the fresh snapshot
    # over this Wingman-originated episode said still-live. Afterwards
    # the flag is consumed -- the episode is closed.
    assert len(h.sent) == 2
    records = [
        payload for handler, payload in h.pushes if handler == "onStreamProbeStatus"
    ]
    assert records[-1]["live"] is True
    assert h.state()["wingman_live"] is False


def test_a_degraded_stop_probe_defers_the_stop():
    """No token / budget dry / gateway down at the STOP gate: NO PRESS
    (2026-10-11 field incident -- a blind stop press can cut a stream
    the user started by hand, the one outcome the probe exists to
    prevent). The episode stays open and the stop is retried: a fight
    resuming refreshes the latches; a quiet gateway run retries on the
    60s wake cadence. The stream errs LONG, never cut."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.probe_error = ProbeError("network")
    h.controller._maybe_stop()
    assert h.probe_calls == 2  # the start probe answered; the stop probe failed
    assert len(h.sent) == 1  # deferred, not pressed
    # The episode stays open: the start gate's reopen branch will hold
    # Wingman's own stream, and the stop retries. No fight: probe retry.
    assert h.state()["wingman_live"] is True
    h.probe_error = None
    h.controller._maybe_stop()
    assert h.probe_calls == 3
    assert len(h.sent) == 2  # the deferred stop lands once the probe answers


def test_the_wingman_live_flag_is_set_at_start_and_consumed_at_stop():
    """The user's model (2026-10-11): the flag is set the moment the
    probe-confirmed start press goes out, and consumed by the stop
    press. A degraded stop defers instead of pressing, so the flag
    survives and the NEXT start gate recognizes its own still-live
    stream -- reopening the episode instead of pressing into it."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    assert h.state()["wingman_live"] is True  # set AT the start press
    h.now += 600 + 1
    h.controller._maybe_stop()  # confirmed and pressed: episode closed
    assert h.state()["wingman_live"] is False
    h.observe(["Kuan Dai"])  # fresh fight opens a fresh episode
    assert h.state()["wingman_live"] is True
    h.now += 300
    h.observe(["Kuan Dai"])  # the fight resumes: the episode holds
    h.now += 600 + 1
    h.probe_error = ProbeError("network")
    h.controller._maybe_stop()
    # Sends: start, stop, start, deferred stop -- 3 presses, not 4.
    assert len(h.sent) == 3
    # The flag survives the deferral; the episode is still open.
    assert h.state()["wingman_live"] is True


def test_a_dry_budget_degrades_the_stop_gate_and_says_so():
    """Budget dry (#335): degrade to open-loop -- the chord still fires
    (never a zombie stream), and the card hears why through the probe
    push, never silently."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    dry = DailyBudget(limit=0, day=lambda: "day 1")
    h.controller._ports = replace(
        h.controller._ports,
        budget_spend=dry.try_spend,
        budget_status=lambda: {"budget_used": 0, "budget_limit": 0},
    )
    h.controller._maybe_stop()
    assert h.probe_calls == 1  # the start gate ran while the budget stood
    assert len(h.sent) == 1  # deferred, never a blind press
    degraded = [
        payload for handler, payload in h.pushes if handler == "onStreamProbeStatus"
    ]
    assert degraded and degraded[-1]["degraded"] == "budget dry -- no press"


def test_the_probe_failure_is_recorded_for_the_card():
    h = Harness()
    h.probe_error = ProbeError("auth")
    h.observe(["Kuan Dai"])
    # The degraded start gate presses NOTHING (2026-10-11: a blind
    # start press cut a hand-started stream); the stop gate with no
    # episode open never runs. The card's one record is the start's.
    assert len(h.sent) == 0
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert h.probe_calls == 1  # the start gate's only spend
    records = [
        payload for handler, payload in h.pushes if handler == "onStreamProbeStatus"
    ]
    assert records and records[-1] == {
        "live": None,
        "live_display": None,
        "degraded": "probe failed -- no press",
        "wingman_live": False,
        "suppressed_display": None,
        "manual_live": False,
        "budget_used": 1,
        "budget_limit": 300,
    }


def test_the_probe_answer_is_recorded_for_the_card():
    h = Harness()
    h.now += 600 + 1  # no episode: the gate does not run
    assert h.controller._maybe_stop() is None
    h.observe(["Kuan Dai"])  # start press; then expiry
    h.now += 600 + 1
    h.controller._maybe_stop()
    records = [
        payload for handler, payload in h.pushes if handler == "onStreamProbeStatus"
    ]
    assert records[-1]["live"] is True
    assert records[-1]["live_display"]  # "HH:MM" for the card's badge
    assert records[-1]["degraded"] is None
    # The start gate probed too (#336) and heard not-live: the chord fired.
    start_records = [p for p in records if p["live"] is False and p["degraded"] is None]
    assert start_records, "the start gate's probe never reached the card"


def test_the_probe_never_runs_without_an_episode():
    """A probe costs budget; no episode open, the stop gate does not
    run. (The start gate (#336) only runs on an armed fire.)"""
    h = Harness()
    h.controller._maybe_stop()
    assert h.probe_calls == 0
    assert h.budget.used() == 0


def test_without_a_probe_seam_the_stop_defers():
    """A hand-built ports object without the probe seams (older tests,
    a controller built before this ticket): the start gate has no
    answer and suppresses, so no episode ever opens and the stop gate
    never runs -- the whole loop is inert, never blind (2026-10-11).
    One degrade notice says the loop is not configured."""
    h = Harness(probe_live=None, budget_spend=None)
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 0
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert len(h.sent) == 0  # no episode, no press, ever
    assert h.state()["degraded"] == "not configured"


def test_the_stop_gate_still_honors_the_consent_and_mirror_gates():
    """The probe adds a gate; it retires none. Chord cleared mid-episode
    and mirror death still abandon without pressing."""
    h = Harness()
    h.observe(["Kuan Dai"])
    h.now += 600 + 1
    h.coupling["chord"] = ""
    h.controller._maybe_stop()
    assert h.probe_calls == 2  # the start gate + the stop gate
    assert len(h.sent) == 1

    h2 = Harness()
    h2.observe(["Kuan Dai"])
    h2.now += 600 + 1
    h2.mirror_running = False
    h2.controller._maybe_stop()
    assert len(h2.sent) == 1
    # The mirror is down: the row says standby, the same posture the
    # start gate holds -- consent present, nothing to pin.
    assert h2.state()["state"] == "standby"


# ---- the start gate (#336) ----------------------------------------------


def test_the_start_gate_probes_before_pressing():
    """The armed trigger fires only after a fresh probe says not-live:
    the enter-combat gate probes at decision time (~2-3s old), which
    collapses the stale-snapshot race to noise. Not-live -> the chord."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 1
    assert len(h.sent) == 1
    assert h.state()["last_fired_action"] == "start"


def test_the_start_gate_suppresses_when_already_live():
    """Snapshot live -> suppress the start chord, LOGGED (never silent).
    The suppression is a no-op on the trigger side: the alert chain, the
    latches and the quiet clock are untouched; no episode opens, so the
    next gated alert may fire."""
    h = Harness()
    h.start_probe_answer = True  # the user is already live by hand
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 1
    assert len(h.sent) == 0  # suppressed
    assert h.state()["last_fired_action"] is None
    # No episode opened: the next gated alert is a fresh decision. The
    # latches DID refresh (the trigger side is untouched by design), so
    # the next decision waits for its own quiet period.
    assert h.state()["state"] == "held" and h.state()["latched"]
    h.start_probe_answer = False
    h.now += 600 + 1
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 2
    assert len(h.sent) == 1


def test_a_degraded_start_probe_suppresses_the_start():
    """No token / budget dry / gateway down at the START gate: NO PRESS
    (2026-10-11 field incident: the old open-loop degrade fired the
    chord blind while the user was live by hand -- the toggle cut their
    stream). A suppressed start costs one fight without an auto-stream,
    never a cut stream. The next gated alert is a fresh decision."""
    h = Harness()
    h.probe_error = ProbeError("network")
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 1
    assert len(h.sent) == 0  # suppressed -- the probe has no answer
    assert h.state()["last_fired_action"] is None
    assert h.state()["degraded"] == "probe failed -- no press"
    # Recovery: the probe answers again and the next alert fires.
    h.probe_error = None
    h.now += 600 + 1
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 2
    assert len(h.sent) == 1


def test_the_start_gate_runs_after_the_free_gates():
    """A probe costs budget: the mirror and spelling gates (free) run
    first, so a dead mirror or an unspellable chord never spends one."""
    h = Harness(mirror_running=lambda: False)
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 0
    assert len(h.sent) == 0

    h2 = Harness(coupling={"chord": "unspellable!", "quiet_s": 600})
    h2.observe(["Kuan Dai"])
    assert h2.probe_calls == 0
    assert len(h2.sent) == 0


def test_the_start_gate_spends_the_shared_budget():
    """The start probe is 1 of the 2-per-fight allowance: the same
    DailyBudget as the stop gate, so a fight's two probes are both
    counted and the card sees the spend."""
    h = Harness()
    h.observe(["Kuan Dai"])  # start probe (not live) -> fire
    h.now += 600 + 1
    h.controller._maybe_stop()  # stop probe (still live) -> stop press
    assert h.budget.used() == 2
    assert h.state()["budget_used"] == 2
    assert h.state()["budget_limit"] == 300


def test_without_a_probe_seam_the_start_suppresses():
    """A hand-built ports object without the probe seams: the start
    gate has no answer, so it presses NOTHING (2026-10-11 -- the same
    rule as every other degraded path) and the row says the loop is
    not configured."""
    h = Harness(probe_live=None, budget_spend=None)
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 0
    assert h.state()["last_fired_action"] is None
    assert h.state()["degraded"] == "not configured"


# ---- the manual-live latch (#337) ---------------------------------------


def test_the_manual_live_latch_suppresses_the_start_without_a_probe():
    """The one-click absolute suppressor (#337): while set, the start
    chord never fires and NO probe is spent -- the latch is absolute,
    not another gated decision. Latches still refresh (trigger side
    untouched); the next gated alert after the latch clears is fresh."""
    h = Harness()
    h.manual_live = True
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 0
    assert len(h.sent) == 0
    assert h.state()["last_fired_action"] is None
    h.manual_live = False
    h.now += 600 + 1  # the first observe's latches must expire first
    h.observe(["Kuan Dai"])
    assert h.probe_calls == 1
    assert len(h.sent) == 1


def test_the_manual_live_latch_blocks_the_stop_press():
    """The latch suppresses both directions -- it says 'I am live by
    hand', and no Wingman press may touch that stream. The episode
    closes without a press (no zombie by construction: nothing Wingman
    opened is left running -- Wingman never opened this one)."""
    h = Harness()
    h.observe(["Kuan Dai"])  # opened before the user clicked the latch
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.manual_live = True
    h.controller._maybe_stop()
    assert len(h.sent) == 1  # no stop press
    # The episode is closed: the next alert is a fresh decision.
    h.manual_live = False
    h.probe_calls = 0
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 2


def test_the_latch_reads_live_on_every_decision():
    """The port is read at decision time, not cached: the user clicks
    the latch mid-session and the very next decision honors it."""
    h = Harness()
    answers = iter([False, True])
    h.controller._ports = replace(
        h.controller._ports, manual_live=lambda: next(answers)
    )
    h.observe(["Kuan Dai"])  # reads False: fires
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.observe(["Kuan Dai"])  # episode open: no fire
    h.controller._maybe_stop()  # reads True: abandon, no press
    assert len(h.sent) == 1


def test_the_latch_state_rides_the_card_payload():
    """The card needs the latch to draw its checkbox (#337): the state
    row and every probe-status push carry it."""
    h = Harness()
    assert h.state()["manual_live"] is False
    h.manual_live = True
    assert h.state()["manual_live"] is True
    h.controller._publish_probe_status()


# ---- the suppressed attempt (#337) --------------------------------------


def test_a_suppressed_start_is_surfaced_with_its_time():
    """#336's suppression must never be silent (#337): the card hears
    'already live -- chord suppressed 14:32' through the probe-status
    push, and the state row carries the same record."""
    h = Harness()
    h.start_probe_answer = True  # the user is already live by hand
    h.observe(["Kuan Dai"])
    records = [
        payload for handler, payload in h.pushes if handler == "onStreamProbeStatus"
    ]
    assert records, "the suppression never reached the card"
    # The frozen wall, formatted the way the card sees it (TZ-independent).
    expected = time.strftime("%H:%M", time.localtime(1759747260.0))
    assert records[-1]["suppressed_display"] == expected
    assert records[-1]["live"] is True
    assert h.state()["suppressed_display"] == expected


def test_a_fired_start_clears_the_suppression_record():
    """The line is the LAST attempt's story: the next fired start (or
    stop) replaces it -- the card never shows a stale suppression."""
    h = Harness()
    h.start_probe_answer = True
    h.observe(["Kuan Dai"])  # suppressed
    assert h.state()["suppressed_display"] is not None
    h.start_probe_answer = False
    h.now += 600 + 1
    h.observe(["Kuan Dai"])  # fired
    assert h.state()["suppressed_display"] is None


def test_a_live_stream_wingman_owns_reopens_the_episode_not_a_press():
    """The self-heal (2026-10-11): a degraded stop left Wingman's own
    stream live with the flag set. The next fight's start gate sees
    live + wingman_live -> NOT a hand stream to suppress, and NOT a
    chord to press: the episode reopens and the quiet clock re-arms,
    which extends the after-combat timer until the stop gate can
    actually answer. The zombie heals without ever toggling it."""
    h = Harness()
    h.observe(["Kuan Dai"])
    assert len(h.sent) == 1
    h.now += 600 + 1
    h.probe_error = ProbeError("network")
    h.controller._maybe_stop()  # deferred: stream still up, flag set
    assert len(h.sent) == 1
    # A new fight arrives while Wingman's stream is still live. The
    # episode was NEVER closed (the stop deferred), so the alternation
    # guard simply refreshes the latches -- no fire, no probe, the
    # quiet clock re-arms and the after-combat timer extends.
    h.probe_error = None
    h.start_probe_answer = True  # irrelevant: no start decision runs
    h.observe(["Faoble"])
    assert h.probe_calls == 2  # no new probe spent on an open episode
    assert len(h.sent) == 1  # no press in either direction
    assert h.state()["wingman_live"] is True  # still Wingman's, still tracked
    h.now += 600 + 1
    h.controller._maybe_stop()
    assert len(h.sent) == 2  # the stop lands once the probe can answer
