import pytest
from obs_youtube_uploader import bookmarks


def test_there_are_twenty_one_binds():
    """All 21 the standalone script had. Copy and Paste were cut in the
    first port and restored: the handlers are two lines each
    (111unified.ahk:988-995) and the corp uses them."""
    assert len(bookmarks.BIND_IDS) == 21
    assert "Copy" in bookmarks.BIND_IDS
    assert "Paste" in bookmarks.BIND_IDS
    assert len(set(bookmarks.BIND_IDS)) == 21


def test_copy_paste_and_setroot_are_the_global_binds():
    """RefreshHotkeys Step 4 (111unified.ahk:763-771) registers exactly
    these three outside the per-window loop. They fire in every
    application, which is the one thing about them a user must be told."""
    assert bookmarks.GLOBAL_BIND_IDS == {"Copy", "Paste", "SetRoot"}
    assert bookmarks.GLOBAL_BIND_IDS < set(bookmarks.BIND_IDS)


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
    others = {k: v for k, v in bookmarks.DEFAULT_BINDS.items()
              if k != "ConvertScout"}
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
    """"+^h" and "^+h" are the same physical hotkey; RefreshHotkeys only
    reports this as a silent ErrorLevel at registration, which is the
    failure this check exists to catch before it gets there."""
    binds = dict(bookmarks.DEFAULT_BINDS, FinH="^+h", FinL="+^h")
    assert bookmarks.collisions(binds) == {"^+h": ["FinH", "FinL"]}


def test_parse_ahk_accepts_a_typed_string():
    """The manual escape hatch for non-US layouts, validated by the same
    rules as capture."""
    assert bookmarks.parse_ahk("^+s") == {
        "ahk": "^+s", "display": "Ctrl+Shift+S", "error": None}


def test_parse_ahk_normalises_modifier_order():
    assert bookmarks.parse_ahk("+^s")["ahk"] == "^+s"


@pytest.mark.parametrize("text", ["", "^", "^!+#", "   "])
def test_parse_ahk_rejects_modifier_only(text):
    assert bookmarks.parse_ahk(text)["error"] == "modifier-only"


def test_parse_ahk_rejects_unknown_key():
    assert bookmarks.parse_ahk("^Nope")["error"] == "unmappable"
