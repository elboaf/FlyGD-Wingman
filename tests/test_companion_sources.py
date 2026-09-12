"""Read-only source identity over OS doubles; no foreign window is launched."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from wingman.preview import win32


class SourceOS:
    def __init__(self):
        self.windows = {10: dict(pid=20, title="Mapper", cls="Browser", visible=True)}
        self.path = r"C:\Tools\browser.exe"
        self.created = 42
        self.size = (1280, 720)
        self.calls = []
        self.opened = set()
        self.fail = None
        self.cloaked = self.affinity = 0
        self.hung = False
        self.libs = SimpleNamespace(user32=self, kernel32=self, dwmapi=self)

    def EnumWindows(self, callback, unused):
        for hwnd in self.windows:
            if not callback(hwnd, unused):
                return False
        return self.fail != "enumerate"

    def GetWindowThreadProcessId(self, hwnd, pointer):
        pointer._obj.value = self.windows[hwnd]["pid"]
        return 7

    def IsWindowVisible(self, hwnd):
        return self.windows[hwnd]["visible"]

    def IsHungAppWindow(self, hwnd):
        return self.hung

    def GetWindowTextW(self, hwnd, buffer, length):
        self.calls.append(("title", hwnd))
        assert self.windows[hwnd]["pid"] != 99, "Own PID read can send WM_GETTEXT"
        buffer.value = self.windows[hwnd]["title"][: length - 1]
        return len(buffer.value)

    def GetClassNameW(self, hwnd, buffer, length):
        buffer.value = self.windows[hwnd]["cls"][: length - 1]
        return len(buffer.value)

    def GetClientRect(self, hwnd, pointer):
        pointer._obj.right, pointer._obj.bottom = self.size
        return True

    def DwmGetWindowAttribute(self, hwnd, attribute, pointer, size):
        assert attribute == 14
        pointer._obj.value = self.cloaked
        return 1 if self.fail == "cloak" else 0

    def GetWindowDisplayAffinity(self, hwnd, pointer):
        pointer._obj.value = self.affinity
        return self.fail != "affinity"

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x1000 and not inherit
        self.calls.append(("open", pid))
        if self.fail == "open":
            return 0
        self.opened.add(pid)
        return pid

    def QueryFullProcessImageNameW(self, handle, flags, buffer, length):
        buffer.value = self.path
        return self.fail != "path"

    def GetProcessTimes(self, handle, created, exited, kernel, user):
        created._obj.dwLowDateTime = self.created
        return self.fail != "times"

    def CloseHandle(self, handle):
        self.calls.append(("close", handle))
        if self.fail == "close":
            return False
        self.opened.remove(handle)
        return True


@pytest.fixture
def catalog(monkeypatch):
    from wingman.preview.sources import SourceCatalog

    monkeypatch.setattr(win32, "enum_windows_proc_type", lambda: lambda fn: fn)
    native = SourceOS()
    return SourceCatalog(native.libs, 99), native


def test_limited_query_handles_closed_and_own_pid_rejected_before_title(catalog):
    source, native = catalog
    native.windows[11] = dict(pid=99, title="Our page", cls="WebView", visible=True)
    rows = source.enumerate()
    assert len(rows) == 1 and rows[0].hwnd == 10
    assert rows[0].process_created == 42 and rows[0].client_size == (1280, 720)
    assert not native.opened
    assert ("title", 11) not in native.calls


@pytest.mark.parametrize("failure", ["path", "times", "open", "cloak"])
def test_unverifiable_source_is_omitted_and_query_handle_closed(catalog, failure):
    source, native = catalog
    native.fail = failure
    assert source.enumerate() == ()
    assert not native.opened


@pytest.mark.parametrize(
    "path",
    [
        r"C:\EVE\exefile.exe",
        r"C:\EVE\eve.exe",
        r"C:\EVE\eve-online.exe",
        r"C:\Wingman\wingman.exe",
        r"C:\Old\OBSYouTubeUploader.exe",
        r"C:\Windows\ApplicationFrameHost.exe",
    ],
)
def test_eve_login_wingman_and_unverifiable_frame_sources_refused(catalog, path):
    source, native = catalog
    native.path = path
    assert source.enumerate() == ()


@pytest.mark.parametrize("title", ["", " ", "bad\ncaption", "x" * 513])
def test_invalid_caption_refused(catalog, title):
    source, native = catalog
    native.windows[10]["title"] = title
    assert source.enumerate() == ()


def test_foreign_python_is_not_itself_wingman_and_optional_affinity_failure_allowed(
    catalog,
):
    source, native = catalog
    native.path = r"C:\Python\python.exe"
    native.fail = "affinity"
    assert len(source.enumerate()) == 1
    native.windows[10]["cls"] = "WingmanCompanionPreview"
    assert source.enumerate() == ()


@pytest.mark.parametrize("field", ["hung", "cloaked", "affinity"])
def test_known_uncapturable_source_is_refused(catalog, field):
    source, native = catalog
    setattr(native, field, 1)
    assert source.enumerate() == ()


def test_hidden_helper_windows_do_not_exhaust_source_scan(catalog):
    from wingman.preview.companions import MAX_SOURCES

    source, native = catalog
    candidate = native.windows[10]
    # Hidden IME/tool/helper HWNDs can outnumber the actual desktop windows.
    native.windows = {
        i: dict(pid=30, title="Hidden helper", cls="IME", visible=False)
        for i in range(1000, 1000 + MAX_SOURCES + 1)
    }
    native.windows[10] = candidate
    rows = source.enumerate()
    assert len(rows) == 1 and rows[0].hwnd == 10
    assert not native.opened
    assert [(kind, value) for kind, value in native.calls if kind == "open"] == [
        ("open", 20),
        ("open", 20),
    ]


def test_incomplete_scan_never_becomes_unique_result(catalog):
    from wingman.preview.sources import SourceUnavailable

    source, native = catalog
    native.fail = "enumerate"
    with pytest.raises(SourceUnavailable, match="Windows could not complete"):
        source.enumerate()
    native.fail = None
    native.windows = {
        i: dict(pid=20, title="Mapper", cls="Browser", visible=True) for i in range(513)
    }
    with pytest.raises(SourceUnavailable, match="Too many visible windows"):
        source.enumerate()
    # The rejected prefix must never reach process inspection or become unique.
    assert not native.calls


def test_verification_retains_changed_title_but_rejects_reused_identity(catalog):
    source, native = catalog
    binding = source.enumerate()[0]
    native.windows[10]["title"] = "Mapper — new document"
    native.size = (1600, 900)
    assert source.verify(binding) == replace(
        binding, title="Mapper — new document", client_size=(1600, 900)
    )
    native.created += 1
    assert source.verify(binding) is None


def test_failed_handle_cleanup_is_retained_and_scan_refused(catalog):
    from wingman.preview.sources import SourceUnavailable

    source, native = catalog
    native.fail = "close"
    with pytest.raises(SourceUnavailable):
        source.enumerate()
    assert native.opened
    native.fail = None
    assert source.close()
    assert not native.opened
