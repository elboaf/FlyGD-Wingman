import logging
from pathlib import Path
from unittest.mock import patch

from obs_youtube_uploader import paths, settings
from obs_youtube_uploader.__main__ import configure_logging, resolve_recording_dir


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


def test_configure_logging_redacts_webhook_token_from_foreign_logger(tmp_path, monkeypatch):
    """The redaction filter must be attached to the HANDLER, not a logger, so
    it also catches records from libraries we never touch directly (e.g. an
    HTTP transport logging a request URL at DEBUG). A filter on our own
    logger would never see those records -- this proves the control is
    actually live, not just unit-tested in isolation."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths.ensure_dirs()

    token = "supersecrettoken1234567890abcdef1234567890abcdef1234567890abcd"
    webhook_url = f"https://discord.com/api/webhooks/123456789012345678/{token}"
    settings.save({**settings.DEFAULTS, "discord_webhook": webhook_url})

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    # configure_logging() calls setLevel(INFO) on the root logger. Restoring
    # the handlers but not the level would leak that into every test that
    # runs after this one.
    original_level = root_logger.level
    try:
        configure_logging()
        handler = root_logger.handlers[-1]

        foreign_logger = logging.getLogger("some.third.party.transport")
        foreign_logger.warning("GET %s", webhook_url)
        handler.flush()

        log_path = paths.log_dir() / "uploader_debug.log"
        contents = log_path.read_text(encoding="utf-8")
    finally:
        for h in list(root_logger.handlers):
            if h not in original_handlers:
                root_logger.removeHandler(h)
                h.close()
        root_logger.setLevel(original_level)

    assert token not in contents
    assert "GET" in contents
