"""One DWM thumbnail: register, position, release."""
import ctypes
import logging
from ctypes import wintypes

from . import win32

logger = logging.getLogger(__name__)


class Thumbnail:
    def __init__(self, libs, handle):
        self._libs, self._handle = libs, handle

    @classmethod
    def register(cls, libs, dest_hwnd, src_hwnd):
        """Returns None on failure -- a client that vanished between the
        sweep and this call is routine, not exceptional."""
        handle = wintypes.HANDLE()
        hr = libs.dwmapi.DwmRegisterThumbnail(dest_hwnd, src_hwnd,
                                              ctypes.byref(handle))
        if hr != 0:
            logger.warning("DwmRegisterThumbnail failed: hr=0x%08x src=0x%x",
                           hr & 0xFFFFFFFF, src_hwnd)
            return None
        return cls(libs, handle)

    def update(self, rect, opacity: int = 255, visible: bool = True) -> None:
        if self._handle is None:
            return
        props = win32.DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = (win32.DWM_TNP_RECTDESTINATION | win32.DWM_TNP_VISIBLE
                         | win32.DWM_TNP_OPACITY
                         | win32.DWM_TNP_SOURCECLIENTAREAONLY)
        # RECT is edges, not extents: right/bottom, never width/height.
        props.rcDestination = win32.RECT(rect.x, rect.y,
                                         rect.right, rect.bottom)
        props.opacity = opacity
        props.fVisible = visible
        props.fSourceClientAreaOnly = True
        self._libs.dwmapi.DwmUpdateThumbnailProperties(self._handle,
                                                       ctypes.byref(props))

    def close(self) -> None:
        """Idempotent: a second unregister is a use-after-free in DWM's
        handle table, and it does not crash here."""
        if self._handle is None:
            return
        self._libs.dwmapi.DwmUnregisterThumbnail(self._handle)
        self._handle = None
