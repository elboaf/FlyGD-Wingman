from pathlib import Path
from unittest.mock import patch

from obs_youtube_uploader.__main__ import resolve_recording_dir


def _unreachable_ask(**kwargs):
    """Fails the test if reached -- proves a branch didn't fall through to
    asking the user."""
    raise AssertionError("filedialog.askdirectory should not have been called")


def test_stored_value_wins_over_detection(tmp_path):
    """A valid stored dir must win even when detection disagrees -- this is
    the precedence bug: prove it's actually exercised, not trivially true
    because detection would return the same thing."""
    stored_dir = tmp_path / "stored"
    stored_dir.mkdir()
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {"recording_dir": str(stored_dir)}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir) as mock_detect:
        result = resolve_recording_dir(cfg, ask=_unreachable_ask)

    assert result == stored_dir
    mock_detect.assert_not_called()


def test_stale_stored_value_falls_through_to_detection(tmp_path):
    """A stored dir that no longer exists (e.g. a drive unplugged, or -- as
    happened for real -- a wrong folder saved before a detection bug was
    fixed) must not be trusted; detection must run instead."""
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {"recording_dir": str(tmp_path / "does-not-exist")}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir):
        result = resolve_recording_dir(cfg, ask=_unreachable_ask)

    assert result == detected_dir


def test_no_stored_value_falls_through_to_detection(tmp_path):
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir):
        result = resolve_recording_dir(cfg, ask=_unreachable_ask)

    assert result == detected_dir


def test_no_stored_value_and_no_detection_asks_user(tmp_path):
    chosen_dir = tmp_path / "chosen"
    chosen_dir.mkdir()
    cfg = {}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=None):
        result = resolve_recording_dir(cfg, ask=lambda **kwargs: str(chosen_dir))

    assert result == chosen_dir
