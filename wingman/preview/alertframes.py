"""Pre-rendered alert ring frames.

The flash must never go through PreviewWindow.redraw(): that method is
cache-keyed and a pulse defeats the key, putting a full Pillow render plus
a ~67k-pixel push on an 80ms timer -- "the cost that made dragging
stutter" (eve-preview-design.md:468-471).

So the frames are rendered once on arm, each into its own DIB with one
shared memory DC, and the tick does SelectObject plus UpdateLayeredWindow.
Cleanup is ordered the way layered.push documents at layered.py:63-67:
restore the DC's original object before deleting ours, or the DIBs leak
for the life of the process.

Pulsing the alpha with SetLayeredWindowAttributes was the alternative and
is not available: probed 2026-08-25, it dims the chrome and the game
thumbnail together and then fails every subsequent UpdateLayeredWindow
with ERROR_INVALID_PARAMETER, recoverable only by dropping and re-adding
WS_EX_LAYERED. docs/preview-roadmap.md carries the measurements.

Imports cleanly on Linux, like every other module here: no WinDLL or
windll at module scope, and the library handles arrive as `libs`.
"""

import ctypes
import logging

from ..alerts import state
from . import chrome, layered, win32

logger = logging.getLogger(__name__)

# The ring is drawn at the outer edge and the DWM thumbnail overpaints
# everything it covers, so a ring wider than the thumbnail's inset is
# clipped to the inset on the sides and bottom -- measured at 6px ring /
# 2px inset giving 2px there and 6px only on the top edge and beside the
# label band. The window widens its inset to match for the duration of an
# alert; see PreviewWindow._set_inset.
ALERT_BORDER = 6

# Above this area the cache falls back to a two-frame blink. Six frames at
# 320x210 is ~1.6MB; at 1920x1080 it is ~50MB, held for as long as an
# unacknowledged persistent alert lasts -- and a fleet-wide aggression
# arms every preview at once.
BLINK_AREA = 640 * 480


def frame_count(size) -> int:
    return 6 if size[0] * size[1] <= BLINK_AREA else 2


def alphas_for(size) -> tuple:
    n = frame_count(size)
    if n == len(state.FRAME_ALPHAS):
        return state.FRAME_ALPHAS
    return (state.FRAME_ALPHAS[0], state.FRAME_ALPHAS[-1])


def frame_for(index: int, count: int) -> int:
    """Map a phase index onto a cache that may hold fewer frames.

    `state.frame_index` is pure and knows nothing about this module: it
    always returns an index into the six-entry FRAME_ALPHAS. Passing that
    straight to a two-frame cache is an IndexError on the large previews
    that are exactly the ones the fallback exists for, and it would only
    fire on Windows with a preview over BLINK_AREA armed -- so it is
    mapped here and tested on Linux instead.
    """
    if count >= len(state.FRAME_ALPHAS):
        return index
    return min(count - 1, index * count // len(state.FRAME_ALPHAS))


def _with_alpha(color: str, alpha: int) -> tuple:
    """`#rrggbb` plus an alpha byte. Falls back to the combat default.

    settings.validated_alerts already refuses anything that is not
    #rrggbb, so a bad value here means a spec that did not come from
    settings -- a test double, or a future caller. Logged rather than
    raised: a malformed colour must not take down the preview thread.
    """
    raw = (color or "").lstrip("#")
    try:
        r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        logger.warning("Unusable alert colour %r; falling back", color)
        r, g, b = 0xFF, 0x4D, 0x4D
    return (r, g, b, alpha)


class FrameCache:
    """One DC, N DIBs, one bitmap per pulse phase.

    Windows only. Every method must run on the preview thread, like
    everything else that touches this window's HWND.
    """

    def __init__(self, size, colour):
        self.size = size
        self.colour = colour
        self._dc = None
        self._old = None
        self._dibs = []

    @classmethod
    def build(cls, libs, size, colour):
        """Render every phase once.

        Every frame is rendered `selected=True` -- an alert draws its ring
        whether or not the client is the selected one, which is the whole
        point of alerting on a preview you are not looking at.
        """
        self = cls(size, colour)
        w, h = size
        bmi = win32.BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(win32.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # negative == top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        screen_dc = libs.user32.GetDC(None)
        self._dc = libs.gdi32.CreateCompatibleDC(screen_dc)
        try:
            for alpha in alphas_for(size):
                img = chrome.render(
                    size,
                    border_color=_with_alpha(colour, alpha),
                    border=ALERT_BORDER,
                    selected=True,
                )
                data = layered.to_premultiplied_bgra(img)
                bits = ctypes.c_void_p()
                dib = libs.gdi32.CreateDIBSection(
                    self._dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0
                )
                if not dib:
                    logger.warning("CreateDIBSection failed; alert will not draw")
                    self.close(libs)
                    return None
                ctypes.memmove(bits, data, len(data))
                self._dibs.append(dib)
        finally:
            libs.user32.ReleaseDC(None, screen_dc)
        return self

    def push(self, libs, hwnd, rect, index: int) -> bool:
        """Blit one phase. Cheap by construction: SelectObject plus
        UpdateLayeredWindow, no Pillow render and no DIB allocation."""
        if not self._dibs:
            return False
        try:
            dib = self._dibs[frame_for(index, len(self._dibs))]
            old = libs.gdi32.SelectObject(self._dc, dib)
            if self._old is None:
                # The DC's original bitmap, kept for the ordered teardown.
                # Captured on the first select rather than at build time,
                # which is the only moment it is knowable.
                self._old = old
            w, h = self.size
            blend = win32.BLENDFUNCTION(win32.AC_SRC_OVER, 0, 255, win32.AC_SRC_ALPHA)
            screen_dc = libs.user32.GetDC(None)
            try:
                return bool(
                    libs.user32.UpdateLayeredWindow(
                        hwnd,
                        screen_dc,
                        ctypes.byref(win32.POINT(rect.x, rect.y)),
                        ctypes.byref(win32.SIZE(w, h)),
                        self._dc,
                        ctypes.byref(win32.POINT(0, 0)),
                        0,
                        ctypes.byref(blend),
                        win32.ULW_ALPHA,
                    )
                )
            finally:
                libs.user32.ReleaseDC(None, screen_dc)
        except Exception:
            # Caught broadly on purpose (no noqa needed -- logger.exception
            # satisfies BLE001). This runs on the preview thread's 80ms
            # timer, inside the WndProc. An exception escaping there takes
            # the pump down, and the pump is previews AND the
            # RegisterHotKey loop. A failed frame is a missed flash; a dead
            # pump is a dead subsystem.
            logger.exception("Alert frame push failed")
            return False

    def close(self, libs) -> None:
        """Ordered exactly as layered.push documents: restore the DC's
        original object before deleting ours, or the DIBs leak for the
        life of the process."""
        if self._dc:
            if self._old is not None:
                libs.gdi32.SelectObject(self._dc, self._old)
                self._old = None
            for dib in self._dibs:
                libs.gdi32.DeleteObject(dib)
            libs.gdi32.DeleteDC(self._dc)
            self._dc = None
        self._dibs = []
