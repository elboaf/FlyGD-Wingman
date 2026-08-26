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

from ..paths import bundle_dir
from . import geometry

logger = logging.getLogger(__name__)


def _font_path() -> Path:
    """Locate the bundled Inter face, mirroring paths.icon_file()'s two cases.

    uploader.spec collects the fonts folder at the bundle root (destination
    "assets/fonts"), so bundle_dir() / "assets" / "fonts" is the frozen
    location. A source checkout has no such collection step, so bundle_dir()
    (the repo root) is wrong there; the real file lives under this package's
    own assets/ folder -- one level up from preview/.
    """
    frozen_candidate = bundle_dir() / "assets" / "fonts" / "Inter-Regular.ttf"
    if frozen_candidate.exists():
        return frozen_candidate
    return (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "fonts"
        / "Inter-Regular.ttf"
    )


FONT_PATH = _font_path()
LABEL_BG = (10, 14, 20, 235)
LABEL_FG = (235, 240, 245, 255)
# Opaque, and that is load-bearing rather than cosmetic. A layered window
# hit-tests against its own alpha channel: every pixel at alpha 0 passes
# mouse input through to whatever is behind it. An earlier version left
# the interior fully transparent -- so the thumbnail was visible (DWM
# composites it OVER the window and contributes nothing to its alpha) but
# clicks went to the window behind, and only the border and label band
# were clickable.
#
# This colour is still what shows in the inset around an unselected
# preview, which is why it stays opaque here. Under the thumbnail it is
# replaced by THUMBNAIL_ALPHA; see _punch_thumbnail_hole.
INTERIOR_BG = (8, 10, 14, 255)
# 1, not 0, and not 255. Three facts, all measured on Windows with a red
# backdrop behind a preview whose thumbnail was set to DWM opacity 128:
#
#   interior alpha 255 -> sampled (4, 5, 135): the thumbnail blends with
#     THIS fill, so lowering preview.opacity walked the game content
#     toward near-black and the backdrop never appeared. That is the
#     "opacity just dims it" bug, and it was in the fill, not in DWM.
#   interior alpha 1   -> sampled (126, 0, 128): a clean 50/50 of game
#     content over the backdrop, and WindowFromPoint still returned the
#     preview.
#   interior alpha 0   -> pixel-identical to 1, and WindowFromPoint
#     returned the window behind: click-through.
#
# So alpha 1 is the only value that is both see-through and clickable.
# docs/preview-roadmap.md used to claim any bitmap alpha reintroduces
# click-through; that holds at 0 only, and believing it of every value is
# what kept this fix off the table.
THUMBNAIL_ALPHA = 1


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
        logger.warning(
            "Bundled font missing at %s; labels will use Pillow's "
            "default face. In a frozen build this means "
            "uploader.spec did not collect assets/fonts.",
            FONT_PATH,
        )
        return ImageFont.load_default()


def _ellipsize(draw, text, font, max_w):
    if not text or draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell


def _punch_thumbnail_hole(d, w, h, border, label_h) -> None:
    """Clear the rect the DWM thumbnail is drawn into to THUMBNAIL_ALPHA.

    Derived from geometry.thumbnail_rect, the same function window.py
    hands to DwmUpdateThumbnailProperties, so the hole and the thumbnail
    cannot drift apart. A mismatch would show as a near-black seam the
    thumbnail does not cover.

    Degenerate sizes fall out here rather than at the call site: a
    preview dragged smaller than its own chrome clamps to a zero-area
    rect, and Pillow would draw a 1px line for it.
    """
    thumb = geometry.thumbnail_rect(geometry.Rect(0, 0, w, h), border, label_h)
    if thumb.w <= 0 or thumb.h <= 0:
        return
    d.rectangle(
        [thumb.x, thumb.y, thumb.right - 1, thumb.bottom - 1],
        fill=(*INTERIOR_BG[:3], THUMBNAIL_ALPHA),
    )


def render(
    size, label, *, border_color, border=5, label_h=30, selected=False, font_size=17
):
    """Render one preview's chrome.

    Every pixel is clickable and none is fully transparent, which is not
    the same thing as opaque: a layered window is hit-tested against its
    alpha channel, and only alpha 0 passes the click through. Chrome
    proper stays solid; the region the DWM thumbnail will cover is
    dropped to THUMBNAIL_ALPHA so that preview.opacity blends the game
    content against the desktop instead of against this bitmap.

    `border` must be the same inset the caller gives the thumbnail --
    BORDER normally, ALERT_BORDER while an alert is armed. Both call
    sites (window.redraw and alertframes.build) already pass exactly
    that, and the hole is derived from it rather than restated.
    """
    w, h = max(1, size[0]), max(1, size[1])
    img = Image.new("RGBA", (w, h), INTERIOR_BG)
    d = ImageDraw.Draw(img)
    # Before the ring and band, so chrome always paints over the hole
    # rather than being eaten by it -- an alert ring is wider than the
    # inset it is drawn at, and the band's last row abuts the hole.
    _punch_thumbnail_hole(d, w, h, border, label_h)

    # Only the selected preview carries a ring. An unselected one shows the
    # interior fill at the inset width instead -- near-black, which reads as
    # nothing over a dark desktop and as a thin dark edge over bright game
    # content. That is the intended look; see the design's Outcome section.
    if selected:
        d.rectangle([0, 0, w - 1, h - 1], outline=border_color, width=border)

    # -1 because Pillow's rectangle is inclusive: without it the band's
    # last row lands on the thumbnail's first one. That overlap was
    # invisible while the thumbnail covered an opaque fill, and shows as
    # a 1px dark seam across the top of a translucent preview.
    band_bottom = min(h - 1, border + label_h - 1)
    if band_bottom > border:
        d.rectangle([border, border, w - border - 1, band_bottom], fill=LABEL_BG)
        font = _font(font_size)
        text = _ellipsize(d, label, font, max_w=w - border * 2 - 12)
        if text:
            d.text((border + 6, border + 4), text, font=font, fill=LABEL_FG)
    return img
