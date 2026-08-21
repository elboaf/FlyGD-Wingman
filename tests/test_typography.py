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


def test_both_heading_styles_use_their_own_font(root):
    app.apply_typography(root)
    style = ttk.Style(root)
    assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == \
        app.COLUMN_HEADING_FONT
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
        assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == \
            app.COLUMN_HEADING_FONT
        assert style.lookup(app.SECTION_HEADING_STYLE, "font") == app.HEADING_FONT
        assert style.lookup(app.MUTED_STYLE, "foreground") == \
            theme.TOKENS[mode]["MUTED"]


def test_heading_font_tracks_the_dpi_rescaled_sv_font(root):
    """theme.apply rescales sv-ttk's fonts BEFORE consumers run, so the
    copy taken here is derived from the corrected size -- not the 96-DPI one
    sv.tcl declared. Compared against the source font rather than an
    absolute number, so this says nothing about metrics."""
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    strong = int(_font_option(root, "SunValleyBodyStrongFont", "-size"))
    assert int(_font_option(root, app.HEADING_FONT, "-size")) == \
        app.scaled_font_size(strong, app.SECTION_RATIO)


def test_apply_typography_is_idempotent(root):
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    first = _font_option(root, app.HEADING_FONT, "-size")
    for _ in range(3):
        theme.apply(root, "dark")
    assert _font_option(root, app.HEADING_FONT, "-size") == first


# --- the type scale --------------------------------------------------------

def test_positive_sizes_are_points_and_scale_upward():
    assert app.scaled_font_size(10, 1.2) == 12


def test_negative_sizes_are_pixels_and_keep_their_sign():
    """Tk reads a negative -size as pixels. Scaling the magnitude and
    dropping the sign would silently reinterpret the unit and produce a
    font an order of magnitude wrong."""
    assert app.scaled_font_size(-20, 1.2) == -24


def test_scaling_down_never_collapses_to_zero_or_flips_sign():
    for base in (1, 2, 3, -1, -2, -3):
        out = app.scaled_font_size(base, 0.875)
        assert out != 0
        assert (out > 0) == (base > 0)


def test_a_zero_or_unreadable_base_is_left_alone():
    """font configure can hand back 0 for a font that has not resolved yet;
    inventing a size from it would be worse than inheriting."""
    assert app.scaled_font_size(0, 1.2) == 0


def test_the_three_steps_are_distinct_and_ordered(root):
    """Hierarchy needs a real ratio between steps. Everything in this app
    used to render at one size, so nothing guided the eye down a 132-row
    list."""
    root.tk.call("tk", "scaling", 144 / 72.0)
    theme.register(lambda mode: app.apply_typography(root))
    theme.apply(root, "dark")
    section = abs(int(_font_option(root, app.HEADING_FONT, "-size")))
    column = abs(int(_font_option(root, app.COLUMN_HEADING_FONT, "-size")))
    small = abs(int(_font_option(root, app.SMALL_FONT, "-size")))
    body = abs(int(_font_option(root, "SunValleyBodyFont", "-size")))
    assert section > body > small
    assert column == small


def test_section_and_column_headings_are_both_bold(root):
    app.apply_typography(root)
    assert _font_option(root, app.HEADING_FONT, "-weight") == "bold"
    assert _font_option(root, app.COLUMN_HEADING_FONT, "-weight") == "bold"


def test_the_tree_heading_no_longer_shares_the_section_font(root):
    """Column headers label the data; they must not outrank it. They now sit
    one step BELOW body, where the section heading sits one step above."""
    app.apply_typography(root)
    style = ttk.Style(root)
    assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == \
        app.COLUMN_HEADING_FONT
    assert style.lookup(app.SECTION_HEADING_STYLE, "font") == app.HEADING_FONT


def test_muted_style_carries_the_small_font(root):
    app.apply_typography(root)
    assert ttk.Style(root).lookup(app.MUTED_STYLE, "font") == app.SMALL_FONT


def test_the_whole_scale_survives_a_theme_switch(root):
    theme.register(lambda mode: app.apply_typography(root))
    for mode in ("dark", "light"):
        theme.apply(root, mode)
        style = ttk.Style(root)
        assert style.lookup(f"{app.TREE_STYLE}.Heading", "font") == \
            app.COLUMN_HEADING_FONT
        assert style.lookup(app.MUTED_STYLE, "font") == app.SMALL_FONT
