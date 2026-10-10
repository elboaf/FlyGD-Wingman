"""Focused page runtime for the Streaming card (streaming_page_runtime.js).

Exists because the #321 test build found the mirror toggle DEAD: the
button rendered and re-labelled but had no click handler attached, and no
guard could see it -- test_bridge_contract asserts sends exist on Api, not
that anything sends them; js_smoke executes only top level, never handler
bodies. The runtime executes the real production module against DOM and
bridge doubles and clicks the button. It needs node; without it these
skip, like test_js_smoke.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

HERE = pathlib.Path(__file__).parent

AVAILABLE_RUNNING = {
    "available": True,
    "running": True,
    "state": "running",
    "error": None,
    "mirror_on": True,
    "exe_path": r"C:\Program Files\FlyGD Wingman"
    r"\_internal\bin\wingman-mirror.exe",
    "chord": "^!d",
    "chord_display": "Ctrl+Alt+D",
}
AVAILABLE_STOPPED = dict(AVAILABLE_RUNNING, running=False, state="off", mirror_on=False)
UNAVAILABLE = {
    "available": False,
    "running": False,
    "state": "unavailable",
    "error": None,
    "mirror_on": False,
    "exe_path": None,
    "chord": "",
    "chord_display": "",
}


def _run_scenario(body: str, **payloads) -> None:
    """Run one scenario against the real streaming.js module. Payload
    doubles are injected as JSON vars -- the scenario strings stay plain
    JS, and f-strings would fight the JS braces."""
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    prelude = "".join(
        f"var {name} = {json.dumps(value)};\n" for name, value in payloads.items()
    )
    result = subprocess.run(
        ["node", str(HERE / "streaming_page_runtime.js")],
        input=prelude + body,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mirror_toggle_clicks_start_then_rereads_the_state():
    """THE regression: the toggle must actually send. Start from stopped,
    click, and the button re-renders from the re-read -- never from a
    state the click invented."""
    _run_scenario(
        """
      setMirror(AVAILABLE_STOPPED);
      setCoupling({state: 'standby', latched: [], quiet_s: 300, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      assert.equal(el('mirror-state').textContent, 'Off');
      assert.equal(el('mirror-toggle').textContent, 'Start mirror');
      calls.length = 0;
      setReply('stream_mirror_start', {ok: true, running: true, error: null});
      setMirror(AVAILABLE_RUNNING);
      el('mirror-toggle').fire('click');
      await tick();
      assert.deepEqual(calls[0], ['stream_mirror_start'], calls);
      assert.deepEqual(calls[1], ['stream_mirror_state'], calls);
      assert.equal(calls.length, 2, calls);
      assert.equal(el('mirror-state').textContent, 'Running');
      assert.equal(el('mirror-toggle').textContent, 'Stop mirror');
    """,
        AVAILABLE_STOPPED=AVAILABLE_STOPPED,
        AVAILABLE_RUNNING=AVAILABLE_RUNNING,
    )


def test_mirror_toggle_clicks_stop_when_running():
    _run_scenario(
        """
      setMirror(AVAILABLE_RUNNING);
      setCoupling({state: 'armed', latched: [], quiet_s: 300, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      calls.length = 0;
      setReply('stream_mirror_stop', {ok: true, running: false, error: null});
      setMirror(AVAILABLE_STOPPED);
      el('mirror-toggle').fire('click');
      await tick();
      assert.deepEqual(calls[0], ['stream_mirror_stop'], calls);
      assert.deepEqual(calls[1], ['stream_mirror_state'], calls);
      assert.equal(el('mirror-state').textContent, 'Off');
      assert.equal(el('mirror-toggle').textContent, 'Start mirror');
    """,
        AVAILABLE_RUNNING=AVAILABLE_RUNNING,
        AVAILABLE_STOPPED=AVAILABLE_STOPPED,
    )


def test_refused_start_shows_the_error_row_without_a_reread():
    """A refused start leaves the rendered state alone and says why in the
    row the supervisor's own errors use -- no re-read that could overwrite
    the refusal before the user reads it."""
    _run_scenario(
        """
      setMirror(AVAILABLE_STOPPED);
      setCoupling({state: 'standby', latched: [], quiet_s: 300, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      calls.length = 0;
      setReply('stream_mirror_start',
               {ok: false, running: false,
                error: 'The stream mirror is missing from this installation.'});
      el('mirror-toggle').fire('click');
      await tick();
      assert.deepEqual(calls, [['stream_mirror_start']], calls);
      assert.ok(el('mirror-error').textContent.includes('missing'),
                el('mirror-error').textContent);
      assert.equal(el('mirror-state').textContent, 'Off');
    """,
        AVAILABLE_STOPPED=AVAILABLE_STOPPED,
    )


def test_entry_shows_the_setup_walk_and_the_unavailable_push_hides_it():
    """The #321 wiring, re-laid out to the dictated screenshot (2026-10-08):
    the four instruction paragraphs render under the setup heading on
    entry, and the whole walk -- heading included -- hides when the push
    says the installation has no mirror."""
    _run_scenario(
        """
      setMirror(AVAILABLE_RUNNING);
      setCoupling({state: 'armed', latched: [], quiet_s: 300, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      assert.equal(el('stream-setup').hidden, false);
      assert.equal(el('chord-row-hint').hidden, false);
      handlers.onMirrorStatus(UNAVAILABLE);
      assert.equal(el('stream-setup').hidden, true);
      assert.equal(el('chord-row-hint').hidden, true);
    """,
        AVAILABLE_RUNNING=AVAILABLE_RUNNING,
        UNAVAILABLE=UNAVAILABLE,
    )


def test_the_card_carries_the_dictated_screenshot_and_nothing_else():
    """2026-10-08: the card's resting copy is the user's dictated
    screenshot, verbatim -- the walk's old side texts (the toggle hint, the
    resolved exe path and the never-main-exe warning, the Combat auto-start
    divider and enable hint, the always-on collision line, the armed-row
    diagnostic) are gone from the markup, and the setup heading exists.
    The runtime double above fails on any id the module still wants, so
    this pins the other direction: ids the markup must NOT carry back."""
    html = (HERE.parent / "wingman" / "web" / "index.html").read_text(encoding="utf-8")
    for gone in (
        "mirror-toggle-hint",
        "mirror-exe-path",
        "mirror-exe-warning",
        "combat-autostart-group",
        "chord-enable-hint",
        "chord-collision",
        "chord-diagnostic",
    ):
        assert f'id="{gone}"' not in html, gone
    assert 'id="stream-setup"' in html
    assert "Discord Setup Instructions" in html


# ---- the probe record (#335/#337) ----------------------------------------


PROBE_LIVE = {
    "live": True,
    "live_display": "14:22",
    "degraded": None,
    "wingman_live": True,
    "budget_used": 2,
    "budget_limit": 300,
}


def test_the_probe_push_renders_the_live_badge():
    _run_scenario(
        """
      setMirror(AVAILABLE_RUNNING);
      setCoupling({state: 'armed', latched: [], quiet_s: 600, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      handlers.onStreamProbeStatus(PROBE_LIVE);
      assert.ok(el('coupling-probe').textContent.indexOf('verified 14:22') !== -1,
                    el('coupling-probe').textContent);
      assert.equal(el('coupling-probe-degraded').hidden, true);
      assert.equal(el('coupling-probe-budget').textContent,
                   'Probes today: 2 of 300');
    """,
        AVAILABLE_RUNNING=AVAILABLE_RUNNING,
        PROBE_LIVE=PROBE_LIVE,
    )


def test_a_degraded_probe_names_the_open_loop_reason():
    _run_scenario(
        """
      setMirror(AVAILABLE_RUNNING);
      setCoupling({state: 'armed', latched: [], quiet_s: 600, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      handlers.onStreamProbeStatus(
        {live: null, live_display: null, degraded: 'budget dry -- open-loop',
         wingman_live: false, budget_used: 300, budget_limit: 300});
      assert.equal(el('coupling-probe').textContent, '');
      assert.ok(el('coupling-probe-degraded').textContent.includes('budget dry'));
      assert.equal(el('coupling-probe-degraded').hidden, false);
    """,
        AVAILABLE_RUNNING=AVAILABLE_RUNNING,
    )


def test_not_live_replaces_the_badge():
    _run_scenario(
        """
      setMirror(AVAILABLE_RUNNING);
      setCoupling({state: 'armed', latched: [], quiet_s: 600, chord_sendable: true});
      document.fire('wm:section', {detail: 'streaming'});
      await tick();
      handlers.onStreamProbeStatus(PROBE_LIVE);
      handlers.onStreamProbeStatus(
        {live: false, live_display: '14:30', degraded: null,
         wingman_live: false, budget_used: 2, budget_limit: 300});
      assert.equal(el('coupling-probe').textContent, 'Not live');
    """,
        AVAILABLE_RUNNING=AVAILABLE_RUNNING,
        PROBE_LIVE=PROBE_LIVE,
    )
