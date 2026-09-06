"""One DWM thumbnail: register, position, release."""

import ctypes
import logging
from ctypes import wintypes

from . import win32

logger = logging.getLogger(__name__)


def _format_hresult(hr: int) -> str:
    """Format HRESULT as unsigned 8-digit hex string."""
    return f"0x{int(hr) & 0xFFFFFFFF:08x}"


class Thumbnail:
    def __init__(self, libs, handle, dest_hwnd, src_hwnd):
        self._libs = libs
        self._handle = handle
        self._dest_hwnd = int(dest_hwnd)
        self._src_hwnd = int(src_hwnd)

    @classmethod
    def register(cls, libs, dest_hwnd, src_hwnd):
        """Returns None on failure -- a client that vanished between the
        sweep and this call is routine, not exceptional."""
        handle = wintypes.HANDLE()
        hr = libs.dwmapi.DwmRegisterThumbnail(dest_hwnd, src_hwnd, ctypes.byref(handle))
        if hr != 0:
            logger.warning(
                "DwmRegisterThumbnail failed: hr=%s src=0x%x dest=0x%x",
                _format_hresult(hr),
                int(src_hwnd),
                int(dest_hwnd),
            )
            return None
        return cls(libs, handle, dest_hwnd, src_hwnd)

    def update(
        self, rect, opacity: int = 255, visible: bool = True, source_rect=None
    ) -> int | None:
        """Update thumbnail properties. Returns raw HRESULT, or None if closed."""
        if self._handle is None:
            return None
        props = win32.DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = (
            win32.DWM_TNP_RECTDESTINATION
            | win32.DWM_TNP_VISIBLE
            | win32.DWM_TNP_OPACITY
            | win32.DWM_TNP_SOURCECLIENTAREAONLY
        )
        # RECT is edges, not extents: right/bottom, never width/height.
        props.rcDestination = win32.RECT(rect.x, rect.y, rect.right, rect.bottom)
        if source_rect is not None:
            props.dwFlags |= win32.DWM_TNP_RECTSOURCE
            props.rcSource = win32.RECT(
                source_rect.x,
                source_rect.y,
                source_rect.right,
                source_rect.bottom,
            )
        props.opacity = opacity
        props.fVisible = visible
        props.fSourceClientAreaOnly = True
        hr = self._libs.dwmapi.DwmUpdateThumbnailProperties(
            self._handle, ctypes.byref(props)
        )
        if hr != 0:
            logger.warning(
                "DwmUpdateThumbnailProperties failed: hr=%s src=0x%x "
                "dest=0x%x destination=%s source=%s",
                _format_hresult(hr),
                self._src_hwnd,
                self._dest_hwnd,
                rect,
                source_rect,
            )
        return int(hr)

    def close(self) -> None:
        """Idempotent: a second unregister is a use-after-free in DWM's
        handle table, and it does not crash here."""
        if self._handle is None:
            return
        self._libs.dwmapi.DwmUnregisterThumbnail(self._handle)
        self._handle = None
