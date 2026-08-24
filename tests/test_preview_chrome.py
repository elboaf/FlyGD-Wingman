"""Chrome rendering is pure: numbers in, RGBA image out.

Testing pixels directly is the point of moving off GDI+ -- these run in
CI on Linux, where no Windows drawing API exists.
"""
from obs_youtube_uploader.preview import chrome

CYAN = (0, 200, 220, 255)


def test_border_is_drawn_in_the_requested_colour():
    img = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert img.getpixel((0, 0)) == CYAN
    assert img.getpixel((319, 209)) == CYAN


def test_interior_below_the_label_is_transparent_for_the_thumbnail():
    """The DWM thumbnail composites over this area. Leaving it opaque is
    harmless today but hides mistakes if the thumbnail fails to register --
    a transparent hole makes that failure visible instead of silent."""
    img = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert img.getpixel((160, 120))[3] == 0


def test_label_band_is_opaque_and_the_right_height():
    img = chrome.render((320, 210), "Pilot", border_color=CYAN,
                        border=5, label_h=30)
    assert img.getpixel((160, 6))[3] > 200      # inside the band
    assert img.getpixel((160, 40))[3] == 0      # below it


def test_label_text_is_actually_drawn():
    blank = chrome.render((320, 210), "", border_color=CYAN)
    named = chrome.render((320, 210), "Pilot", border_color=CYAN)
    assert blank.tobytes() != named.tobytes()


def test_long_labels_do_not_overflow_the_band():
    """A 40-character character name must not paint over the thumbnail."""
    img = chrome.render((320, 210), "X" * 60, border_color=CYAN,
                        border=5, label_h=30)
    assert img.getpixel((160, 40))[3] == 0


def test_selected_draws_a_thicker_border():
    plain = chrome.render((320, 210), "P", border_color=CYAN, border=5)
    picked = chrome.render((320, 210), "P", border_color=CYAN, border=5,
                           selected=True)
    assert plain.tobytes() != picked.tobytes()


def test_degenerate_size_does_not_raise():
    """Resize can transiently produce a rect smaller than the chrome."""
    chrome.render((4, 4), "P", border_color=CYAN)


def test_missing_font_is_logged_not_swallowed(monkeypatch, caplog):
    """The realistic cause is a frozen build that did not collect the font
    (uploader.spec's datas is enumerated by hand and PyInstaller exits 0
    when an entry misses). A silent fallback ships unlabelled previews
    with nothing in the log to explain them."""
    import pathlib
    chrome._font.cache_clear()
    monkeypatch.setattr(chrome, "FONT_PATH", pathlib.Path("/nonexistent.ttf"))
    with caplog.at_level("WARNING"):
        chrome.render((320, 210), "Pilot", border_color=CYAN)
    chrome._font.cache_clear()
    assert any("font" in r.message.lower() for r in caplog.records)
