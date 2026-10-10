"""Probe #334: the STREAMING-detection and evidence-filtering helpers."""

from importlib import util
from pathlib import Path

_spec = util.spec_from_file_location(
    "discord_presence_probe",
    Path(__file__).resolve().parents[1] / "scripts" / "discord_presence_probe.py",
)
probe = util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def test_streaming_activity_detected():
    assert probe._is_streaming(
        [{"type": 1, "name": "Twitch", "url": "https://twitch.tv/x"}]
    )
    assert not probe._is_streaming([{"type": 0, "name": "EVE Online"}])
    assert not probe._is_streaming([])


def test_streaming_among_other_activities():
    activities = [
        {"type": 0, "name": "EVE Online"},
        {"type": 2, "name": "Spotify"},
        {"type": 1, "name": "Twitch", "url": "https://twitch.tv/x"},
    ]
    assert probe._is_streaming(activities)


def test_activity_line_carries_url_and_kind():
    line = probe._activity_line(
        {"type": 1, "name": "Twitch", "url": "https://twitch.tv/x"}
    )
    assert "STREAMING" in line and "https://twitch.tv/x" in line
    game = probe._activity_line({"type": 0, "name": "EVE Online", "url": None})
    assert "GAME" in game and "url=None" in game
