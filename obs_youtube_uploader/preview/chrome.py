"""Preview chrome, rendered with Pillow.

Pure by construction: it takes sizes and colours and returns an RGBA
image. Nothing here knows about HWNDs, which is what lets the whole
drawing layer be tested on Linux -- the reason this replaces TriffView's
GDI+ path rather than porting it.
"""
import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Inter-Regular.ttf"
LABEL_BG = (10, 14, 20, 235)
LABEL_FG = (235, 240, 245, 255)


@lru_cache(maxsize=8)
def _font(size: int):
    """Cached: a drag re-renders chrome on every move, and reopening the
    face each time shows up as stutter."""
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        # Degrade rather than take the subsystem down -- but LOUDLY. The
        # realistic cause is a frozen build that did not collect the font
        # (uploader.spec's datas is enumerated by hand and PyInstaller exits
        # 0 when an entry misses), and a silent fallback there ships
        # unlabelled previews with nothing in the log to explain them.
        logger.warning("Bundled font missing at %s; labels will use Pillow's "
                       "default face. In a frozen build this means "
                       "uploader.spec did not collect assets/fonts.",
                       FONT_PATH)
        return ImageFont.load_default()


def _ellipsize(draw, text, font, max_w):
    if not text or draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell


def render(size, label, *, border_color, border=5, label_h=30,
           selected=False, font_size=17):
    """Render one preview's chrome. Interior is left transparent."""
    w, h = max(1, size[0]), max(1, size[1])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    width = border * 2 if selected else border
    d.rectangle([0, 0, w - 1, h - 1], outline=border_color, width=width)

    band_bottom = min(h - 1, border + label_h)
    if band_bottom > border:
        d.rectangle([border, border, w - border - 1, band_bottom], fill=LABEL_BG)
        font = _font(font_size)
        text = _ellipsize(d, label, font, max_w=w - border * 2 - 12)
        if text:
            d.text((border + 6, border + 4), text, font=font, fill=LABEL_FG)
    return img
