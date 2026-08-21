"""Bold headings, the muted style, and surviving a live theme switch.

No assertion here touches font metrics: this host's Tk has no Xft, so
linespace and measure() are meaningless. What IS checkable is the font's
CONFIGURATION (weight, size) and which style points at it, which is
exactly where this can regress.

The switch test is the point of the file. ttk stores style options per
THEME, and sv_ttk.set_theme() swaps the whole theme, so anything
configured before a switch is gone after it -- the same hazard
_apply_row_height's docstring describes.
"""
import tkinter as tk
from tkinter import ttk

import pytest

from obs_youtube_uploader import app, theme


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display (CI)
        pytest.skip(f"Tk needs a display: {exc}")
    yield r
    r.destroy()


@pytest.fixture(autouse=True)
def _clear_consumers():
    """theme._consumers is module-level; mirrors tests/test_theme.py."""
    saved = list(theme._consumers)
    theme._consumers.clear()
    yield
    theme._consumers.clear()
    theme._consumers.extend(saved)


def _font_option(root, name, option):
    return str(root.tk.call("font", "configure", name, option))


def test_heading_font_is_bold(root):
    app.apply_typography(root)
    assert _font_option(root, app.HEADING_FONT, "-weight") == "bold"


def test_both_heading_styles_use_that_font(root):
    app.apply_typography(root)
    style = ttk.Style(root)
    assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == app.HEADING_FONT
    assert style.lookup(app.SECTION_HEADING_STYLE, "font") == app.HEADING_FONT


def test_muted_style_follows_the_active_mode(root, monkeypatch):
    for mode in ("light", "dark"):
        monkeypatch.setattr(theme, "_current_mode", mode)
        app.apply_typography(root)
        assert ttk.Style(root).lookup(app.MUTED_STYLE, "foreground") == \
            theme.TOKENS[mode]["MUTED"]


def test_a_treeview_can_actually_wear_the_named_style(root):
    """The named style has no layout of its own; ttk must fall back to
    Treeview's. If that fallback ever stopped working the widget would
    fail to render rather than merely look wrong."""
    app.apply_typography(root)
    tree = ttk.Treeview(root, columns=("filename",), show="tree headings",
                        style=app.TREE_STYLE)
    tree.heading("filename", text="Filename")
    tree.pack(fill=tk.BOTH, expand=True)
    root.update()  # geometry is zeros until realised
    assert tree.winfo_width() > 1


def test_a_theme_switch_wipes_the_styles_without_a_re_assert(root):
    # Documents the hazard the wiring exists for. If this ever stops
    # failing, the re-assert below is no longer load-bearing.
    app.apply_typography(root)
    theme.apply(root, "dark")
    assert ttk.Style(root).lookup(f"{app.TREE_STYLE}.Heading", "font") \
        != app.HEADING_FONT


def test_registered_consumer_restores_the_styles_after_a_switch(root):
    # How UploaderWindow wires it: apply_typography runs from the ONE
    # registered consumer, so it lands after sv_ttk.set_theme has
    # rewritten the theme's styles.
    theme.register(lambda mode: app.apply_typography(root))
    for mode in ("dark", "light"):
        theme.apply(root, mode)
        style = ttk.Style(root)
        assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == app.HEADING_FONT
        assert style.lookup(app.SECTION_HEADING_STYLE, "font") == app.HEADING_FONT
        assert style.lookup(app.MUTED_STYLE, "foreground") == \
            theme.TOKENS[mode]["MUTED"]


def test_heading_font_tracks_the_dpi_rescaled_sv_font(root):
    """theme.apply rescales sv-ttk's fonts BEFORE consumers run, so the
    copy taken here is the corrected size -- not the 96-DPI one sv.tcl
    declared. Compared against the source font rather than an absolute
    number, so this says nothing about metrics."""
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    strong = _font_option(root, "SunValleyBodyStrongFont", "-size")
    assert _font_option(root, app.HEADING_FONT, "-size") == strong


def test_apply_typography_is_idempotent(root):
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    first = _font_option(root, app.HEADING_FONT, "-size")
    for _ in range(3):
        theme.apply(root, "dark")
    assert _font_option(root, app.HEADING_FONT, "-size") == first
