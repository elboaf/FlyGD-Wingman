"""Chrome rendering is pure: numbers in, RGBA image out.

Testing pixels directly is the point of moving off GDI+ -- these run in
CI on Linux, where no Windows drawing API exists.
"""

from pathlib import Path

from obs_youtube_uploader.preview import chrome

CYAN = (0, 200, 220, 255)


def test_border_is_drawn_in_the_requested_colour():
    img = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert img.getpixel((0, 0)) == CYAN
    assert img.getpixel((319, 209)) == CYAN


def test_every_pixel_is_opaque_so_the_window_is_clickable():
    """A layered window hit-tests against its ALPHA CHANNEL: any pixel at
    alpha 0 passes the click through to whatever is behind it.

    An earlier version left the interior transparent, reasoning that the
    DWM thumbnail composites over it anyway. It does -- visually. But the
    thumbnail contributes nothing to the window's alpha, so the preview
    looked right and was click-through everywhere except its 5px border
    and label band, and clicks landed in the browser behind it.
    """
    img = chrome.render((320, 210), "Pilot", border_color=CYAN)
    alphas = {px[3] for px in img.get_flattened_data()}
    assert 0 not in alphas, "transparent pixels are click-through"


def test_a_degenerate_size_is_still_fully_opaque():
    """Resize passes through tiny sizes; a transparent frame there would
    briefly make the preview unclickable mid-drag."""
    img = chrome.render((6, 6), "P", border_color=CYAN)
    assert 0 not in {px[3] for px in img.get_flattened_data()}


def test_label_band_is_opaque_and_the_right_height():
    img = chrome.render((320, 210), "Pilot", border_color=CYAN, border=5, label_h=30)
    assert img.getpixel((160, 6))[3] > 200  # inside the band
    # Below the band is the thumbnail area: opaque (see the hit-testing
    # test above) but a different colour from the band.
    assert img.getpixel((160, 40))[3] == 255
    assert img.getpixel((160, 40))[:3] != img.getpixel((160, 6))[:3]


def test_label_text_is_actually_drawn():
    blank = chrome.render((320, 210), "", border_color=CYAN)
    named = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert blank.tobytes() != named.tobytes()


def test_long_labels_do_not_overflow_the_band():
    """A 40-character character name must not paint over the thumbnail."""
    img = chrome.render((320, 210), "X" * 60, border_color=CYAN, border=5, label_h=30)
    band = chrome.render((320, 210), "", border_color=CYAN, border=5, label_h=30)
    # Below the band must be untouched interior, identical to the
    # unlabelled render.
    assert img.getpixel((160, 40)) == band.getpixel((160, 40))


def test_selected_draws_a_thicker_border():
    plain = chrome.render((320, 210), "P", border_color=CYAN, border=5)
    picked = chrome.render((320, 210), "P", border_color=CYAN, border=5, selected=True)
    assert plain.tobytes() != picked.tobytes()


def test_degenerate_size_does_not_raise():
    """Resize can transiently produce a rect smaller than the chrome."""
    chrome.render((4, 4), "P", border_color=CYAN)


def test_font_path_prefers_the_frozen_location(monkeypatch, tmp_path):
    """uploader.spec collects the fonts folder at destination "assets/fonts",
    which lands it at bundle_dir() / "assets" / "fonts" in a frozen build --
    NOT bundle_dir() / "obs_youtube_uploader" / "assets" / "fonts". A bare
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
        chrome.render((320, 210), "Pilot", border_color=CYAN)
    chrome._font.cache_clear()
    assert any("font" in r.message.lower() for r in caplog.records)
