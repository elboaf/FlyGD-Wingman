"""Conservative foreign-window catalog. Every source operation here is read-only.

Foreign captions use Windows' cached text; own-process captions can synchronously
send WM_GETTEXT, so PID exclusion MUST precede the title read. No process cache,
WMI, message fallback, or process-memory access belongs on the preview pump.
"""

import ctypes
import ntpath
from ctypes import wintypes

from . import win32
from .companions import (
    EXECUTABLE_PATH_MAX_CHARS,
    MAX_SOURCES,
    TITLE_MAX_CHARS,
    WINDOW_CLASS_MAX_CHARS,
    SourceBinding,
)


class SourceUnavailable(RuntimeError):
    """An incomplete scan is not an empty (or uniquely matching) catalog."""


def _text(value, bound):
    if not value.strip() or len(value) > bound or not value.isprintable():
        raise ValueError("Source text is empty, too long, or contains controls")
    return value


class SourceCatalog:
    def __init__(self, libs, own_pid: int):
        self._libs = libs
        self._own_pid = own_pid
        self._handles = set()

    def close(self) -> bool:
        for handle in tuple(self._handles):
            if self._libs.kernel32.CloseHandle(handle):
                self._handles.remove(handle)
        return not self._handles

    def _pid(self, hwnd):
        pid = wintypes.DWORD()
        if not self._libs.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise OSError("Source PID unavailable")
        return pid.value

    def _process(self, pid):
        kernel = self._libs.kernel32
        handle = kernel.OpenProcess(win32.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            raise OSError("Source process inaccessible")
        self._handles.add(handle)
        try:
            buffer = ctypes.create_unicode_buffer(EXECUTABLE_PATH_MAX_CHARS + 1)
            length = wintypes.DWORD(len(buffer))
            if not kernel.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(length)
            ):
                raise OSError("Source executable unavailable")
            path = _text(buffer.value, EXECUTABLE_PATH_MAX_CHARS)
            drive, tail = ntpath.splitdrive(path)
            if not drive or not tail.startswith(("\\", "/")):
                raise ValueError("Full executable path required")
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise OSError("Source creation time unavailable")
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            if not created:
                raise ValueError("Source creation time unavailable")
            return ntpath.normcase(ntpath.normpath(path)), created
        finally:
            if kernel.CloseHandle(handle):
                self._handles.remove(handle)
            else:
                # Keep the real owner, and do not leak one new handle per scan.
                raise SourceUnavailable("Source process handle cleanup incomplete")

    def _class(self, hwnd):
        buffer = ctypes.create_unicode_buffer(WINDOW_CLASS_MAX_CHARS + 2)
        if not self._libs.user32.GetClassNameW(hwnd, buffer, len(buffer)):
            raise OSError("Source class unavailable")
        return _text(buffer.value, WINDOW_CLASS_MAX_CHARS)

    def _inspect(self, hwnd):
        try:
            user = self._libs.user32
            pid = self._pid(hwnd)
            if not pid or pid == self._own_pid or not user.IsWindowVisible(hwnd):
                return None
            path, created = self._process(pid)
            if ntpath.basename(path) in (
                "exefile.exe",
                "eve.exe",
                "eve-online.exe",
                "wingman.exe",
                "obsyoutubeuploader.exe",
                "applicationframehost.exe",
            ):
                return None
            window_class = self._class(hwnd)
            if window_class.casefold().startswith("wingman") or window_class in (
                "ApplicationFrameWindow",
                "Windows.UI.Core.CoreWindow",
            ):
                return None
            cloaked = wintypes.DWORD()
            if (
                self._libs.dwmapi.DwmGetWindowAttribute(
                    hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                )
                != 0
            ):
                return None  # Cloaking is mandatory; affinity is optional.
            if cloaked.value or user.IsHungAppWindow(hwnd):
                return None
            affinity = wintypes.DWORD()
            if (
                user.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity))
                and affinity.value
            ):
                return None
            rect = win32.RECT()
            if not user.GetClientRect(hwnd, ctypes.byref(rect)):
                return None
            size = rect.right - rect.left, rect.bottom - rect.top
            if min(size) <= 0 or self._pid(hwnd) != pid:
                return None
            title = ctypes.create_unicode_buffer(TITLE_MAX_CHARS + 2)
            if not user.GetWindowTextW(hwnd, title, len(title)):
                return None
            caption = _text(title.value, TITLE_MAX_CHARS)
            # Do not assemble a binding from two different HWND/process lives.
            if (
                self._pid(hwnd) != pid
                or self._process(pid) != (path, created)
                or self._class(hwnd) != window_class
            ):
                return None
            return SourceBinding(hwnd, pid, created, path, window_class, caption, size)
        except (OSError, ValueError):
            return None  # Vanishing/inaccessible foreign windows are routine.

    def enumerate(self) -> tuple[SourceBinding, ...]:
        if self._handles and not self.close():
            raise SourceUnavailable("Source process cleanup is still pending")
        handles = []

        def visit(hwnd, unused):
            # Hidden IME/tool/helper windows are not source candidates. Counting
            # them made ordinary desktop churn exhaust the inspection budget.
            if self._libs.user32.IsWindowVisible(hwnd):
                handles.append(int(hwnd))
            return len(handles) <= MAX_SOURCES

        callback = win32.enum_windows_proc_type()(visit)
        complete = self._libs.user32.EnumWindows(callback, 0)
        if len(handles) > MAX_SOURCES:
            raise SourceUnavailable("Too many visible windows to list sources safely")
        if not complete:
            raise SourceUnavailable(
                "Windows could not complete the source scan. Try again."
            )
        return tuple(
            binding for hwnd in handles if (binding := self._inspect(hwnd)) is not None
        )

    def verify(self, binding: SourceBinding) -> SourceBinding | None:
        if self._handles and not self.close():
            raise SourceUnavailable("Source process cleanup is still pending")
        fresh = self._inspect(binding.hwnd)
        if fresh is None:
            return None
        identity = ("hwnd", "pid", "process_created", "executable_path", "window_class")
        return (
            fresh
            if all(getattr(fresh, k) == getattr(binding, k) for k in identity)
            else None
        )
