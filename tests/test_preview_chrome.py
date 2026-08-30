"""Chrome rendering is pure: numbers in, RGBA image out.

Testing pixels directly is the point of moving off GDI+ -- these run in
CI on Linux, where no Windows drawing API exists.
"""

from pathlib import Path

from wingman.preview import chrome, geometry

CYAN = (0, 200, 220, 255)


def test_border_is_drawn_in_the_requested_colour():
    """Only when selected -- the ring is now conditional; see the
    selected/unselected tests below."""
    img = chrome.render((320, 210), border_color=CYAN, selected=True)
    assert img.getpixel((0, 0)) == CYAN
    assert img.getpixel((319, 209)) == CYAN


def test_no_pixel_is_fully_transparent_so_the_window_is_clickable():
    """A layered window hit-tests against its ALPHA CHANNEL: any pixel at
    alpha 0 passes the click through to whatever is behind it.

    An earlier version left the interior transparent, reasoning that the
    DWM thumbnail composites over it anyway. It does -- visually. But the
    thumbnail contributes nothing to the window's alpha, so the preview
    looked right and was click-through everywhere except its 5px border
    and label band, and clicks landed in the browser behind it.
    """
    img = chrome.render((320, 210), border_color=CYAN)
    alphas = {px[3] for px in img.get_flattened_data()}
    assert 0 not in alphas, "transparent pixels are click-through"


def test_a_degenerate_size_is_still_clickable():
    """Resize passes through tiny sizes; a transparent frame there would
    briefly make the preview unclickable mid-drag."""
    img = chrome.render((6, 6), border_color=CYAN)
    assert 0 not in {px[3] for px in img.get_flattened_data()}


def test_the_label_pill_fits_its_text_and_holds_the_band_palette():
    """The overlay pill replaces the band: sized to the text, in the band's
    colours, rounded, transparent outside the pill so the video shows
    around it.

    The palette is asserted at (2, mid-height): on the pill's straight
    left edge inside the corner radius, which is padding by construction.
    The centre pixel is NOT safe for this -- whether it lands on a glyph
    stroke or between glyphs depends on the platform's FreeType metrics
    (observed: same font, same Pillow, different pixel on ubuntu)."""
    img = chrome.render_label("Pilot", 300)
    assert img is not None
    assert 20 < img.width < 300  # fitted to the text, not the preview
    assert 18 < img.height < 40
    edge = img.getpixel((2, img.height // 2))
    assert edge[3] > 200  # opaque band, readable over bright video
    assert edge[:3] == chrome.LABEL_BG[:3]


def test_long_labels_ellipsize_against_the_preview_width():
    """The overlay must never be wider than its preview."""
    img = chrome.render_label("X" * 60, 120)
    assert img is not None
    assert img.width <= 120


def test_an_empty_label_renders_no_window():
    """A client with no readable name gets no pill -- an empty rounded
    rectangle floating over the video would be pure noise."""
    assert chrome.render_label("", 300) is None
    assert chrome.render_label(None, 300) is None


def test_an_unselected_preview_draws_no_ring():
    """The alert ring is then the only coloured ring on screen, which is
    what makes it legible on a small tile."""
    img = chrome.render(
        (200, 150), border_color=(0, 200, 220, 255), border=2, selected=False
    )
    assert img.getpixel((0, 100))[:3] != (0, 200, 220)


def test_the_selected_preview_draws_its_ring():
    img = chrome.render(
        (200, 150), border_color=(0, 200, 220, 255), border=2, selected=True
    )
    assert img.getpixel((0, 100))[:3] == (0, 200, 220)


def test_the_interior_stays_clickable_either_way():
    """Hit-testing is load-bearing, not cosmetic: a layered window is
    hit-tested against its own alpha, so a FULLY transparent pixel is
    click-through and drag breaks.

    This used to assert alpha 255 and read that as the same thing. It is
    not: only alpha 0 is click-through, and requiring 255 here is what
    made preview.opacity dim the game content instead of revealing the
    desktop behind it. See THUMBNAIL_ALPHA in chrome.py for the
    measurements.
    """
    for selected in (True, False):
        img = chrome.render(
            (200, 150),
            border_color=(0, 200, 220, 255),
            border=2,
            selected=selected,
        )
        assert img.getpixel((100, 100))[3] > 0


def test_degenerate_size_does_not_raise():
    """Resize can transiently produce a rect smaller than the chrome."""
    chrome.render((4, 4), border_color=CYAN)


def test_font_path_prefers_the_frozen_location(monkeypatch, tmp_path):
    """uploader.spec collects the fonts folder at destination "assets/fonts",
    which lands it at bundle_dir() / "assets" / "fonts" in a frozen build --
    NOT bundle_dir() / "wingman" / "assets" / "fonts". A bare
    Path(__file__) resolution disagreed with the spec by one path segment
    and silently fell back to Pillow's default face in every shipped build."""

    frozen_fonts = tmp_path / "assets" / "fonts"
    frozen_fonts.mkdir(parents=True)
    font_file = frozen_fonts / "Inter-Regular.ttf"
    font_file.write_bytes(b"")
    monkeypatch.setattr(chrome, "bundle_dir", lambda: tmp_path)

    assert chrome._font_path() == font_file


def test_font_path_falls_back_to_the_source_checkout_copy(monkeypatch, tmp_path):
    """When bundle_dir() (a frozen build, or the repo root in a source
    checkout) has no collected assets/fonts, the real source-tree location
    beside this package is used instead -- the case every test and dev run
    exercises."""

    monkeypatch.setattr(chrome, "bundle_dir", lambda: tmp_path)

    assert chrome._font_path() == (
        Path(chrome.__file__).resolve().parent.parent
        / "assets"
        / "fonts"
        / "Inter-Regular.ttf"
    )


def test_missing_font_is_logged_not_swallowed(monkeypatch, caplog):
    """The realistic cause is a frozen build that did not collect the font
    (uploader.spec's datas is enumerated by hand and PyInstaller exits 0
    when an entry misses). A silent fallback ships unlabelled previews
    with nothing in the log to explain them."""
    chrome._font.cache_clear()
    monkeypatch.setattr(chrome, "FONT_PATH", Path("/nonexistent.ttf"))
    with caplog.at_level("WARNING"):
        # render_label, not render: the name moved to the overlay pill,
        # and chrome.render no longer loads a font at all.
        chrome.render_label("Pilot", 300)
    chrome._font.cache_clear()
    assert any("font" in r.message.lower() for r in caplog.records)


# -- the thumbnail hole -------------------------------------------------
# DWM composites the thumbnail OVER this bitmap, so whatever alpha sits
# under it is what preview.opacity blends the game content against.
# Measured on Windows: an opaque fill there means a translucent preview
# blends toward near-black -- it dims, and the desktop never shows
# through, which is what users reported the opacity slider doing.


def test_the_thumbnail_region_is_transparent_so_opacity_reveals_the_desktop():
    img = chrome.render((320, 210), border_color=CYAN, border=2)
    assert img.getpixel((160, 105))[3] == chrome.THUMBNAIL_ALPHA
    assert chrome.THUMBNAIL_ALPHA < 255, "an opaque fill dims instead of revealing"


def test_the_thumbnail_region_is_still_hit_testable():
    """Alpha 1 rather than 0, and the difference is the whole design.

    Measured: WindowFromPoint over an alpha-1 pixel returns the preview,
    over an alpha-0 pixel it returns the window behind. Zero would give
    the same translucency and make the tile click-through -- the exact
    regression chrome's opaque fill was introduced to fix.
    """
    assert chrome.THUMBNAIL_ALPHA > 0


def test_the_thumbnail_hole_matches_the_rect_the_thumbnail_is_drawn_into():
    """Derived from geometry, never retyped: the hole and the DWM
    destination rect must be the same rectangle, or the seam shows as a
    ring of near-black the thumbnail does not cover."""
    w, h, border = 320, 210, 2
    img = chrome.render((w, h), border_color=CYAN, border=border)
    thumb = geometry.thumbnail_rect(geometry.Rect(0, 0, w, h), border)
    for x, y in (
        (thumb.x, thumb.y),
        (thumb.right - 1, thumb.bottom - 1),
    ):
        assert img.getpixel((x, y))[3] == chrome.THUMBNAIL_ALPHA, (x, y)
    # Just outside every edge is chrome, and chrome stays solid.
    assert img.getpixel((thumb.x - 1, thumb.y))[3] == 255
    assert img.getpixel((thumb.right, thumb.y))[3] == 255
    assert img.getpixel((thumb.x, thumb.bottom))[3] == 255


def test_the_unselected_edge_stays_opaque():
    """An unselected preview shows the interior fill at the inset width
    instead of a ring. Punching the thumbnail hole must not take that
    edge with it -- it is the only thing separating two stacked previews
    when neither is selected."""
    img = chrome.render((320, 210), border_color=CYAN, border=2)
    assert img.getpixel((0, 0))[3] == 255
    assert img.getpixel((1, 1))[3] == 255
    assert img.getpixel((319, 209))[3] == 255


def test_the_alert_ring_is_drawn_over_the_hole_not_under_it():
    """Alert frames render at ALERT_BORDER, and window.py widens the
    thumbnail inset to match. The ring must survive the punch or an armed
    alert draws nothing."""
    img = chrome.render((320, 210), border_color=CYAN, border=6, selected=True)
    assert img.getpixel((160, 3)) == CYAN
