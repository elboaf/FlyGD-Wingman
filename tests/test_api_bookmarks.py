"""The bridge is tested headless through FakeWindow, as every other Api
method is (tests/fakes.py)."""
import json
import pytest
from obs_youtube_uploader import bookmarks, hotkeys, settings
from tests.fakes import FakeWindow


class FakeEngine:
    def __init__(self):
        self.applied = []
        self.started = 0
        self.stopped = 0
        self.commands = []
        self.running = False
        self.last_error = None

    def apply(self, section):
        self.applied.append(section)

    def start(self):
        self.started += 1
        self.running = True
        return True

    def stop(self, timeout=5.0):
        self.stopped += 1
        self.running = False

    def is_running(self):
        return self.running

    def sync_sequence(self):
        pass

    def send_command(self, name, argument=""):
        self.commands.append((name, argument))
        return True

    def status(self, enabled, now=None):
        if not enabled:
            return hotkeys.EngineStatus(state="off")
        if not self.running:
            return hotkeys.EngineStatus(state="stopped",
                                        last_error=self.last_error)
        return hotkeys.EngineStatus(state="running", root="J1234")


@pytest.fixture
def api(tmp_path, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod.paths, "settings_file",
                        lambda: tmp_path / "s.json")
    state = api_mod.AppState(recording_dir=tmp_path,
                             settings=settings.load(tmp_path / "s.json"))
    state.engine = FakeEngine()
    built = api_mod.Api(state)
    built._window = FakeWindow()
    return built


def test_get_returns_settings_labels_and_order(api):
    got = api.get_bookmarks()
    assert got["settings"]["enabled"] is False
    assert got["order"] == list(bookmarks.BIND_IDS)
    assert got["labels"]["FinH"] == "Finisher: HS (highsec)"


def test_get_returns_human_labels_for_bound_keys(api):
    """The page must never translate a hotkey string itself -- that is why
    to_ahk returns a display value. Unbound ids are absent rather than
    empty so the page's `|| 'Not set'` fallback fires."""
    got = api.get_bookmarks()
    assert got["displays"]["ConvertScout"] == "Ctrl+Shift+S"
    assert "FinH" not in got["displays"]


def test_get_lists_live_eve_windows(api, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod.evewindows, "list_eve_windows",
                        lambda: ["EVE - Pilot"])
    assert api.get_bookmarks()["windows"] == ["EVE - Pilot"]


def test_save_persists_and_regenerates_the_ini(api, tmp_path):
    section = dict(api.get_bookmarks()["settings"])
    section["keybinds"] = dict(bookmarks.DEFAULT_BINDS, FinH="^h")
    api.save_bookmarks(section)
    assert api._state.engine.applied[-1]["keybinds"]["FinH"] == "^h"
    on_disk = json.loads((tmp_path / "s.json").read_text())
    assert on_disk["eve_bookmarks"]["keybinds"]["FinH"] == "^h"


def test_enabling_starts_the_engine_and_disabling_stops_it(api):
    section = dict(api.get_bookmarks()["settings"], enabled=True)
    api.save_bookmarks(section)
    assert api._state.engine.started == 1
    api.save_bookmarks(dict(section, enabled=False))
    assert api._state.engine.stopped == 1


def test_save_reports_collisions_rather_than_silently_accepting(api):
    """RefreshHotkeys would let one bind win silently."""
    section = dict(api.get_bookmarks()["settings"])
    section["keybinds"] = dict(bookmarks.DEFAULT_BINDS, FinH="^h", FinL="^h")
    got = api.save_bookmarks(section)
    assert got["collisions"] == {"^h": ["FinH", "FinL"]}


def test_save_rejects_a_non_dict_payload(api):
    """Everything from the page is untrusted input to a file that drives a
    keyboard hook."""
    before = api.get_bookmarks()["settings"]
    api.save_bookmarks("nonsense")
    assert api.get_bookmarks()["settings"] == before


def test_a_settings_file_that_cannot_be_written_leaves_state_untouched(api, monkeypatch):
    """Same contract as save_settings: bail before touching in-memory state
    so state and disk never diverge, and tell the user why."""
    from obs_youtube_uploader.ui import api as api_mod
    from tests import fakes
    api._alert = fakes.Alerts()
    before = api.get_bookmarks()["settings"]

    def boom(cfg, path=None):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "save", boom)

    section = dict(before, keybinds=dict(bookmarks.DEFAULT_BINDS, FinH="^h"))
    got = api.save_bookmarks(section)
    assert got["settings"] == before
    assert api._alert.titles() == ["Could not save settings"]
    assert api._state.engine.applied == []


def test_capture_and_parse_delegate_to_bookmarks(api):
    assert api.capture_bind({"ctrl": True, "alt": False, "shift": True,
                             "meta": False, "code": "KeyS"})["ahk"] == "^+s"
    assert api.parse_bind("+^s")["ahk"] == "^+s"


def test_eve_command_is_forwarded(api):
    api.eve_command("set_root", "J1234")
    assert api._state.engine.commands == [("set_root", "J1234")]


def test_import_applies_and_reports(api, tmp_path, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod, "_open_file_dialog_kind", lambda: "OPEN")
    legacy = tmp_path / "eve_bookmark_helper.ini"
    legacy.write_text("[Keybinds]\r\nFinH=y\r\nCopy=^c\r\n")
    api._window.dialog_result = (str(legacy),)
    got = api.import_bookmarks()
    assert got["ok"] is True
    binds = api.get_bookmarks()["settings"]["keybinds"]
    assert binds["FinH"] == "y"
    assert "Copy" not in binds
    # Not empty any more: a legacy Copy bind has nowhere to go and the
    # route tells the user so.
    assert got["discarded"] == ["Copy (hotkey, no longer part of Wingman)"]


def test_import_reads_the_utf16_a_real_helper_ini_is_written_in(
        api, tmp_path, monkeypatch):
    """AutoHotkey's IniWrite emits UTF-16 LE on a Unicode build, which is
    what the file in the wild actually is. Read as UTF-8 it parsed as
    nothing, and that nothing was then saved over the user's settings while
    the dialog said "Import complete"."""
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod, "_open_file_dialog_kind", lambda: "OPEN")
    legacy = tmp_path / "eve_bookmark_helper.ini"
    legacy.write_bytes(
        "\ufeff[Keybinds]\r\nFinH=y\r\nGrabSig=^j\r\n"
        "[Enabled]\r\nEVE - Pilot=1\r\n".encode("utf-16-le"))
    api._window.dialog_result = (str(legacy),)
    assert api.import_bookmarks()["ok"] is True
    section = api.get_bookmarks()["settings"]
    assert section["keybinds"]["FinH"] == "y"
    assert section["keybinds"]["GrabSig"] == "^j"
    assert section["windows"] == {"EVE - Pilot": True}


def test_an_unparseable_file_does_not_wipe_the_existing_settings(
        api, tmp_path, monkeypatch):
    """The failure mode the encoding bug actually caused: nothing parsed,
    and the empty result was saved over real settings."""
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod, "_open_file_dialog_kind", lambda: "OPEN")
    api.save_bookmarks({**api.get_bookmarks()["settings"],
                        "keybinds": {"FinH": "^h"}})
    junk = tmp_path / "junk.ini"
    junk.write_bytes(b"\x00\x01 not an ini at all")
    api._window.dialog_result = (str(junk),)
    got = api.import_bookmarks()
    assert got["ok"] is False
    assert got["notes"], "a refusal must say why"
    assert api.get_bookmarks()["settings"]["keybinds"]["FinH"] == "^h"


def test_reset_binds_overwrites_every_bind(api):
    """The standalone GUI's Reset Defaults button. Overwrite, not
    fill-blanks: a reset whose effect depends on hidden state is not one."""
    api.save_bookmarks({**api.get_bookmarks()["settings"],
                        "keybinds": {"FinH": "^h", "GrabSig": "^g"}})
    binds = api.reset_binds()["settings"]["keybinds"]
    assert binds == bookmarks.RECOMMENDED_BINDS


def test_import_cancelled_changes_nothing(api, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod, "_open_file_dialog_kind", lambda: "OPEN")
    api._window.dialog_result = None
    assert api.import_bookmarks()["ok"] is False


def test_a_failed_start_is_reported_to_the_page(api):
    """Otherwise the toggle reads "on" while nothing is running, and the
    reason -- a missing engine binary -- never reaches the user."""
    api._state.engine.start = lambda: False
    api._state.engine.last_error = "The bookmark engine is missing."
    section = dict(api.get_bookmarks()["settings"], enabled=True)
    got = api.save_bookmarks(section)
    assert got["engine"]["state"] == "stopped"
    assert "missing" in got["engine"]["last_error"]


def test_a_failed_start_does_not_crash_the_save(api):
    """A save that raises would leave the page with no response at all."""
    api._state.engine.start = lambda: False
    section = dict(api.get_bookmarks()["settings"], enabled=True)
    assert api.save_bookmarks(section)["settings"]["enabled"] is True


def test_import_does_not_claim_success_when_the_save_fails(
        api, tmp_path, monkeypatch):
    """save_bookmarks returns the same shape whether it wrote or refused, so
    import used to report "Import complete" beside the error dialog naming
    the failure. The `saved` flag is what lets it tell the two apart."""
    from obs_youtube_uploader.ui import api as api_mod
    monkeypatch.setattr(api_mod, "_open_file_dialog_kind", lambda: "OPEN")
    legacy = tmp_path / "eve_bookmark_helper.ini"
    legacy.write_text("[Keybinds]\r\nFinH=y\r\n")
    api._window.dialog_result = (str(legacy),)

    def boom(*a, **kw):
        raise OSError("read-only file system")
    monkeypatch.setattr(api_mod.settings_mod, "save", boom)

    got = api.import_bookmarks()
    assert got["ok"] is False
    # No note of its own: save_bookmarks already alerted with the reason,
    # and a second message would mean two dialogs for one failure.
    assert got["notes"] == []


def test_save_bookmarks_reports_whether_it_actually_wrote(api, monkeypatch):
    from obs_youtube_uploader.ui import api as api_mod
    section = api.get_bookmarks()["settings"]
    assert api.save_bookmarks(section)["saved"] is True
    assert api.save_bookmarks("not a dict")["saved"] is False

    def boom(*a, **kw):
        raise OSError("nope")
    monkeypatch.setattr(api_mod.settings_mod, "save", boom)
    assert api.save_bookmarks(section)["saved"] is False
