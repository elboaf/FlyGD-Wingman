"""Verify the WebView2 runtime before pywebview is allowed to try.

pywebview does not fail when the runtime is missing. It logs the exception,
returns from webview.start() normally, and the process exits 0 -- so a user
without the runtime gets no window, no error dialog, and a success exit
code. In a windowed build there is no console either, so even the logged
diagnostic is unreachable. Nothing downstream can detect this state, which
is why the check has to happen before webview is started rather than around
it.

The installer's Evergreen bootstrapper does not make this redundant: a
runtime can be uninstalled or broken after a successful install. The
installer's detection and this one are deliberately the same predicate over
the same three keys, and must stay that way.

Testable without a VM: point WEBVIEW2_BROWSER_EXECUTABLE_FOLDER at an empty
directory to reproduce the runtime-not-found path non-destructively.
"""
import logging
import sys

logger = logging.getLogger(__name__)

# EdgeUpdate's client id for the WebView2 Evergreen runtime. Also used by
# installer.iss -- if this constant changes, that one has to change with it.
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

# All three are real install shapes and any one of them means present:
# per-machine on 64-bit Windows (WOW6432Node -- EdgeUpdate is a 32-bit
# process, so its per-machine keys land under the redirect even on x64),
# per-machine on 32-bit Windows, and per-user. Checking only the first
# would refuse to start on a machine with a working per-user runtime.
REGISTRY_KEYS = (
    ("HKLM", rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    ("HKLM", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    ("HKCU", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
)

# EdgeUpdate zeroes pv rather than deleting the key when the runtime is
# removed, so a bare "the key exists" test reports a runtime that is gone.
_ABSENT_VERSIONS = {"", "0.0.0.0"}

DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"

MISSING_RUNTIME_TITLE = "Microsoft WebView2 Runtime required"


def missing_runtime_message() -> str:
    """The body of the only dialog this app can show before it has a window.

    Pure and module-level for the usual reason, but with an extra one here:
    it is the single piece of copy no automated UI check will ever reach,
    since displaying it requires a machine without the runtime.

    Names the product and gives the URL because "WebView2 initialization
    failed" is not something a user can act on, and this dialog is their
    only chance -- the alternative, today, is a program that appears to do
    nothing at all.
    """
    return (
        "FlyGD Wingman needs the Microsoft Edge WebView2 Evergreen Runtime, "
        "which is not installed on this computer.\n\n"
        "Install it from:\n"
        f"{DOWNLOAD_URL}\n\n"
        "Then start FlyGD Wingman again."
    )


def _read_pv(hive: str, subkey: str) -> str | None:
    """Read one EdgeUpdate client key's `pv` value, or None.

    None on any failure and off Windows, mirroring
    theme.read_apps_use_light_theme: an unreadable key means "no runtime
    recorded here", and the caller has two more keys to try. Raising would
    turn a permissions quirk into a crash before any window exists, which
    is the failure mode this whole module was written to remove.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        root = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
        key = winreg.OpenKey(root, subkey)
        try:
            value, _ = winreg.QueryValueEx(key, "pv")
        finally:
            winreg.CloseKey(key)
        return str(value)
    except Exception:
        return None


def webview2_version(reader=_read_pv) -> str | None:
    """The installed runtime version, or None if there is none.

    reader is injectable so the decision logic is tested off-Windows, the
    same convention as theme.detect_mode's reader= and library.discover's
    runner=.

    Scans all three keys rather than returning on the first hit's raw
    value, because a stale zeroed per-machine key can sit beside a live
    per-user install; stopping early would report absent on a machine where
    the runtime works.
    """
    for hive, subkey in REGISTRY_KEYS:
        try:
            value = reader(hive, subkey)
        except Exception:
            continue
        if value is None:
            continue
        value = value.strip()
        if value not in _ABSENT_VERSIONS:
            return value
    return None


def _message_box(title: str, body: str) -> None:
    """A native modal, because no webview exists to render an in-app one.

    MB_SETFOREGROUND|MB_TOPMOST are not decoration: this fires before any
    window is created, so the dialog has no owner and lands behind whatever
    the user was doing without them -- which would reproduce the very
    silence it is here to break.

    Off Windows this is a no-op so the suite runs on ubuntu-latest; the
    caller's decision does not depend on the dialog appearing.
    """
    if sys.platform != "win32":
        return
    import ctypes

    MB_OK = 0x0
    MB_ICONERROR = 0x10
    MB_SETFOREGROUND = 0x10000
    MB_TOPMOST = 0x40000
    ctypes.windll.user32.MessageBoxW(
        None, body, title, MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST)
    return


def require_webview2(version=webview2_version, alert=_message_box) -> bool:
    """True when it is safe to call webview.start(); False means exit non-zero.

    Returns rather than calls sys.exit so the caller keeps ordering control
    -- the tray icon may already be running by this point and needs
    stopping before the process ends.

    Logs as well as alerting: the dialog is for the user, the log line is
    for the support conversation afterwards, and Q7 proved neither exists
    by default.
    """
    found = version()
    if found is not None:
        logger.debug("WebView2 runtime %s detected", found)
        return True
    logger.error("WebView2 runtime not found; refusing to start a webview "
                 "that would silently render nothing")
    alert(MISSING_RUNTIME_TITLE, missing_runtime_message())
    return False
