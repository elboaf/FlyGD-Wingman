"""Client discovery. Every collaborator is injected so identity and
filtering logic is testable off Windows."""

from obs_youtube_uploader.preview import discovery

WINDOWS = [(0x10, "EVE - Pilot One"), (0x20, "Firefox"), (0x30, "EVE - Pilot Two")]
PIDS = {0x10: 100, 0x20: 200, 0x30: 300}
IMAGES = {100: "exefile.exe", 200: "firefox.exe", 300: "exefile.exe"}


def _list(**kw):
    kw.setdefault("enumerator", lambda: WINDOWS)
    kw.setdefault("pids", PIDS.get)
    kw.setdefault("image_name", IMAGES.get)
    return discovery.list_clients(**kw)


def test_finds_eve_clients():
    assert [c.character for c in _list()] == ["Pilot One", "Pilot Two"]


def test_rejects_a_non_eve_process_with_an_eve_title():
    """A browser tab titled 'EVE - something' must not become a preview.
    Title alone is user-controlled; the process name is not."""
    windows = [(0x40, "EVE - Not A Client")]
    out = discovery.list_clients(
        enumerator=lambda: windows,
        pids={0x40: 400}.get,
        image_name={400: "chrome.exe"}.get,
    )
    assert out == []


def test_does_not_apply_the_engine_ini_rule():
    """bookmarks.is_engine_window_title also rejects '=' because the AHK
    INI format cannot carry it (bookmarks.py:308-309). That is a storage
    constraint of a different feature, not a property of EVE clients, and
    reusing it here would silently drop a previewable window."""
    windows = [(0x50, "EVE - Odd=Name")]
    out = discovery.list_clients(
        enumerator=lambda: windows,
        pids={0x50: 500}.get,
        image_name={500: "exefile.exe"}.get,
    )
    assert len(out) == 1


def test_stable_key_is_the_character_name():
    assert _list()[0].stable_key == "Pilot One"


def test_character_select_has_no_character_and_falls_back_to_the_handle():
    """A client at character select has no name. It must still preview,
    but must never have a layout persisted against it -- the next client
    to sit at that screen would inherit the position."""
    windows = [(0x60, "EVE")]
    out = discovery.list_clients(
        enumerator=lambda: windows,
        pids={0x60: 600}.get,
        image_name={600: "exefile.exe"}.get,
    )
    assert out[0].character is None
    assert out[0].stable_key == "hwnd:0x60"


def test_access_denied_on_image_name_drops_the_window():
    """OpenProcess fails for another user's or a higher-integrity process.
    That is expected, not an error, and must not raise."""
    out = _list(image_name=lambda pid: None)
    assert out == []


def test_enumerator_failure_is_survivable():
    def boom():
        raise OSError("no window station")

    assert _list(enumerator=boom) == []
