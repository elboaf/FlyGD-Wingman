"""Clicking anywhere on a row toggles it, not just the checkbox cell.

Real clicks at real coordinates: every test here finds its target with
tree.bbox(iid, column) and generates <Button-1> there, so it exercises the
same identify_region()/identify_row() path a user's mouse does. Asserting
_toggle_row() directly would pass no matter which regions are bound, which
is the entire behaviour under test.
"""
from pathlib import Path

# Tk decides <Double-Button-1> from the gap between presses, and it keeps
# that state across widgets and tests. event_generate() with no `time`
# stamps every press with the same clock tick, so two ordinary clicks in a
# row would silently arrive as a double-click and the test would exercise a
# path it never meant to. Every press here therefore carries an explicit,
# advancing timestamp: 1000ms apart reads as two singles, 50ms apart reads
# as a double. Measured on this host — 400ms was still ambiguous.
_SINGLE_GAP = 1000
_DOUBLE_GAP = 50
_clock = [500_000]


def _click(tree, iid, column, gap=_SINGLE_GAP):
    """Press <Button-1> at the centre of one cell, `gap` ms after the last."""
    tree.update()
    box = tree.bbox(iid, column)
    assert box, f"{column} has no bbox — the row is not visible"
    x, y, w, h = box
    cx, cy = x + w // 2, y + h // 2
    _clock[0] += gap
    tree.event_generate("<Button-1>", x=cx, y=cy, time=_clock[0])
    tree.update()
    return cx, cy


def _double_click(tree, iid, column):
    """Two presses close enough together that Tk raises <Double-Button-1>."""
    _click(tree, iid, column)
    _click(tree, iid, column, gap=_DOUBLE_GAP)


def _state(window, iid):
    """The two things that must never drift apart: the var and the image.

    The image comes back as Tk's own name for it, so compare against the
    name of the PhotoImage the window would draw, not the object.
    """
    var = window.selected[Path(iid)]
    drawn = window.tree.item(iid, "image")
    return var.get(), (str(drawn[0]) if drawn else "")


def _image_name(window, checked):
    return str(window._checkbox_image(checked))


def test_clicking_a_data_cell_toggles_the_row(make_window):
    window = make_window()
    iid = window.tree.get_children("")[0]
    assert _state(window, iid)[0] is False

    _click(window.tree, iid, "filename")

    checked, image = _state(window, iid)
    assert checked is True
    assert image == _image_name(window, True)


def test_clicking_a_data_cell_again_untoggles_it(make_window):
    """Toggle semantics, not select-and-replace."""
    window = make_window()
    iid = window.tree.get_children("")[0]

    _click(window.tree, iid, "date")
    _click(window.tree, iid, "date")  # a full second later: two singles

    checked, image = _state(window, iid)
    assert checked is False
    assert image == _image_name(window, False)


def test_every_data_column_is_a_click_target(make_window):
    """Including `link`: the ↗ glyph cell toggles like any other cell."""
    window = make_window()
    iid = window.tree.get_children("")[0]

    for column in ("filename", "date", "size", "duration", "link"):
        before = _state(window, iid)[0]
        _click(window.tree, iid, column)
        assert _state(window, iid)[0] is not before, f"{column} did not toggle"


def test_the_checkbox_cell_still_toggles(make_window):
    """The original click target must not regress."""
    window = make_window()
    iid = window.tree.get_children("")[0]

    _click(window.tree, iid, "#0")

    assert _state(window, iid)[0] is True


def test_clicking_one_row_leaves_the_others_alone(make_window):
    """Multi-select: rows accumulate, a click never clears the rest."""
    window = make_window()
    first, second = window.tree.get_children("")[:2]

    _click(window.tree, first, "filename")
    _click(window.tree, second, "filename")

    assert _state(window, first)[0] is True
    assert _state(window, second)[0] is True


def test_clicking_below_the_last_row_toggles_nothing(make_window):
    """Empty space under the rows has no iid; it must not raise or toggle."""
    window = make_window()
    tree = window.tree
    rows = tree.get_children("")
    tree.update()
    last = tree.bbox(rows[-1], "filename")
    before = [_state(window, iid)[0] for iid in rows]

    _clock[0] += _SINGLE_GAP
    tree.event_generate("<Button-1>", x=last[0] + 5, y=last[1] + last[3] + 40,
                        time=_clock[0])
    tree.update()

    assert [_state(window, iid)[0] for iid in rows] == before


def test_the_selection_summary_follows_a_row_click(make_window):
    """The click path must go through _toggle_row, which owns the summary."""
    window = make_window()
    iid = window.tree.get_children("")[0]
    assert "Nothing selected" in window.selection_summary.cget("text")

    _click(window.tree, iid, "filename")

    assert "1 selected" in window.selection_summary.cget("text")


def test_double_clicking_a_data_cell_opens_the_link_and_nets_zero_toggles(
        make_window, monkeypatch):
    """Opening a video must not leave the row selected.

    Measured, because the code used to claim otherwise: Tk delivers exactly
    ONE <Button-1> before <Double-Button-1> — the second press dispatches
    to the more specific binding instead of firing <Button-1> again. So one
    toggle lands and _on_row_double_click undoes it. If Tk ever changed to
    deliver two, this test would catch the double-undo.
    """
    window = make_window()
    iid = window.tree.get_children("")[0]
    window.links[Path(iid)] = "https://youtu.be/abc123"
    opened = []
    monkeypatch.setattr("obs_youtube_uploader.app.webbrowser.open", opened.append)

    # Two real presses close together: Tk raises <Double-Button-1> itself.
    # event_generate refuses an explicit Double modifier, and synthesising
    # one would test a dispatch path the mouse never takes.
    _double_click(window.tree, iid, "filename")

    assert opened == ["https://youtu.be/abc123"]
    assert _state(window, iid)[0] is False


def test_double_clicking_the_checkbox_cell_also_opens_the_link(make_window,
                                                               monkeypatch):
    """The old region guard is gone: the whole row behaves alike.

    Double-click used to bail out inside the checkbox cell. On the old code
    that left the row selected (one toggle, never undone); now the checkbox
    cell behaves like every other cell and the link opens from anywhere.
    """
    window = make_window()
    iid = window.tree.get_children("")[0]
    window.links[Path(iid)] = "https://youtu.be/xyz789"
    opened = []
    monkeypatch.setattr("obs_youtube_uploader.app.webbrowser.open", opened.append)

    _double_click(window.tree, iid, "#0")

    assert opened == ["https://youtu.be/xyz789"]
    assert _state(window, iid)[0] is False
