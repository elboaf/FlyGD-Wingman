"""Client discovery. Every collaborator is injected so identity and
filtering logic is testable off Windows."""

import pytest

from wingman.preview import discovery

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


def test_image_name_failure_is_skipped_by_default_but_strict_propagates():
    def image_name(pid):
        raise OSError("process disappeared")

    assert _list(image_name=image_name) == []
    with pytest.raises(OSError, match="process disappeared"):
        _list(image_name=image_name, strict=True)


def test_enumerator_failure_is_survivable():
    def boom():
        raise OSError("no window station")

    assert _list(enumerator=boom) == []


def test_strict_discovery_propagates_an_enumerator_failure():
    def boom():
        raise OSError("no window station")

    with pytest.raises(OSError, match="no window station"):
        _list(enumerator=boom, strict=True)


def test_window_inspection_failure_is_skipped_by_default_but_strict_propagates():
    def pids(hwnd):
        if hwnd == 0x10:
            raise OSError("window disappeared")
        return PIDS.get(hwnd)

    assert [client.character for client in _list(pids=pids)] == ["Pilot Two"]
    with pytest.raises(OSError, match="window disappeared"):
        _list(pids=pids, strict=True)


def test_strict_discovery_still_skips_an_inaccessible_process():
    assert _list(image_name=lambda pid: None, strict=True) == []


# ---------------------------------------------------------------------------
# enumerate_clients(): the failure-aware seam ClientDiscovery consumes
# ---------------------------------------------------------------------------


def test_enumerate_clients_reports_success_with_the_same_clients_as_list_clients():
    result = discovery.enumerate_clients(
        enumerator=lambda: WINDOWS, pids=PIDS.get, image_name=IMAGES.get
    )
    assert result.success is True
    assert [c.character for c in result.clients] == ["Pilot One", "Pilot Two"]


def test_enumerate_clients_reports_success_on_a_genuinely_empty_scan():
    result = discovery.enumerate_clients(enumerator=list)
    assert result.success is True
    assert result.clients == []


def test_enumerate_clients_reports_failure_on_enumerator_exception():
    def boom():
        raise OSError("no window station")

    result = discovery.enumerate_clients(enumerator=boom)
    assert result.success is False
    assert result.clients == []


def test_enumerate_clients_strict_still_propagates_an_enumerator_failure():
    def boom():
        raise OSError("no window station")

    with pytest.raises(OSError, match="no window station"):
        discovery.enumerate_clients(enumerator=boom, strict=True)


def test_enumerate_clients_per_window_failure_is_not_an_enumeration_failure():
    """A per-window pids()/image_name() failure only drops that window --
    the top-level enumerator succeeded, so this is not the kind of
    failure ClientDiscovery must treat as "the scan itself failed"."""

    def pids(hwnd):
        if hwnd == 0x10:
            raise OSError("window disappeared")
        return PIDS.get(hwnd)

    result = discovery.enumerate_clients(
        enumerator=lambda: WINDOWS, pids=pids, image_name=IMAGES.get
    )
    assert result.success is True
    assert [c.character for c in result.clients] == ["Pilot Two"]


def test_list_clients_is_the_clients_of_enumerate_clients():
    """list_clients() remains a thin compatibility adapter: same clients
    on success, and the same empty-list collapse on failure it always had."""

    def boom():
        raise OSError("no window station")

    assert discovery.list_clients(enumerator=lambda: WINDOWS) == list(
        discovery.enumerate_clients(enumerator=lambda: WINDOWS).clients
    )
    assert discovery.list_clients(enumerator=boom) == []
