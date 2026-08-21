"""The selection summary, and the probe-completion path that keeps it fresh."""


def test_summary_is_refreshed_when_a_probe_lands(make_window):
    """REGRESSION: a summary wired only to selection changes goes stale.

    _apply_duration writes one Treeview cell and touches nothing else, so
    the partial-total "+" survives the very probe that completes the total
    unless _apply_duration recomputes the summary too.
    """
    window = make_window()
    probed, outstanding = window.infos[0], window.infos[1]
    probed.duration, probed.probed = 60.0, True
    outstanding.duration, outstanding.probed = None, False

    window._set_all(True)
    partial = window.selection_summary.cget("text")
    assert "+" in partial, "an outstanding probe must be marked partial"

    # The probe lands. Nothing else happens -- no refresh, no click.
    window._apply_duration(outstanding, 45.0, True)

    complete = window.selection_summary.cget("text")
    assert "+" not in complete, "summary went stale behind the probe"
    assert complete != partial


def test_toggling_one_row_updates_the_summary(make_window):
    window = make_window()
    window._set_all(False)
    empty = window.selection_summary.cget("text")
    window._toggle_row(str(window.infos[0].path))
    assert window.selection_summary.cget("text") != empty
    assert "1" in window.selection_summary.cget("text")


def test_select_all_and_none_update_the_summary(make_window):
    window = make_window()
    window._set_all(True)
    all_text = window.selection_summary.cget("text")
    assert str(len(window.infos)) in all_text
    window._set_all(False)
    assert window.selection_summary.cget("text") != all_text


def test_select_all_and_none_repaint_the_checkboxes(make_window):
    """REGRESSION: _set_all set the vars but not the row images.

    Nothing traces these BooleanVars, so the drawn checkbox is only ever
    updated where it is written. Before the fix the panel said "2 selected"
    while both boxes rendered empty — the summary made a pre-existing miss
    into a visible contradiction.

    Images are compared by identity against _checkbox_image, not by
    inspecting pixels: the two PhotoImages are cached per state, so the
    name Tk reports for a row is exactly one of them.
    """
    window = make_window()
    checked = str(window._checkbox_image(True))
    unchecked = str(window._checkbox_image(False))
    assert checked != unchecked

    for value, expected in ((True, checked), (False, unchecked)):
        window._set_all(value)
        for info in window.infos:
            drawn = window.tree.item(str(info.path), "image")
            # Tk returns the image list as a tuple (or a bare string).
            drawn = drawn[0] if isinstance(drawn, (tuple, list)) else drawn
            assert str(drawn) == expected, (info.path.name, value)


def test_refresh_rebuilds_the_summary_from_the_preselect(make_window):
    # The watcher's preselect arrives through refresh(), which rebuilds
    # self.selected wholesale -- the summary must follow that rebuild, not
    # the selection it had before it.
    window = make_window()
    window._set_all(True)
    window.refresh(preselect={window.infos[0].path})
    window._refresh_generation += 1  # stop the probe this refresh started
    text = window.selection_summary.cget("text")
    assert text.startswith("1 ")


def test_deleting_through_refresh_leaves_no_stale_count(make_window):
    window = make_window()
    window._set_all(True)
    for info in window.infos:
        info.path.unlink()
    window.refresh()
    window._refresh_generation += 1
    # format_selection_summary's own no-selection string (Task 2, pure and
    # already tested) is "Nothing selected" -- not "0 selected" and not "".
    # The point of this test is that refresh() actually recomputes the
    # summary from the now-empty selection rather than leaving the old
    # count sitting there.
    assert window.selection_summary.cget("text") == "Nothing selected"
