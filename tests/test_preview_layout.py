"""Layout persistence, pure. Mirrors settings.py's posture: a malformed
stored value must fall back, never raise -- a corrupt layout key should
cost you one preview's position, not the app's launch."""
from obs_youtube_uploader.preview import layout
from obs_youtube_uploader.preview.geometry import Rect


def test_round_trips():
    entries = {"Pilot One": layout.Entry(Rect(10, 20, 320, 210), locked=False)}
    assert layout.deserialize(layout.serialize(entries)) == entries


def test_deserialize_ignores_a_malformed_entry_but_keeps_the_others():
    raw = {
        "Good": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": False},
        "Bad": {"x": "not-a-number", "y": 2, "w": 3, "h": 4},
    }
    out = layout.deserialize(raw)
    assert set(out) == {"Good"}


def test_deserialize_of_a_wrong_type_returns_empty():
    for raw in (None, [], "nope", 3):
        assert layout.deserialize(raw) == {}


def test_locked_defaults_to_false_when_absent():
    out = layout.deserialize({"P": {"x": 1, "y": 2, "w": 3, "h": 4}})
    assert out["P"].locked is False


def test_non_positive_sizes_are_rejected():
    """A zero-width stored rect would produce an invisible, undraggable
    preview that looks like the feature is broken."""
    assert layout.deserialize({"P": {"x": 1, "y": 2, "w": 0, "h": 4}}) == {}
