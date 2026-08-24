import pytest
from obs_youtube_uploader import bookmarks


def test_there_are_nineteen_binds():
    """19 of the standalone script's 21. Copy and Paste are gone: their
    handlers were Send ^c and Send ^v (111unified.ahk:988-995), so they
    spent a global keyboard hook on what Windows already does."""
    assert len(bookmarks.BIND_IDS) == 19
    assert "Copy" not in bookmarks.BIND_IDS
    assert "Paste" not in bookmarks.BIND_IDS
    assert len(set(bookmarks.BIND_IDS)) == 19


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
