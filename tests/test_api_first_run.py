"""The first-run gate: who sees that screen, and what a skip persists.

`_push_first_run_when_ready` had no test of its own, which is how the
screen came to be the only one in the app with no exit. PRODUCT.md holds
the uploader and EVE halves independent -- "It must not require the EVE
tools to upload a video, or a Google account to use the EVE tools" -- and
a mandatory OBS-recordings folder is the uploader half gating the other.

These assert the state machine around that, not the link that triggers it:
the page-side skip affordance lives in web/firstrun.js.
"""

from pathlib import Path

from tests import fakes
from wingman import settings as settings_mod


class FakeTimer:
    """Records the callback instead of scheduling it, and reports whether
    _push_first_run_when_ready got as far as arming anything at all."""

    armed = None

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.started = False
        FakeTimer.armed = self

    def start(self):
        self.started = True
        self.callback()


def api_for(tmp_path, **settings):
    api, _window = fakes.build_api(tmp_path, settings=settings or None)
    FakeTimer.armed = None
    api._timer = FakeTimer
    return api


# --- who gets shown the screen --------------------------------------------


def test_an_unconfigured_install_is_still_shown_the_first_run_screen(tmp_path):
    """The default path, unchanged. The skip key must not cost the screen
    to the users it exists for."""
    api = api_for(tmp_path)
    sent = fakes.record_pushes(api)

    api._push_first_run_when_ready()

    assert fakes.payloads(sent, "onFirstRun") == [{}]


def test_a_skipped_install_is_not_asked_again_on_the_next_launch(tmp_path):
    """The whole reason the skip is persisted. __main__ calls this whenever
    no recording folder RESOLVES, so a session-only skip would re-gate the
    EVE half on every launch."""
    api = api_for(tmp_path, first_run_skipped=True)
    sent = fakes.record_pushes(api)

    api._push_first_run_when_ready()

    assert fakes.payloads(sent, "onFirstRun") == []
    # Not merely un-pushed: no timer is armed either, so nothing is left
    # pending that could fire the route a second and a half later.
    assert FakeTimer.armed is None


# --- what the skip writes -------------------------------------------------


def test_skipping_persists_the_choice(tmp_path):
    api = api_for(tmp_path)

    result = api.skip_first_run()

    assert result["applied"] is True
    assert api._state.settings["first_run_skipped"] is True


def test_choosing_a_folder_later_ends_the_skip(tmp_path):
    """The skip defers a question; naming a real folder answers it. Without
    this an install that skipped once would keep the flag forever, and the
    screen would never return even after the folder went away."""
    folder = tmp_path / "recordings"
    folder.mkdir()
    api = api_for(tmp_path, first_run_skipped=True)

    api.set_folder("recording", str(folder))

    assert api._state.settings["first_run_skipped"] is False


def test_a_refused_folder_does_not_end_the_skip(tmp_path):
    """set_folder refuses a path that is not a directory, and a refusal
    settles nothing -- the user is still in the state the skip recorded."""
    api = api_for(tmp_path, first_run_skipped=True)

    result = api.set_folder("recording", str(tmp_path / "nope"))

    assert result["applied"] is False
    assert api._state.settings["first_run_skipped"] is True


def test_the_gamelogs_folder_is_not_a_first_run_answer(tmp_path):
    """set_folder serves both folders. Only the recording one is what the
    first-run screen asks for, so only it can clear the flag."""
    logs = tmp_path / "gamelogs"
    logs.mkdir()
    api = api_for(tmp_path, first_run_skipped=True)

    api.set_folder("gamelogs", str(logs))

    assert api._state.settings["first_run_skipped"] is True


# --- what the Uploader shows afterwards -----------------------------------


def test_a_skipped_install_gets_an_empty_list_rather_than_a_blank_screen(tmp_path):
    """#list-empty starts hidden in markup and is only unhidden by list.js's
    render(), which runs on this push. Without it the screen the skip routes
    to has no rows, no empty state and no explanation -- the inert screen
    DESIGN.md warns is indistinguishable from a broken one."""
    api = api_for(tmp_path, first_run_skipped=True)
    api._state.recording_dir = None
    sent = fakes.record_pushes(api)

    api.list_rows()

    assert fakes.payloads(sent, "onRows") == [{"rows": []}]


def test_an_unconfigured_install_still_pushes_nothing(tmp_path):
    """list_rows' documented guard, unchanged: during first run the page is
    showing its own route, and an empty push would replace that screen with
    an empty uploader and no explanation."""
    api = api_for(tmp_path)
    api._state.recording_dir = None
    sent = fakes.record_pushes(api)

    api.list_rows()

    assert fakes.payloads(sent, "onRows") == []


# --- the persisted shape ---------------------------------------------------


def test_the_flag_survives_a_round_trip_through_the_settings_file(tmp_path):
    """save() projects the COMPLETE document from DEFAULTS, so a key absent
    from DEFAULTS is dropped on every write. This is the regression that
    would make the skip look like it worked and then forget it."""
    path = Path(tmp_path) / "settings.json"
    cfg = settings_mod.load(path)
    cfg["first_run_skipped"] = True
    settings_mod.save(cfg, path)

    assert settings_mod.load(path)["first_run_skipped"] is True


def test_a_hand_edited_value_is_coerced_to_a_real_bool(tmp_path):
    """Coerced rather than defaulted, exactly like show_eve_tools: what
    matters is that the stored value is a bool, because the gate and the
    tests around it assert on `is True`. The truthy/empty split that follows
    is the same one show_eve_tools already accepts, and is asserted here so
    it is a decision on record rather than an accident."""
    path = Path(tmp_path) / "settings.json"
    path.write_text('{"first_run_skipped": "no"}', encoding="utf-8")

    assert settings_mod.load(path)["first_run_skipped"] is True
    path.write_text('{"first_run_skipped": ""}', encoding="utf-8")
    assert settings_mod.load(path)["first_run_skipped"] is False
