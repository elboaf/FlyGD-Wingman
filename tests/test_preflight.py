"""The WebView2 runtime pre-flight check.

Spike Q7 is the reason this module exists: with no runtime installed,
pywebview logs the initialization failure, returns from webview.start()
normally, and the process exits 0. A windowed build has no console, so the
user gets no window, no error, and a success exit code. Everything here is
about making that state loud.

Registry access and the native message box are injected, so the decision
logic is tested on ubuntu-latest with no Windows and no runtime present --
the same reader= convention theme.detect_mode uses.
"""

import sys

import pytest

from wingman.ui import preflight


def _reader(present: dict):
    """A fake _read_pv over a {(hive, subkey): pv} mapping."""
    return lambda hive, subkey: present.get((hive, subkey))


def test_all_three_documented_keys_are_checked():
    """Per-machine 64-bit, per-machine 32-bit, and per-user are three real
    install shapes; checking only the first would call a per-user install
    absent and refuse to start on a machine that works."""
    hives = {hive for hive, _ in preflight.REGISTRY_KEYS}
    assert hives == {"HKLM", "HKCU"}
    assert len(preflight.REGISTRY_KEYS) == 3
    for _, subkey in preflight.REGISTRY_KEYS:
        assert subkey.endswith(preflight.WEBVIEW2_GUID)


@pytest.mark.parametrize("key", list(range(3)))
def test_a_version_under_any_single_key_counts_as_present(key):
    hive, subkey = preflight.REGISTRY_KEYS[key]
    found = preflight.webview2_version(
        reader=_reader({(hive, subkey): "151.0.4129.93"})
    )
    assert found == "151.0.4129.93"


def test_no_key_at_all_reads_as_absent():
    assert preflight.webview2_version(reader=_reader({})) is None


def test_a_zeroed_version_reads_as_absent():
    """EdgeUpdate leaves pv=0.0.0.0 behind after an uninstall. Treating that
    as a version is how a stale registry key turns into a silent no-window
    launch -- exactly the failure the check exists to prevent."""
    present = {k: "0.0.0.0" for k in preflight.REGISTRY_KEYS}
    assert preflight.webview2_version(reader=_reader(present)) is None


def test_an_empty_version_reads_as_absent():
    present = {k: "" for k in preflight.REGISTRY_KEYS}
    assert preflight.webview2_version(reader=_reader(present)) is None
    present = {k: "   " for k in preflight.REGISTRY_KEYS}
    assert preflight.webview2_version(reader=_reader(present)) is None


def test_a_usable_key_wins_over_an_emptied_one():
    """A machine can carry a stale zeroed per-machine key beside a live
    per-user install. Order of the scan must not decide the verdict."""
    stale = preflight.REGISTRY_KEYS[0]
    live = preflight.REGISTRY_KEYS[2]
    found = preflight.webview2_version(
        reader=_reader({stale: "0.0.0.0", live: "151.0.4129.93"})
    )
    assert found == "151.0.4129.93"


def test_a_reader_that_raises_does_not_take_down_startup():
    """Injected here, but the real reader wraps winreg, which raises for a
    dozen unremarkable reasons. An unreadable key means "not found here",
    never "crash before the window exists"."""

    def boom(hive, subkey):
        raise OSError("access denied")

    assert preflight.webview2_version(reader=boom) is None


def test_present_runtime_proceeds_without_alerting():
    alerts = []
    ok = preflight.require_webview2(
        version=lambda: "151.0.4129.93",
        alert=lambda title, body: alerts.append((title, body)),
    )
    assert ok is True
    assert alerts == []


def test_absent_runtime_alerts_and_refuses_to_proceed():
    alerts = []
    ok = preflight.require_webview2(
        version=lambda: None, alert=lambda title, body: alerts.append((title, body))
    )
    assert ok is False
    assert len(alerts) == 1


def test_the_alert_names_the_runtime_and_where_to_get_it():
    """The user cannot act on "WebView2 failed". They can act on a product
    name and a URL, which is the entire content of this dialog."""
    body = preflight.missing_runtime_message()
    assert "WebView2" in body
    assert "Evergreen" in body
    assert preflight.DOWNLOAD_URL in body


def test_the_alert_title_says_what_is_missing():
    assert "WebView2" in preflight.MISSING_RUNTIME_TITLE


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="off-Windows degradation; on Windows it really reads the registry",
)
def test_the_real_reader_degrades_rather_than_raising_off_windows():
    for hive, subkey in preflight.REGISTRY_KEYS:
        assert preflight._read_pv(hive, subkey) is None


@pytest.mark.skipif(
    sys.platform == "win32", reason="would pop a real modal dialog and hang the suite"
)
def test_the_real_message_box_is_a_no_op_off_windows():
    """ctypes.windll does not exist off Windows. This must degrade, not
    raise: the suite runs on ubuntu-latest."""
    assert preflight._message_box("title", "body") is None
