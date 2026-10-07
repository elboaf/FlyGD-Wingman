"""Bridge slice of #319: the chord is the consent gate.

The card records the Discord Toggle-Screen-Share keybind through the one
ADR 0002 seam -- ``capture_bind``, the same resolution the Bookmarks rows
use, so the two capture consumers cannot disagree about what a key
produces -- and persists it through ``stream_chord_set``. Presence of the
chord IS the enabled state: no checkbox, the empty string is the explicit
off, and a chord the notation cannot spell must never survive anywhere it
could fire.

The layout-awareness acceptance rides the shared seam rather than
re-testing it: on Linux these tests exercise capture_bind's
position-fallback leg (no Win32 view), and tests/test_keylayout.py holds
the produced-character leg (Dvorak position -> layout letter) the same
call resolves on Windows.
"""

import json

from tests.test_api import make_api
from wingman import paths, settings


def test_capture_then_set_round_trip(tmp_path, monkeypatch):
    """The flow the card performs: resolve the keydown through the shared
    seam, then persist exactly what it produced. bridge_view is stubbed to
    None so the deterministic position leg runs everywhere -- KeyD with
    Ctrl+Alt is ^!d by position, the same answer the layout path gives
    when the position produces 'd'."""
    from wingman import keylayout

    monkeypatch.setattr(keylayout, "bridge_view", lambda: None)
    api = make_api(tmp_path)
    resolved = api.capture_bind(
        {"ctrl": True, "alt": True, "shift": False, "meta": False, "code": "KeyD"}
    )
    assert resolved["error"] is None
    assert resolved["ahk"] == "^!d"
    stored = api.stream_chord_set(resolved["ahk"])
    assert stored["ok"] is True
    assert stored["chord"] == "^!d"
    # The display is derived Python-side (the bookmarks rule: the page
    # holds no notation table of its own).
    assert stored["chord_display"] == "Ctrl+Alt+D"


def test_the_stored_chord_is_what_the_layout_produced(tmp_path):
    """The ADR 0002 acceptance, machine-honest: capture_bind consults
    whatever layout this box's foreground thread carries, and the chord
    stores exactly what it produced -- a Dvorak box records the key the
    user pressed, not the hardware keycode's QWERTY letter. The
    assertion is the round trip, not a spelled chord."""
    api = make_api(tmp_path)
    resolved = api.capture_bind(
        {"ctrl": True, "alt": True, "shift": False, "meta": False, "code": "KeyD"}
    )
    assert resolved["error"] is None
    stored = api.stream_chord_set(resolved["ahk"])
    assert stored["ok"] is True
    assert stored["chord"] == resolved["ahk"]
    assert stored["chord_display"]


def test_set_persists_across_a_restart(tmp_path):
    api = make_api(tmp_path)
    assert api.stream_chord_set("^+s")["ok"] is True
    fresh = settings.load()
    coupling = fresh["preview"]["alerts"]["stream_coupling"]
    assert coupling["chord"] == "^+s"


def test_clear_is_an_explicit_off(tmp_path):
    api = make_api(tmp_path)
    assert api.stream_chord_set("^!d")["ok"] is True
    cleared = api.stream_chord_set("")
    assert cleared["ok"] is True
    assert cleared["chord"] == ""
    assert cleared["chord_display"] == ""
    assert settings.load()["preview"]["alerts"]["stream_coupling"]["chord"] == ""


def test_refuses_a_chord_the_notation_cannot_spell(tmp_path):
    """The write path applies the same parser the validator does: a value
    that would fall back alone on load never gets stored in the first
    place, and the refused write leaves the previous chord standing."""
    api = make_api(tmp_path)
    assert api.stream_chord_set("^!d")["ok"] is True
    refused = api.stream_chord_set("nonsense")
    assert refused["ok"] is False
    assert refused["error"]
    # The stored chord survives the refused write.
    assert api.stream_mirror_state()["chord"] == "^!d"
    # Modifier-only notation names no key either.
    assert api.stream_chord_set("^")["ok"] is False
    assert api.stream_chord_set("!")["ok"] is False


def test_a_non_string_argument_writes_nothing(tmp_path):
    """Only an explicit empty string may clear consent: a type mismatch
    must neither invent a chord nor silently erase the user's recorded
    one."""
    api = make_api(tmp_path)
    assert api.stream_chord_set("^!d")["ok"] is True
    for junk in (None, 17, {"ahk": "^!d"}):
        result = api.stream_chord_set(junk)
        assert result["ok"] is False
    assert api.stream_mirror_state()["chord"] == "^!d"


def test_the_write_canonicalises_spelling(tmp_path):
    """parse_ahk is the same entry the hand-typed Edit... path uses, so a
    chord arriving loose (" f007 ") is stored the way the trigger will
    spell it (F7), not the way it arrived."""
    api = make_api(tmp_path)
    stored = api.stream_chord_set(" f007 ")
    assert stored["ok"] is True
    assert stored["chord"] == "F7"


def test_payload_carries_chord_fields_even_without_a_supervisor(tmp_path):
    """Linux/dev builds construct no supervisor; the consent fields are
    settings state, not process state, and ride the same payload either
    way -- the card renders one read, not two."""
    api = make_api(tmp_path)
    assert api.stream_mirror_state()["available"] is False
    assert api.stream_chord_set("^!d")["ok"] is True
    state = api.stream_mirror_state()
    assert state["available"] is False
    assert state["chord"] == "^!d"
    assert state["chord_display"] == "Ctrl+Alt+D"


def test_an_unspellable_stored_chord_renders_as_no_chord(tmp_path):
    """A chord the notation cannot spell never fires, and the card never
    shows one: load's validator drops it ALONE end-to-end from the file an
    older build wrote, and the payload's own derivation renders an
    unspellable chord as no display -- the same as nothing to fire."""
    raw = {
        "preview": {
            "alerts": {
                "stream_coupling": {
                    "chord": "junk!!",
                    "quiet_s": 120,
                    "mirror_on": True,
                }
            }
        }
    }
    paths.settings_file().parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file().write_text(json.dumps(raw), encoding="utf-8")
    coupling = settings.load()["preview"]["alerts"]["stream_coupling"]
    assert coupling == {"chord": "", "quiet_s": 120, "mirror_on": True}

    api = make_api(tmp_path)
    api._state.settings.setdefault("preview", {}).setdefault("alerts", {}).setdefault(
        "stream_coupling", {}
    )["chord"] = "junk!!"
    state = api.stream_mirror_state()
    assert state["chord"] == "junk!!"
    assert state["chord_display"] == ""


def test_the_stored_document_round_trips_through_load(tmp_path):
    """A written chord survives load's validator byte-for-byte: the write
    path already canonicalised it, so the validator has nothing to drop."""
    api = make_api(tmp_path)
    api.stream_chord_set("^!d")
    on_disk = json.loads(paths.settings_file().read_text(encoding="utf-8"))
    assert on_disk["preview"]["alerts"]["stream_coupling"]["chord"] == "^!d"
    assert settings.load()["preview"]["alerts"]["stream_coupling"]["chord"] == "^!d"
