"""Column geometry, header alignment, and the link glyph.

These drive a REAL Tk widget: ttk.Treeview normalises and clamps what
column()/heading() are given, so asserting on the spec tuple alone would
test the tuple rather than the widget. The suite otherwise has no UI
tests, so the fixture skips rather than fails where no display exists
(CI runs ubuntu-latest with no X server); locally WSLg provides one.

Nothing here measures font metrics: this host's Tk has no Xft, so
tkfont.families() returns only "fixed" and linespace is meaningless.
Row height is therefore tested through the pure helper, and the visual
result is a smoke-checklist item.
"""
import tkinter as tk
from tkinter import ttk

import pytest

from obs_youtube_uploader import app


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - no display (CI)
        pytest.skip(f"Tk needs a display: {exc}")
    yield r
    r.destroy()


def _tree(root, dpi):
    """Build a configured Treeview at *dpi*, driving scaling the way
    __main__.main() does rather than monkeypatching dpi_scale."""
    root.tk.call("tk", "scaling", dpi / 72.0)
    scale = app.dpi_scale(root)
    tree = ttk.Treeview(
        root,
        columns=("filename", "date", "size", "duration", "link"),
        show="tree headings",
    )
    sorted_keys = []
    app.configure_tree_columns(tree, scale, sorted_keys.append)
    tree.pack(fill=tk.BOTH, expand=True)
    # winfo_*/column readback is zeros until the widget is realised.
    root.update()
    return tree, scale, sorted_keys


@pytest.mark.parametrize("dpi,expected_scale", [(96, 1.0), (144, 1.5)])
def test_columns_match_the_spec_at_every_scale(root, dpi, expected_scale):
    tree, scale, _ = _tree(root, dpi)
    assert scale == expected_scale
    for key, text, _sort_key, width, minwidth, stretch, anchor in app.COLUMN_SPEC:
        assert tree.column(key, "width") == int(width * scale), key
        assert tree.column(key, "minwidth") == int(minwidth * scale), key
        assert bool(tree.column(key, "stretch")) is stretch, key
        assert str(tree.column(key, "anchor")) == anchor, key


def test_every_heading_is_anchored_like_its_column(root):
    # The defect being fixed: centred headers over left/right-aligned data.
    tree, _, _ = _tree(root, 96)
    for key, _text, _sort_key, _w, _m, _s, anchor in app.COLUMN_SPEC:
        assert str(tree.heading(key, "anchor")) == anchor, key


def test_every_compressible_column_stretches():
    """A minwidth on a non-stretching column is unreachable.

    ttk.Treeview distributes a width deficit across its STRETCHING columns
    only, so `date`, `size` and `duration` must stretch for their minimums
    to mean anything at the window floor. `link` is exempt: it is a fixed
    glyph cell already sitting at its minimum, so it neither grows nor
    needs to shrink.
    """
    stretching = [c[0] for c in app.COLUMN_SPEC if c[5]]
    assert stretching == ["filename", "date", "size", "duration"]


def test_minimums_fit_the_pane_at_the_window_floor():
    # The preferred widths do not fit at the minimum window width; the
    # minimums are what make that case survive. That the minimums really do
    # fit is measured against a real window in
    # test_app_layout.test_no_column_is_clipped_at_the_minimum_window_size;
    # these two sums are the numbers that measurement was reasoned from.
    assert sum(c[3] for c in app.COLUMN_SPEC) == 620
    assert sum(c[4] for c in app.COLUMN_SPEC) == 410


def test_duration_header_reads_length_but_keeps_its_sort_key(root):
    # _sort_by dispatches on the column KEY, so renaming the header must
    # not rename the key.
    tree, _, sorted_keys = _tree(root, 96)
    assert str(tree.heading("duration", "text")) == "Length"
    root.tk.call(tree.heading("duration", "command"))
    assert sorted_keys == ["duration"]


def test_checkbox_header_still_sorts_by_checked(root):
    tree, _, sorted_keys = _tree(root, 96)
    root.tk.call(tree.heading("#0", "command"))
    assert sorted_keys == ["checked"]


def test_link_cell_is_a_glyph_not_a_url():
    assert app.link_cell("https://www.youtube.com/watch?v=abc") == app.LINK_GLYPH
    assert app.link_cell("") == ""
    assert app.link_cell(None) == ""


def test_link_cell_round_trips_through_a_real_row(root):
    tree, _, _ = _tree(root, 96)
    iid = tree.insert("", tk.END, values=("a.mkv", "Aug 20", "1 MB", "1:00",
                                          app.link_cell(None)))
    assert tree.set(iid, "link") == ""
    tree.set(iid, "link", app.link_cell("https://youtu.be/abc"))
    assert tree.set(iid, "link") == app.LINK_GLYPH


@pytest.mark.parametrize("checkbox,linespace,scale,expected", [
    (20, 10, 1.0, 28),   # the new comfort floor wins
    (40, 10, 1.0, 44),   # the checkbox guarantee still wins
    (10, 40, 1.0, 43),   # the line-box guarantee still wins
    (20, 10, 1.5, 42),   # the comfort floor scales with DPI
])
def test_row_height_keeps_both_old_guarantees_and_adds_a_floor(
        checkbox, linespace, scale, expected):
    assert app.row_height(checkbox, linespace, scale) == expected
