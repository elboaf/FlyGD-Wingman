"""Per-field settings writes.

The Settings screen commits one field at a time and has no Save button, so
these endpoints carry the guards the old whole-document `save_settings`
got for free from an explicit commit. Each one is a guard that a blur or a
stray change must not be able to walk through.

The harness is `test_api_settings.settings_api`, reused rather than
rebuilt: it fakes only `_save_locked`, so the real lock-and-rollback
machinery in `settings.update` stays in the loop.
"""

import json

import pytest

from tests import fakes
from tests.test_api_settings import settings_api
from wingman import discord, paths
from wingman.ui import api as api_mod

# ---- shape ------------------------------------------------------------


def test_a_refusal_is_distinguishable_from_a_failed_write(monkeypatch, tmp_path):
    """Three outcomes, not two. A bare bool would collapse "we rejected
    what you typed" and "it took effect but did not reach the disk" into
    one answer, and the page has to say something different for each."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    refused = api.set_category("gaming")
    assert refused["applied"] is False
    assert refused["persisted"] is False
    assert refused["error"]

    ok = api.set_category("22")
    assert ok == {"applied": True, "persisted": True, "error": None}


def test_an_unwritable_settings_file_still_applies_the_change(monkeypatch, tmp_path):
    """A settings file that cannot be written must not stop the setting
    taking effect -- but the page has to be able to say it is not saved,
    or the control shows a choice the next restart discards."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    def boom(data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", boom)
    result = api.set_privacy("public")

    assert result["applied"] is True
    assert result["persisted"] is False


# ---- the no-op guard --------------------------------------------------


def test_rewriting_the_same_value_does_not_touch_the_file(monkeypatch, tmp_path):
    """settings.save projects the COMPLETE document, so a no-op write is a
    full rewrite -- and an immediate-save page re-emits on every render.
    save_settings had no such guard and also re-ran OBS detection and a
    whole list_rows() ffprobe sweep each time."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    api.set_privacy("public")
    assert saved["privacy"] == "public"

    saved.clear()
    result = api.set_privacy("public")

    assert result["applied"] is True
    assert saved == {}, "a no-op write reached _save_locked"


# ---- scalars ----------------------------------------------------------


@pytest.mark.parametrize("value", ["private", "unlisted", "public"])
def test_every_privacy_the_select_offers_is_accepted(monkeypatch, tmp_path, value):
    # Asserted on the live settings, not on what reached the disk: the
    # harness starts at "unlisted", and that case is a no-op write by
    # design (see the guard test above). Both paths must still leave the
    # setting at the requested value.
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    assert api.set_privacy(value)["applied"] is True
    assert api._state.settings["privacy"] == value


def test_a_bogus_privacy_is_refused_rather_than_silently_coerced(monkeypatch, tmp_path):
    """settings._normalize would quietly turn this into the default, which
    on an immediate-save screen means the user watches their choice snap
    back with no explanation."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_privacy("secret")["applied"] is False
    assert saved == {}


def test_a_non_numeric_category_is_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_category("gaming")["applied"] is False
    assert saved == {}


def test_a_category_is_stripped_before_it_is_stored(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_category("  22  ")["applied"] is True
    assert saved["category"] == "22"


def test_a_bogus_notify_mode_is_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_notify_mode("carrier-pigeon")["applied"] is False
    assert saved == {}


# ---- the webhook ------------------------------------------------------


def test_an_empty_webhook_is_refused_rather_than_treated_as_a_clear(
    monkeypatch, tmp_path
):
    """THE wipe guard. save_settings skips validation entirely when the
    value is empty and writes "", so under immediate-save a select-all,
    Delete, then look away would destroy a configured secret -- with no
    Cancel to take it back and no pre-edit copy anywhere on the page."""
    api, _window, saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={"discord_webhook": "https://discord.com/api/webhooks/1/abc"},
    )

    result = api.set_discord_webhook("")

    assert result["applied"] is False
    assert saved == {}
    assert api._state.settings["discord_webhook"] == (
        "https://discord.com/api/webhooks/1/abc"
    )


def test_whitespace_alone_is_also_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_discord_webhook("   ")["applied"] is False
    assert saved == {}


def test_an_unparseable_webhook_is_refused_and_says_why(monkeypatch, tmp_path):
    """The parse error is returned for the field's own inline message.
    save_settings routed this through _alert, which QUEUES -- so a URL
    typed a character at a time stacked a pile of modal dialogs."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)

    result = api.set_discord_webhook("https://example.com/not-a-webhook")

    assert result["applied"] is False
    assert result["error"]
    assert saved == {}


def test_clearing_a_webhook_is_its_own_explicit_action(monkeypatch, tmp_path):
    api, _window, saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={"discord_webhook": "https://discord.com/api/webhooks/1/abc"},
    )

    assert api.clear_discord_webhook()["applied"] is True
    assert saved["discord_webhook"] == ""


def test_setting_a_webhook_returns_the_new_summary_line(monkeypatch, tmp_path):
    """The page cannot derive this line -- copy.webhook_status is the only
    description of what is stored and settings.js is forbidden to rebuild
    it -- and nothing repaints the Settings route after page load:
    get_settings is fetched once at startup and the per-field endpoints
    deliberately never push. Without the line on the commit's own return,
    a webhook persisted while the card kept saying `not configured` and
    Show/Remove stayed disabled for the rest of the session.
    """
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    url = "https://discord.com/api/webhooks/1538615213203656754/abcdefGHIJ"

    result = api.set_discord_webhook(url)

    assert result["applied"] is True
    assert result["webhook_status"] == discord.describe(discord.parse_webhook(url)[0])


def test_clearing_a_webhook_returns_the_not_configured_line(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(
        tmp_path,
        monkeypatch,
        settings={
            "discord_webhook": (
                "https://discord.com/api/webhooks/1538615213203656754/abcdefGHIJ"
            )
        },
    )

    assert api.clear_discord_webhook()["webhook_status"] == "not configured"


def test_a_refused_webhook_does_not_restate_the_summary(monkeypatch, tmp_path):
    """Nothing changed, so the line already on screen still describes what
    is stored. Overwriting it would replace a description of the STORED
    value with one derived from what the user typed and had rejected."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    result = api.set_discord_webhook("")

    assert result["applied"] is False
    assert "webhook_status" not in result


# ---- folders ----------------------------------------------------------


def test_a_new_recording_folder_rebinds_the_live_watcher(monkeypatch, tmp_path):
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    assert api.set_folder("recording", str(new_dir))["applied"] is True

    assert watcher.rebound == [new_dir]
    assert api._state.recording_dir == new_dir


def test_recommitting_the_same_folder_never_rebinds(monkeypatch, tmp_path):
    """THE re-baseline guard, and the reason free text commits on Enter
    rather than on blur. rebind() marks every file already in the folder
    as seen, so a redundant rebind silently suppresses the announcement
    for anything that landed since startup but has not yet been polled."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    api.set_folder("recording", str(tmp_path))

    assert watcher.rebound == []


def test_a_rebind_reports_how_many_recordings_it_silenced(monkeypatch, tmp_path):
    """Round 3's B11 answer. A hint written before the click cannot carry
    the number -- it depends on the folder the user is about to name -- so
    the disclosure is a report the endpoint sends back, and the page shows
    it in the same .field-msg slot a refusal uses.

    The count is the recordings rebind() has just marked as seen: they are
    still listed, they simply arrive unannounced and unticked.
    """
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (new_dir / name).write_bytes(b"x")
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    result = api.set_folder("recording", str(new_dir))

    assert watcher.rebound == [new_dir]
    assert result["note"] == (
        f"Now watching {new_dir}. 3 recordings already there were not announced."
    )


def test_an_empty_new_folder_reports_the_move_and_no_count(monkeypatch, tmp_path):
    """ "0 recordings were not announced" is a sentence the reader has to
    parse twice to learn nothing happened."""
    new_dir = tmp_path / "empty"
    new_dir.mkdir()
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    assert (
        api.set_folder("recording", str(new_dir))["note"] == f"Now watching {new_dir}."
    )


def test_one_silenced_recording_is_singular(monkeypatch, tmp_path):
    new_dir = tmp_path / "one"
    new_dir.mkdir()
    (new_dir / "a.mp4").write_bytes(b"x")
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    assert (
        "1 recording already there was not announced"
        in (api.set_folder("recording", str(new_dir))["note"])
    )


def test_a_first_folder_reports_no_suppression_it_cannot_vouch_for(
    monkeypatch, tmp_path
):
    """The other branch. With no watcher yet, start_watching() calls
    Watcher.baseline(), which silently baselines only on a first-EVER run
    and otherwise announces what it finds -- so "were not announced" would
    be a guess. No note rather than a wrong one.
    """
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    (new_dir / "a.mp4").write_bytes(b"x")
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=None)
    api._on_recording_dir_ready = lambda folder: None

    assert "note" not in api.set_folder("recording", str(new_dir))


def test_recommitting_the_same_folder_reports_nothing(monkeypatch, tmp_path):
    """The early return is the whole point: nothing was rebound, so there
    is nothing to report, and a note would tell the user a cost they did
    not pay."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    assert "note" not in api.set_folder("recording", str(tmp_path))


def test_a_folder_that_does_not_exist_leaves_the_watcher_alone(monkeypatch, tmp_path):
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    result = api.set_folder("recording", str(tmp_path / "nope"))

    assert result["applied"] is False
    assert watcher.rebound == []
    assert saved == {}
    assert api._state.recording_dir == tmp_path


def test_an_empty_recording_folder_does_not_blame_a_folder_called_None(
    monkeypatch, tmp_path
):
    """save_settings mapped an empty field to Path("None") and told the
    user that "None is not a folder"."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    result = api.set_folder("recording", "")

    assert result["applied"] is False
    assert "None" not in result["error"]


def test_a_first_folder_starts_watching_instead_of_rebinding(monkeypatch, tmp_path):
    """The hole this endpoint closes. set_recording_dir could only CREATE
    a watcher and save_settings could only REPOINT one, so with _watcher
    None the folder persisted and list_rows un-gated -- the window looked
    healthy -- while nothing ever started polling."""
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=None)
    started = []
    api._on_recording_dir_ready = started.append

    assert api.set_folder("recording", str(new_dir))["applied"] is True

    assert started == [new_dir]


def test_an_empty_gamelogs_folder_is_stored_as_no_folder(monkeypatch, tmp_path):
    """Unlike the recording folder this drives no watcher, and empty
    legitimately means "I have no gamelogs folder"."""
    api, _window, saved = settings_api(
        tmp_path, monkeypatch, settings={"gamelogs_dir": str(tmp_path)}
    )

    assert api.set_folder("gamelogs", "")["applied"] is True
    assert saved["gamelogs_dir"] is None


def test_a_gamelogs_folder_that_does_not_exist_is_refused(monkeypatch, tmp_path):
    """save_settings never validated this one at all, so every
    intermediate prefix of a typed path persisted silently."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)

    assert api.set_folder("gamelogs", str(tmp_path / "nope"))["applied"] is False
    assert saved == {}


# ---- invariants carried over from save_settings -----------------------
#
# These were written against save_settings and are ported here rather than
# retired with it: they encode properties of ANY settings write, and the
# per-field endpoints are the writer now.


def test_the_settings_object_survives_a_per_field_write(monkeypatch, tmp_path):
    """Regression test for the settings rebind race, re-aimed.

    save_settings, set_recording_dir and save_bookmarks used to finish with
    `self._state.settings = settings_mod.load()`, replacing the dict with a
    fresh one read back from disk. preview/store.py's LayoutStore keeps its
    own reference to that same dict and writes through it later, so a store
    reference captured before a rebind landed on an orphaned object, and
    the next save overwrote disk with a document that had silently lost it.

    `_write_setting` goes through settings.update, which normalises in
    place, so identity survives. Asserted directly, because nothing else
    would notice if a future edit reintroduced a rebind.
    """
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(paths, "settings_file", lambda: settings_path)
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    api.list_rows = lambda preselect=None: None

    # Stands in for LayoutStore, which captures this object once and reuses
    # it across writes.
    captured_ref = api._state.settings

    assert api.set_category("22")["applied"] is True
    assert api._state.settings is captured_ref

    with api_mod.settings_mod.update(captured_ref) as cfg:
        cfg["preview"]["layouts"]["Pilot"] = {"x": 0, "y": 0, "w": 320, "h": 210}

    # A second, unrelated write must not discard that layout.
    assert api.set_privacy("public")["applied"] is True

    on_disk = json.loads(settings_path.read_text())
    assert "Pilot" in on_disk["preview"]["layouts"]
    assert "Pilot" in api._state.settings["preview"]["layouts"]


def test_a_per_field_write_does_not_revert_the_uploaders_channel(monkeypatch, tmp_path):
    """save_settings once built its payload from a snapshot taken outside
    _SAVE_LOCK, so a channel learned from an upload mid-save was projected
    away. The per-field endpoints mutate the live document inside the lock
    instead of sending a payload at all, which is what makes this hold."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(paths, "settings_file", lambda: settings_path)
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    api.list_rows = lambda preselect=None: None

    # As the uploader records it after videos.insert answers.
    with api_mod.settings_mod.update(api._state.settings) as cfg:
        cfg["channel_id"] = "UC123"
        cfg["channel_title"] = "Test Channel"

    assert api.set_category("22")["applied"] is True

    on_disk = json.loads(settings_path.read_text())
    assert on_disk["channel_id"] == "UC123"
    assert on_disk["channel_title"] == "Test Channel"


def test_a_failed_write_leaves_state_and_disk_agreeing(monkeypatch, tmp_path):
    """State and disk must never diverge: a divergence survives until the
    next launch reads the file back. settings.update restores the live dict
    when the block raises, which is what protects this."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    before = api._state.settings["privacy"]

    def boom(data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", boom)
    result = api.set_privacy("public")

    assert result["persisted"] is False
    # The rollback is what matters: the live dict must not be left holding
    # a value that never reached disk.
    assert api._state.settings["privacy"] == before


# --- start on login (M3) ----------------------------------------------------


class FakeAutostart:
    """Stands in for the autostart module's three entry points."""

    def __init__(self, enabled=False, denied=False):
        self.enabled = enabled
        self.denied = denied
        self.calls = []

    def is_enabled(self):
        return self.enabled

    def enable(self):
        self.calls.append("enable")
        if self.denied:
            raise OSError("access is denied by policy")
        self.enabled = True

    def disable(self):
        self.calls.append("disable")
        if self.denied:
            raise OSError("access is denied by policy")
        self.enabled = False


def test_start_on_login_is_read_from_the_registry_not_from_settings(
    monkeypatch, tmp_path
):
    """The login entry IS the state. A settings.json copy would go stale the
    first time a user deletes the entry from Task Manager's Startup tab, and
    the checkbox would then describe a world that no longer exists."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "autostart", FakeAutostart(enabled=True))

    payload = api.get_settings()

    assert payload["start_on_login"] is True
    # Derived, top level, and never written back as a setting.
    assert "start_on_login" not in payload["settings"]
    assert "start_on_login" not in api._state.settings


def test_turning_start_on_login_on_and_off_reaches_the_registry(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    fake = FakeAutostart()
    monkeypatch.setattr(api_mod, "autostart", fake)

    assert api.set_start_on_login(True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api.get_settings()["start_on_login"] is True

    assert api.set_start_on_login(False)["applied"] is True
    assert api.get_settings()["start_on_login"] is False
    assert fake.calls == ["enable", "disable"]


def test_a_refused_registry_write_is_reported_not_swallowed(monkeypatch, tmp_path):
    """A managed machine can deny the Run key by policy. A checkbox that
    assumed success would silently do nothing at every boot, which is what
    the commit contract exists to prevent."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "autostart", FakeAutostart(denied=True))

    result = api.set_start_on_login(True)

    assert result["applied"] is False
    assert result["persisted"] is False
    assert "login entry" in result["error"]
    # Says WHY, carrying the OS's own words -- "it did not work" alone is
    # not diagnosable from a bug report.
    assert "policy" in result["error"]


def test_a_non_boolean_is_refused_rather_than_coerced(monkeypatch, tmp_path):
    """Coercion would let a stray truthy value register a login entry the
    user never ticked -- and this one writes outside the app's own config."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    fake = FakeAutostart()
    monkeypatch.setattr(api_mod, "autostart", fake)

    result = api.set_start_on_login("yes")

    assert result["applied"] is False
    assert fake.calls == []


# ---- preview size / snap / reset --------------------------------------


def test_parse_preview_size_reports_an_error_rather_than_raising(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    assert api.parse_preview_size("nonsense")["error"]
    assert api.parse_preview_size("1280x720") == {"w": 1280, "h": 720, "error": None}


def test_set_preview_size_refuses_below_the_floor(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    result = api.set_preview_size("Alice", 10, 10)

    assert result["applied"] is False
    assert "120x90" in result["error"]


def test_set_preview_size_refuses_a_character_with_no_saved_rect(monkeypatch, tmp_path):
    """There is no x/y to write, and layout.deserialize drops any entry
    missing a full rect -- so a w/h written alone vanishes at the next
    load, after the page has reported it accepted."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    result = api.set_preview_size("Nobody", 640, 392)

    assert result["applied"] is False


def test_set_preview_size_rewrites_an_offline_entry_in_place(monkeypatch, tmp_path):
    # No _api(layouts=...) helper exists; seed the saved layout directly on
    # the state built by settings_api, same as production code would see
    # it after settings.load() ran the entry through preview_layout.
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._state.settings["preview"]["layouts"]["Alice"] = {
        "x": 5,
        "y": 6,
        "w": 320,
        "h": 210,
    }

    result = api.set_preview_size("Alice", 640, 392)

    assert result["applied"] is True
    saved = api._state.settings["preview"]["layouts"]["Alice"]
    assert (saved["w"], saved["h"], saved["x"]) == (640, 392, 5)


class _FakeSizeHost:
    """Just enough of PreviewHost for _preview_sizes and set_bind_capture:
    characters(), is_running and set_capture(). Not fakes.py's build_api-produced host, because
    settings_api/build_api take no preview_host kwarg -- this is assigned
    onto the built Api the same way settings_api tests already assign
    api._alert."""

    def __init__(self, characters=(), is_running=True):
        self._characters = list(characters)
        self.is_running = is_running
        self.captures = []

    def characters(self):
        return list(self._characters)

    def set_capture(self, armed):
        self.captures.append(armed)


def test_preview_sizes_falls_back_to_the_configured_default(monkeypatch, tmp_path):
    """A character with no layout entry has never been dragged or typed
    into, so the Size... dialog must not open on an empty field quoting a
    number that matches nothing on screen -- it should show
    preview.width/height, the pair every unsaved preview actually opens
    at (__main__.py's PreviewHost(size=...))."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._state.settings["preview"]["width"] = 800
    api._state.settings["preview"]["height"] = 500
    api._state.settings["preview"]["seen"] = ["Alice"]

    assert api._preview_sizes() == {"Alice": [800, 500]}


def test_preview_sizes_prefers_a_real_layout_entry_over_the_default(
    monkeypatch, tmp_path
):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._state.settings["preview"]["layouts"]["Alice"] = {
        "x": 0,
        "y": 0,
        "w": 640,
        "h": 392,
    }

    assert api._preview_sizes() == {"Alice": [640, 392]}


def test_preview_sizes_skips_a_malformed_layout_entry_rather_than_raising(
    monkeypatch, tmp_path
):
    """layout.deserialize already drops an entry missing a full rect before
    it ever reaches settings, but _preview_sizes reads the settings dict
    straight rather than through that path -- so it needs its own guard
    against an entry that lost its "w" some other way."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._state.settings["preview"]["layouts"]["Alice"] = {"x": 0, "y": 0, "h": 210}

    assert api._preview_sizes() == {}


def test_preview_sizes_defaults_a_running_character_the_host_has_not_dragged(
    monkeypatch, tmp_path
):
    """The common case the bug report was about: a preview opened and never
    dragged reports host.characters() but no layout entry."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._preview_host = _FakeSizeHost(characters=["Bob"], is_running=True)

    assert api._preview_sizes() == {"Bob": [320, 210]}


def test_preview_sizes_ignores_a_stopped_hosts_characters(monkeypatch, tmp_path):
    """Same gate get_preview_hotkey_state already uses: a stopped host's
    last-known characters() must not be treated as rows that need a
    default, the same as it must not be reported as registered chords."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._preview_host = _FakeSizeHost(characters=["Bob"], is_running=False)

    assert api._preview_sizes() == {}


def test_set_bind_capture_reaches_the_host(monkeypatch, tmp_path):
    """The page waits on this call before it invites a keystroke, so the
    answer has to mean the host really knows."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    host = _FakeSizeHost()
    api._preview_host = host

    assert api.set_bind_capture(True) is True
    assert host.captures == [True]
    assert api.set_bind_capture(False) is True
    assert host.captures == [True, False]


def test_set_bind_capture_without_a_host_says_so(monkeypatch, tmp_path):
    """False, not a raise: previews are optional (build_preview_host
    returns None off Windows and on a construction failure), and the bind
    screen is still reachable. The page's own keydown path is unaffected
    -- with no host there are no registered chords to be swallowed by."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._preview_host = None

    assert api.set_bind_capture(True) is False
def test_set_preview_lock_aspect_persists_and_pushes_live(monkeypatch, tmp_path):
    """Read per mouse-move by PreviewWindow, exactly like snap, so a write
    that does not restyle would leave the checkbox inert until restart."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._preview_host = _RestyleSpy()

    result = api.set_preview_lock_aspect(False)

    assert result["applied"] is True
    assert api._state.settings["preview"]["lock_aspect"] is False
    assert api._preview_host.restyled == 1


def test_set_preview_lock_aspect_coerces_to_a_bool(monkeypatch, tmp_path):
    """The bridge hands over whatever JS sent. settings.validated_preview
    drops a non-bool on the next load, so an uncoerced truthy string would
    survive this session and vanish at the next launch."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    api._preview_host = _RestyleSpy()

    api.set_preview_lock_aspect("")

    assert api._state.settings["preview"]["lock_aspect"] is False


class _RestyleSpy:
    """Just enough PreviewHost for the restyle assertion above."""

    def __init__(self):
        self.restyled = 0

    def restyle(self):
        self.restyled += 1
