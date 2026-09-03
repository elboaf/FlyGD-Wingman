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


# Probe tests: fail-closed EVE client state detection
@pytest.mark.parametrize(
    ("windows", "pid", "image", "expected"),
    [
        ([], 7, "exefile.exe", discovery.EveClientState.CLOSED),
        ([(1, "Browser")], 7, None, discovery.EveClientState.CLOSED),
        ([(1, "EVE - Alice")], 7, "exefile.exe", discovery.EveClientState.RUNNING),
        ([(1, "EVE - Alice")], 7, "chrome.exe", discovery.EveClientState.CLOSED),
        ([(1, "EVE - Alice")], 0, "exefile.exe", discovery.EveClientState.UNKNOWN),
        ([(1, "EVE - Alice")], 7, None, discovery.EveClientState.UNKNOWN),
    ],
)
def test_profile_probe_states(windows, pid, image, expected):
    """Probe returns tri-state: CLOSED, RUNNING, or UNKNOWN."""
    result = discovery.probe_eve_client_state(
        enumerator=lambda: windows,
        pids=lambda _hwnd: pid,
        image_name=lambda _pid: image,
    )
    assert result.state is expected


def test_probe_reports_a_zero_pid_as_a_collected_error():
    """A zero PID is a failed lookup, not an absent client.

    The state alone cannot tell the two synthesised failures apart from a
    caught exception, and _eve_profile_copy_refusal logs probe.errors as the
    only account of WHY it refused a whole-profile write. An empty errors
    tuple beside an UNKNOWN state would leave that refusal unexplainable."""
    result = discovery.probe_eve_client_state(
        enumerator=lambda: [(0x10, "EVE - Alice")],
        pids=lambda _hwnd: 0,
        image_name=lambda _pid: "exefile.exe",
    )
    assert result.state is discovery.EveClientState.UNKNOWN
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], OSError)
    assert "0x10" in str(result.errors[0])


def test_probe_reports_an_unresolvable_image_as_a_collected_error():
    """None from image_name means the process could not be opened.

    list_clients reads that as "owned by another user, not a client" and
    skips it; the probe must instead name it, for the same reason as the
    zero-PID case above."""
    result = discovery.probe_eve_client_state(
        enumerator=lambda: [(0x10, "EVE - Alice")],
        pids=lambda _hwnd: 7,
        image_name=lambda _pid: None,
    )
    assert result.state is discovery.EveClientState.UNKNOWN
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], OSError)
    assert "7" in str(result.errors[0])


def test_probe_enumerator_exception_is_collected():
    """Enumerator exception collects as an error; probe returns UNKNOWN."""

    def boom():
        raise OSError("no window station")

    result = discovery.probe_eve_client_state(
        enumerator=boom,
        pids=lambda _hwnd: 7,
        image_name=lambda _pid: "exefile.exe",
    )
    assert result.state is discovery.EveClientState.UNKNOWN
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], OSError)


def test_probe_pid_exception_is_collected():
    """PID lookup exception collects as an error; with EVE window, returns UNKNOWN."""

    def boom(_hwnd):
        raise OSError("process disappeared")

    result = discovery.probe_eve_client_state(
        enumerator=lambda: [(1, "EVE - Alice")],
        pids=boom,
        image_name=lambda _pid: "exefile.exe",
    )
    assert result.state is discovery.EveClientState.UNKNOWN
    assert len(result.errors) == 1


def test_probe_image_exception_is_collected():
    """Image lookup exception collects as an error; with EVE window, returns UNKNOWN."""

    def boom(_pid):
        raise OSError("access denied")

    result = discovery.probe_eve_client_state(
        enumerator=lambda: [(1, "EVE - Alice")],
        pids=lambda _hwnd: 7,
        image_name=boom,
    )
    assert result.state is discovery.EveClientState.UNKNOWN
    assert len(result.errors) == 1


def test_probe_mixed_known_and_unresolved_returns_unknown():
    """UNKNOWN dominates: if any candidate has errors, probe returns UNKNOWN."""

    def pids(hwnd):
        if hwnd == 1:
            return 7
        raise OSError("process disappeared")

    result = discovery.probe_eve_client_state(
        enumerator=lambda: [(1, "EVE - Alice"), (2, "EVE - Bob")],
        pids=pids,
        image_name=lambda _pid: "exefile.exe",
    )
    assert result.state is discovery.EveClientState.UNKNOWN
    assert len(result.errors) > 0


def test_probe_does_not_widen_the_title_net_to_non_eve_windows():
    """Only EVE-titled windows are probed at all.

    An unresolvable window that is not EVE's is not doubt about EVE, and
    collecting it would make every machine with one locked-down process
    permanently UNKNOWN -- a refusal the user could never clear."""
    result = discovery.probe_eve_client_state(
        enumerator=lambda: [(0x20, "Firefox")],
        pids=lambda _hwnd: 0,
        image_name=lambda _pid: None,
    )
    assert result.state is discovery.EveClientState.CLOSED
    assert result.errors == ()
