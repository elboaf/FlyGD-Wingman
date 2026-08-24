"""Push a Pillow image onto a layered window.

Split deliberately: the byte conversion is pure and tested in CI, the
UpdateLayeredWindow call is thin enough to leave to the smoke checklist.
"""
import ctypes

from PIL import Image

from . import win32


def to_premultiplied_bgra(img) -> bytes:
    """Premultiplied BGRA bytes, top-down, as ULW_ALPHA requires.

    Pillow's raw encoder mode "BGRa" (lowercase a) emits premultiplied
    output directly, which avoids a per-pixel Python loop over ~67k pixels
    per repaint. Verified byte-exact on Pillow 12.3.0; the tests pin the
    values so a future release that changes the encoder fails here rather
    than shipping subtly glowing previews.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.tobytes("raw", "BGRa")


def push(libs, hwnd, img, x, y) -> bool:
    """Blit *img* onto the layered window at absolute (x, y)."""
    w, h = img.size
    data = to_premultiplied_bgra(img)

    bmi = win32.BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(win32.BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h        # negative == top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0    # BI_RGB

    screen_dc = libs.user32.GetDC(None)
    mem_dc = libs.gdi32.CreateCompatibleDC(screen_dc)
    bits = ctypes.c_void_p()
    dib = libs.gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0,
                                      ctypes.byref(bits), None, 0)
    old = libs.gdi32.SelectObject(mem_dc, dib)
    try:
        ctypes.memmove(bits, data, len(data))
        blend = win32.BLENDFUNCTION(win32.AC_SRC_OVER, 0, 255,
                                    win32.AC_SRC_ALPHA)
        return bool(libs.user32.UpdateLayeredWindow(
            hwnd, screen_dc, ctypes.byref(win32.POINT(x, y)),
            ctypes.byref(win32.SIZE(w, h)), mem_dc,
            ctypes.byref(win32.POINT(0, 0)), 0,
            ctypes.byref(blend), win32.ULW_ALPHA))
    finally:
        # Ordered: restore the DC's original object before deleting ours,
        # or the DIB leaks for the life of the process.
        libs.gdi32.SelectObject(mem_dc, old)
        libs.gdi32.DeleteObject(dib)
        libs.gdi32.DeleteDC(mem_dc)
        libs.user32.ReleaseDC(None, screen_dc)
