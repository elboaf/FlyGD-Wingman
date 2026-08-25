import pytest

from obs_youtube_uploader import bookmarks


def test_there_are_eighteen_binds():
    """18 of the standalone script's 21. Copy and Paste are gone -- their
    handlers were Send ^c and Send ^v (111unified.ahk:988-995), a global
    keyboard hook spent on what Windows already does -- and the medium-hole
    tag went with the helper author's own tag rework."""
    assert len(bookmarks.BIND_IDS) == 18
    for gone in ("Copy", "Paste", "FinM"):
        assert gone not in bookmarks.BIND_IDS
    assert len(set(bookmarks.BIND_IDS)) == 18


def test_the_tag_labels_name_the_character_the_engine_writes():
    """The labels are the only place a user learns which letter lands in
    the bookmark, so they have to move when the engine's does. FinS keeps
    its id on purpose: only the letter changed, and renaming the id would
    silently drop every existing binding for it."""
    assert bookmarks.BIND_LABELS["FinETag"].startswith("e ")
    assert bookmarks.BIND_LABELS["FinS"].startswith("f ")
    assert bookmarks.BIND_LABELS["FinC"].startswith("c ")
    assert "FinS" in bookmarks.BIND_IDS


def test_no_bind_is_advertised_as_global():
    """GLOBAL_BIND_IDS is gone along with the route's per-row scope marker.
    Every bind is registered inside the per-window loop now, so a set of
    exceptions reintroduced here would be describing something the engine
    no longer does -- and the route would start telling users a hotkey
    fires everywhere when it does not."""
    assert not hasattr(bookmarks, "GLOBAL_BIND_IDS")
    assert "SetRoot" in bookmarks.BIND_IDS


def test_recommended_binds_cover_every_id_without_colliding():
    """Offered behind one button that overwrites everything, so a gap would
    silently leave a bind blank and a duplicate would silently disable
    one of the two actions sharing it."""
    assert set(bookmarks.RECOMMENDED_BINDS) == set(bookmarks.BIND_IDS)
    assert not bookmarks.collisions(bookmarks.RECOMMENDED_BINDS)


def test_only_convertscout_has_a_default():
    """111unified.ahk:57,140 ships ^+s. Blanking it would silently take a
    working binding away from every existing user."""
    assert bookmarks.DEFAULT_BINDS["ConvertScout"] == "^+s"
    others = {k: v for k, v in bookmarks.DEFAULT_BINDS.items() if k != "ConvertScout"}
    assert set(others.values()) == {""}
    assert set(bookmarks.DEFAULT_BINDS) == set(bookmarks.BIND_IDS)


def test_no_collision_when_all_distinct():
    binds = dict(bookmarks.DEFAULT_BINDS, FinH="^h", FinL="^l")
    assert bookmarks.collisions(binds) == {}


def test_collision_is_reported_with_every_owner():
    """RefreshHotkeys registers with UseErrorLevel and silently lets one
    win (111unified.ahk:707-828); catching it here is the improvement."""
    binds = dict(bookmarks.DEFAULT_BINDS, FinH="^h", FinL="^h", FinN="^h")
    assert bookmarks.collisions(binds) == {"^h": ["FinH", "FinL", "FinN"]}


def test_blank_binds_never_collide():
    """Eighteen of nineteen ship blank; treating that as a 17-way collision
    would make the screen unusable on first run."""
    assert bookmarks.collisions(dict(bookmarks.DEFAULT_BINDS)) == {}


def test_collision_is_caught_across_modifier_order():
    """ "+^h" and "^+h" are the same physical hotkey; RefreshHotkeys only
    reports this as a silent ErrorLevel at registration, which is the
    failure this check exists to catch before it gets there."""
    binds = dict(bookmarks.DEFAULT_BINDS, FinH="^+h", FinL="+^h")
    assert bookmarks.collisions(binds) == {"^+h": ["FinH", "FinL"]}


def test_parse_ahk_accepts_a_typed_string():
    """The manual escape hatch for non-US layouts, validated by the same
    rules as capture."""
    assert bookmarks.parse_ahk("^+s") == {
        "ahk": "^+s",
        "display": "Ctrl+Shift+S",
        "error": None,
    }


def test_parse_ahk_normalises_modifier_order():
    assert bookmarks.parse_ahk("+^s")["ahk"] == "^+s"


@pytest.mark.parametrize("text", ["", "^", "^!+#", "   "])
def test_parse_ahk_rejects_modifier_only(text):
    assert bookmarks.parse_ahk(text)["error"] == "modifier-only"


def test_parse_ahk_rejects_unknown_key():
    assert bookmarks.parse_ahk("^Nope")["error"] == "unmappable"


class TestRegistrationBlockers:
    """Why a running engine would register no hotkeys at all.

    RegisterBind returns early on a blank key WITHOUT recording a failure
    (eve_bookmarks.ahk), and the per-window loop it sits in does not run at
    all when no window is enabled. Either way the engine comes up, writes a
    healthy status file with an empty failed_binds, and registers nothing --
    so the UI reports "Running", shows no warning, and every keypress does
    nothing. Indistinguishable from the feature being broken.

    Decided here rather than in the page because Wingman generates the INI
    and therefore knows what it would produce; the page only renders the
    answer. Same reasoning that had the engine publish root_mode rather
    than let the UI infer it from a human-readable string.
    """

    def test_a_working_setup_has_no_blockers(self):
        assert (
            bookmarks.registration_blockers(
                {"windows": {"EVE - Pilot": True}, "keybinds": {"FinH": "^y"}}
            )
            == []
        )

    def test_no_enabled_window_blocks_everything(self):
        """The per-window loop is the only place binds are registered, so
        with nothing ticked it never executes."""
        assert bookmarks.registration_blockers(
            {"windows": {}, "keybinds": {"FinH": "^y"}}
        ) == ["no_windows"]

    def test_a_window_present_but_unticked_still_blocks(self):
        """The INI carries `Title=0`, and the loop tests for "1"."""
        assert bookmarks.registration_blockers(
            {"windows": {"EVE - Pilot": False}, "keybinds": {"FinH": "^y"}}
        ) == ["no_windows"]

    def test_no_bound_key_blocks_everything(self):
        assert bookmarks.registration_blockers(
            {"windows": {"EVE - Pilot": True}, "keybinds": {"FinH": "", "FinL": "   "}}
        ) == ["no_binds"]

    def test_both_are_reported_together(self):
        """Fixing one would leave the user in exactly the same silence, so
        naming only the first would send them round twice."""
        assert bookmarks.registration_blockers(
            {"windows": {}, "keybinds": {"FinH": ""}}
        ) == ["no_windows", "no_binds"]

    def test_a_malformed_section_is_treated_as_blocked(self):
        """get_bookmarks passes the live settings section, and a
        hand-edited settings.json can carry anything. Claiming a working
        setup on the strength of a wrong type is the failure this check
        exists to prevent."""
        for section in (
            {},
            {"windows": None, "keybinds": None},
            {"windows": "x", "keybinds": 7},
        ):
            assert bookmarks.registration_blockers(section) == [
                "no_windows",
                "no_binds",
            ], section
