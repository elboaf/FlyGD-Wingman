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


def test_the_groups_partition_every_bind_exactly_once():
    """Round 5, C8. The route renders one block per group, so a bind that
    fell through the derivation would not be shown at all -- and the screen
    it disappeared from is one that already looks finished with no rows in
    it at all (see tests/test_dev_harness.py's module docstring)."""
    groups = bookmarks.bind_groups()
    seen = [bid for group in groups for bid in group["ids"]]
    assert seen == list(bookmarks.BIND_IDS), (
        "bind_groups() dropped, duplicated or re-ordered a bind"
    )
    for group in groups:
        assert set(group["short"]) == set(group["ids"])


def test_the_group_shorts_are_the_labels_with_the_shared_token_lifted():
    """The point of the split: the ten finishers opened with the same five
    characters, which is why the route spent 618px of an 1112px card on
    them. The heading carries the token now, so the SHORT label must be the
    full one minus exactly that token -- if it is not, the block is a
    second set of names for the same binds rather than the same names
    read once."""
    groups = {group["name"]: group for group in bookmarks.bind_groups()}
    assert set(groups) == {"", "Finishers", "Tags"}

    for bid, short in groups["Finishers"]["short"].items():
        assert bookmarks.BIND_LABELS[bid] == "Finisher: " + short
    for bid, short in groups["Tags"]["short"].items():
        assert bookmarks.BIND_LABELS[bid].replace(" Tag", "", 1) == short
    # The leading group heads nothing, so nothing is lifted out of it and
    # its rows render at full length exactly as they always did.
    for bid, short in groups[""]["short"].items():
        assert bookmarks.BIND_LABELS[bid] == short


def test_labels_that_share_no_token_fall_back_to_one_flat_group(monkeypatch):
    """The failure mode for a fork is the OLD screen, not a broken one.
    PRODUCT.md makes BIND_LABELS the table a fork rewrites for its own
    house style; a fork whose scheme has no shared prefix gets a single
    unnamed group, which renders as the flat list this replaced."""
    monkeypatch.setattr(
        bookmarks,
        "BIND_LABELS",
        {bid: bid.upper() for bid in bookmarks.BIND_IDS},
    )
    groups = bookmarks.bind_groups()
    assert len(groups) == 1
    assert groups[0]["name"] == ""
    assert groups[0]["ids"] == list(bookmarks.BIND_IDS)


def test_a_group_marker_that_stops_being_contiguous_cannot_reorder_the_list(
    monkeypatch,
):
    """CodeRabbit caught this, and it is worth the test rather than only the
    fix: the first version accumulated into one bucket per group NAME, so a
    fork that renamed only its LAST tag -- leaving it matching neither
    marker -- dropped that id into the unnamed bucket the first action had
    opened, and it then rendered fourth, ahead of every finisher.

    BIND_IDS is the route's display order (see its own comment), so a
    silent reorder is a user-visible defect with nothing on screen to show
    it happened. Segmenting contiguously makes the output BIND_IDS with
    dividers inserted and nothing else, which is what this asserts."""
    labels = dict(bookmarks.BIND_LABELS)
    labels["FinC"] = "Critical"  # no "Finisher: " and no " Tag"
    monkeypatch.setattr(bookmarks, "BIND_LABELS", labels)

    groups = bookmarks.bind_groups()
    assert [bid for group in groups for bid in group["ids"]] == list(bookmarks.BIND_IDS)
    # The renamed tag opens its OWN trailing unnamed group rather than
    # joining the leading one.
    assert [(g["name"], len(g["ids"])) for g in groups] == [
        ("", 4),
        ("Finishers", 10),
        ("Tags", 3),
        ("", 1),
    ]
