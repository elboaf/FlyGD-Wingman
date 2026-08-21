"""Structural checks on the two-pane layout, against real widgets.

These assert the things a refactor of _build can silently break — a
control that stopped being created, a panel that stopped being fixed
width, content pushed past the bottom edge — and nothing that depends on
font rendering.
"""
import tkinter as tk

import pytest


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
    bottom = actions.winfo_rooty() + actions.winfo_height()
    assert bottom <= window.upload_panel.winfo_rooty() + window.upload_panel.winfo_height()
    assert window.tree.winfo_width() > 0


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
