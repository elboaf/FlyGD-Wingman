"""Structural checks on the two-pane layout, against real widgets.

These assert the things a refactor of _build can silently break — a
control that stopped being created, a panel that stopped being fixed
width, content pushed past the bottom edge — and nothing that depends on
font rendering.
"""
import tkinter as tk

import pytest

from obs_youtube_uploader import app


def _labelled(widget):
    """Every text label in the widget subtree, flattened."""
    found = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except tk.TclError:
            text = ""
        if text:
            found.append(str(text))
        found.extend(_labelled(child))
    return found


def test_every_moved_control_still_exists(make_window):
    window = make_window()
    texts = _labelled(window.root)
    for label in ("Upload", "Title", "Description", "Stitch selected videos",
                  "Upload combat logs", "Retry", "Upload Selected",
                  "Select All", "Select None", "Delete Selected", "Settings"):
        assert label in texts, f"{label} disappeared in the restructure"


def test_upload_controls_live_in_the_panel(make_window):
    # Adjacency is the point of the redesign: the button that consumes the
    # fields must be in the same pane as the fields.
    window = make_window()
    panel_texts = _labelled(window.upload_panel)
    assert "Upload Selected" in panel_texts
    assert "Upload combat logs" in panel_texts
    assert "Retry" in panel_texts
    assert window.desc_txt.winfo_parent() == str(window.upload_panel)
    assert window.stitch_chk.winfo_parent() == str(window.upload_panel)
    # ...and the list commands must NOT have followed them there.
    assert "Delete Selected" not in panel_texts


def test_every_command_is_bound(make_window):
    window = make_window()

    def commands(widget):
        out = []
        for child in widget.winfo_children():
            try:
                out.append((str(child.cget("text")), str(child.cget("command"))))
            except tk.TclError:
                pass
            out.extend(commands(child))
        return out

    bound = {text: cmd for text, cmd in commands(window.root) if text}
    for label in ("Settings", "Select All", "Select None", "Delete Selected",
                  "Upload combat logs", "Retry", "Upload Selected"):
        assert bound.get(label), f"{label} lost its command binding"


@pytest.mark.parametrize("dpi,scale", [(96, 1.0), (144, 1.5), (192, 2.0)])
def test_panel_width_is_fixed_and_scales(make_window, dpi, scale):
    window = make_window(dpi=dpi)
    assert window.upload_panel.winfo_width() == int(300 * scale)
    # The list gets everything else, so it must still be the larger pane at
    # the default geometry.
    assert window.tree.winfo_width() > window.upload_panel.winfo_width()


def test_description_absorbs_panel_slack(make_window):
    window = make_window()
    # height=3 is a floor; the weighted row makes the real box much taller.
    assert window.desc_txt.winfo_height() > 3 * 20


def test_nothing_is_clipped_at_the_minimum_window_size(make_window):
    """The action row must still fit inside the panel at the window floor.

    grid shrinks the weighted Description row first; only once that is gone
    does fixed content start falling off the bottom, which is what this
    catches.
    """
    window = make_window()
    root = window.root
    root.update()
    min_w, min_h = root.wm_minsize()
    root.geometry(f"{int(min_w)}x{int(min_h)}")
    root.update()
    actions = window.retry_btn.master
    # Mapped, not merely positioned: grid unmaps a slave it cannot fit, and
    # an unmapped frame reports the geometry it last had, which would sail
    # through the bounds check below while being invisible on screen.
    assert actions.winfo_ismapped()
    bottom = actions.winfo_rooty() + actions.winfo_height()
    assert bottom <= window.upload_panel.winfo_rooty() + window.upload_panel.winfo_height()
    assert window.tree.winfo_width() > 0


def test_no_column_is_clipped_at_the_minimum_window_size(make_window):
    """Every column present and inside the viewport at the window floor.

    Measured, not reasoned about: this is the check that caught the design's
    false arithmetic. With the pre-fix 750px floor the tree viewport was
    381px against the 490px the columns need — `Length` was 76% clipped and
    `Link` began 58px past the right edge. The floor is now 860px, giving
    491px.
    """
    window = make_window()
    root = window.root
    root.update()
    min_w, min_h = root.wm_minsize()
    root.geometry(f"{int(min_w)}x{int(min_h)}")
    root.update()

    tree = window.tree
    viewport = tree.winfo_width()
    iid = tree.get_children("")[0]
    for key, *_rest in app.COLUMN_SPEC:
        box = tree.bbox(iid, key)
        assert box, f"{key} has no bbox at the window floor"
        left, _top, width, _height = box
        assert width > 0, key
        assert left >= 0, f"{key} starts left of the viewport"
        assert left + width <= viewport, (
            f"{key} runs {left + width - viewport}px past the right edge")


def test_only_the_filename_column_grows_on_a_wide_window(make_window):
    """`filename` is the only stretching column, so it takes the whole surplus.

    Guards the rejected alternative: making date/size/duration stretch so a
    deficit could reach their minimums also handed them an equal share of
    every SURPLUS (Size reached 344px at 1920), which is what this asserts
    cannot happen.
    """
    window = make_window()
    root = window.root
    root.update()
    root.geometry("1350x650")
    root.update()
    root.update()  # the <Configure> handler runs on the second pass

    tree = window.tree
    for key, _t, _s, preferred, _m, _st, _a in app.COLUMN_SPEC:
        if key == "filename":
            continue
        assert tree.column(key, "width") == int(preferred * window._dpi_scale), key
    assert tree.column("filename", "width") > int(260 * window._dpi_scale)


def test_no_column_is_clipped_after_widening_and_narrowing_back(make_window):
    """Both drag directions, since a layout can be path-dependent.

    Replaces a test of the removed _fit_columns regime flag. That flag is
    gone, but the property it was protecting is not: ttk redistributes from
    whatever the current widths happen to be, so a return trip is a
    different code path from the outbound one and worth its own check.
    """
    window = make_window()
    root = window.root
    root.update()
    min_w, min_h = root.wm_minsize()

    root.geometry("1350x650")
    root.update()
    root.geometry(f"{int(min_w)}x{int(min_h)}")
    root.update()

    tree = window.tree
    viewport = tree.winfo_width()
    iid = tree.get_children("")[0]
    for key, *_rest in app.COLUMN_SPEC:
        box = tree.bbox(iid, key)
        assert box, f"{key} has no bbox after the return trip"
        left, _top, width, _height = box
        assert left >= 0 and left + width <= viewport, (
            f"{key} is clipped after widening and narrowing back")
    # And the fixed columns came back to exactly where they started.
    for key, _t, _s, preferred, _m, stretch, _a in app.COLUMN_SPEC:
        if stretch:
            continue
        assert tree.column(key, "width") == int(preferred * window._dpi_scale), key


def test_ffmpeg_warning_sits_under_stitch_and_wraps(make_window):
    window = make_window(ffmpeg_bin=None)
    assert window.ffmpeg_warn_label is not None
    assert window.stitch_chk.instate(["disabled"])
    assert window.ffmpeg_warn_label.winfo_parent() == str(window.upload_panel)
    # Below the checkbox it explains, and constrained to the panel — an
    # unwrapped label would be silently clipped by grid_propagate(False).
    assert window.ffmpeg_warn_label.grid_info()["row"] > window.stitch_chk.grid_info()["row"]
    assert 0 < window.ffmpeg_warn_label.cget("wraplength") <= window._panel_width


def test_no_ffmpeg_warning_when_ffmpeg_is_present(make_window):
    window = make_window(ffmpeg_bin="/usr/bin/ffmpeg")
    assert window.ffmpeg_warn_label is None
    assert not window.stitch_chk.instate(["disabled"])


def test_description_box_is_painted_from_tokens(make_window):
    from obs_youtube_uploader import theme

    window = make_window()
    assert window.desc_txt.cget("background") == theme.token("ROW_EVEN")
    assert window.desc_txt.cget("relief") == "solid"


def test_description_box_follows_a_live_theme_switch(make_window):
    """The repaint is deferred, so only a second update() proves it stuck.

    tk_setPalette runs one tick after the switch and resets this classic
    widget; reading back immediately would pass even without the deferral.
    """
    from obs_youtube_uploader import theme

    window = make_window()
    theme.apply(window.root, "light")
    window.root.update()
    window.root.update()
    assert window.desc_txt.cget("background") == theme.token("ROW_EVEN", "light")
    assert window.desc_txt.cget("foreground") == theme.token("FG", "light")
