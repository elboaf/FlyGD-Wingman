"""Arm, severity, expiry, acknowledgement, pulse phase.

Pure by construction: every function takes `now` rather than reading a
clock, which is what makes the whole state machine testable on Linux --
the same reason preview/geometry.py exists.
"""

import pytest

from obs_youtube_uploader.alerts import state

ARM = dict(duration_ms=1200, pulses=3, persist=False, target_is_selected=False)


def _arm(current, event, now, **over):
    kwargs = {**ARM, **over}
    return state.arm(current, event, "#ff4d4d", now, **kwargs)


def test_arming_from_nothing_returns_the_incoming_alert():
    a = _arm(None, "combat", 0.0)
    assert a.event == "combat" and a.expires == pytest.approx(1.2)


def test_persist_makes_the_alert_never_expire():
    a = _arm(None, "combat", 0.0, persist=True)
    assert a.expires is None
    assert state.is_active(a, 99999.0) is True


def test_an_alert_on_an_already_selected_client_is_not_persistent():
    """You are looking at that client, so there is nothing to acknowledge
    and a persistent ring would pulse until you tabbed away and back."""
    a = _arm(None, "combat", 0.0, persist=True, target_is_selected=True)
    assert a.expires is not None


def test_higher_severity_replaces_outright():
    combat = _arm(None, "combat", 0.0)
    scram = _arm(combat, "warp_scramble", 0.5)
    assert scram.event == "warp_scramble"


def test_lower_severity_extends_but_does_not_repaint():
    """Without this a decloak repaints a live scramble as the milder
    alert, which is the opposite of what severity is for."""
    scram = _arm(None, "warp_scramble", 0.0)
    after = _arm(scram, "decloak", 0.5)
    assert after.event == "warp_scramble"
    assert after.expires > scram.expires


def test_equal_severity_restarts_the_pulse():
    """The common case: a fight emits a combat line every server tick, and
    each one should restart the pulse rather than let it finish."""
    first = _arm(None, "combat", 0.0)
    second = _arm(first, "combat", 0.9)
    assert second.started == 0.9
    assert second.event == "combat"


def test_lower_severity_over_a_persistent_alert_changes_nothing():
    """With persistence on there is no expiry to extend, so the extend
    rule is inert. It is written down so that turning persistence OFF does
    not quietly change which colour is showing."""
    scram = _arm(None, "warp_scramble", 0.0, persist=True)
    after = _arm(scram, "decloak", 0.5, persist=True)
    assert after == scram


def test_clear_expired_drops_a_timed_alert_and_keeps_a_persistent_one():
    timed = _arm(None, "combat", 0.0)
    persistent = _arm(None, "combat", 0.0, persist=True)
    assert state.clear_expired(timed, 99.0) is None
    assert state.clear_expired(persistent, 99.0) == persistent


def test_acknowledge_clears_only_a_persistent_alert():
    """A timed alert is already going away; acknowledging it would make
    selecting a client cut short a ring that had just appeared."""
    timed = _arm(None, "combat", 0.0)
    persistent = _arm(None, "combat", 0.0, persist=True)
    assert state.acknowledge(timed) == timed
    assert state.acknowledge(persistent) is None


def test_progress_clamps_for_timed_and_free_runs_for_persistent():
    timed = _arm(None, "combat", 0.0)
    persistent = _arm(None, "combat", 0.0, persist=True)
    assert state.progress(timed, 99.0) == 1.0
    assert 0.0 <= state.progress(persistent, 99.0) < 1.0


def test_alpha_never_reaches_zero():
    """The ring pulses rather than blinking off. An alpha of 0 mid-pulse
    reads as the alert having ended."""
    alphas = [state.alpha_for(i / 50, 3) for i in range(51)]
    assert min(alphas) >= 90 and max(alphas) <= 255


def test_frame_index_is_in_range():
    a = _arm(None, "combat", 0.0, persist=True)
    for i in range(60):
        assert 0 <= state.frame_index(a, i * 0.08) < len(state.FRAME_ALPHAS)
