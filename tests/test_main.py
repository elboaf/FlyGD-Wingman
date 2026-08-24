import logging
from types import SimpleNamespace
from unittest.mock import patch

from obs_youtube_uploader import __main__ as main_mod
from obs_youtube_uploader import paths, settings
from obs_youtube_uploader.__main__ import (
    configure_logging,
    resolve_recording_dir,
    set_dpi_awareness,
)


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
        result = resolve_recording_dir(cfg)

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
        result = resolve_recording_dir(cfg)

    assert result == detected_dir


def test_no_stored_value_falls_through_to_detection(tmp_path):
    detected_dir = tmp_path / "detected"
    detected_dir.mkdir()
    cfg = {}

    with patch("obs_youtube_uploader.__main__.obsconfig.find_recording_dir",
               return_value=detected_dir):
        result = resolve_recording_dir(cfg)

    assert result == detected_dir


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


class _FakeShcore:
    def __init__(self, exc=None):
        self._exc = exc
        self.calls = []

    def SetProcessDpiAwareness(self, value):
        if self._exc is not None:
            raise self._exc
        self.calls.append(value)


def _fake_windll(monkeypatch, **modules):
    import ctypes
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(**modules), raising=False)


def test_set_dpi_awareness_is_a_silent_no_op_off_windows():
    """Must not raise: it is the very first statement in main(), so anything
    it throws off-Windows blocks startup entirely during development."""
    with patch("sys.platform", "linux"):
        assert set_dpi_awareness() is None


def test_set_dpi_awareness_requests_system_dpi_aware_not_per_monitor(monkeypatch):
    """1 == PROCESS_SYSTEM_DPI_AWARE. Per-Monitor (2) is deliberately NOT
    used: it would require handling WM_DPICHANGED when the window moves
    between monitors of different scale."""
    shcore = _FakeShcore()
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, shcore=shcore)
        set_dpi_awareness()
    assert shcore.calls == [1]


def test_set_dpi_awareness_degrades_when_shcore_is_missing(monkeypatch):
    """shcore.dll predates Windows 8.1. A missing DLL must leave the process
    DPI-unaware, never prevent it from starting."""
    with patch("sys.platform", "win32"):
        _fake_windll(monkeypatch, shcore=_FakeShcore(exc=OSError("no shcore.dll")))
        assert set_dpi_awareness() is None


# --- Log level ---------------------------------------------------------------
#
# The Windows-only half of the preview subsystem is verified by a manual
# checklist, so when it breaks in the field the log is the only evidence.
# Several of its load-bearing diagnostics are logger.debug -- whether
# WM_HOTKEY reached the message-only window, whether the thread's DPI
# override was accepted, why a placement read failed -- and INFO discards
# every one of them. Without a way to raise the level, a checklist item
# that says "check the log for the DPI override result" cannot be walked
# at all.


def test_log_level_defaults_to_info():
    assert main_mod._log_level() == logging.INFO


def test_log_level_honours_the_environment(monkeypatch):
    monkeypatch.setenv("WINGMAN_LOG_LEVEL", "DEBUG")
    assert main_mod._log_level() == logging.DEBUG


def test_log_level_is_case_and_space_insensitive(monkeypatch):
    monkeypatch.setenv("WINGMAN_LOG_LEVEL", "  debug ")
    assert main_mod._log_level() == logging.DEBUG


def test_an_unrecognised_log_level_falls_back_to_info(monkeypatch):
    """logging.getLevelName returns the STRING 'Level BANANAS' for an
    unknown name rather than raising, and setLevel would then reject it.
    A typo in an env var must not take logging down at startup."""
    monkeypatch.setenv("WINGMAN_LOG_LEVEL", "BANANAS")
    assert main_mod._log_level() == logging.INFO


def test_an_empty_log_level_falls_back_to_info(monkeypatch):
    monkeypatch.setenv("WINGMAN_LOG_LEVEL", "")
    assert main_mod._log_level() == logging.INFO


def test_configure_logging_applies_the_requested_level(tmp_path, monkeypatch):
    """End to end: a debug record must actually reach the file, not merely
    be permitted by _log_level()."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("WINGMAN_LOG_LEVEL", "DEBUG")
    paths.ensure_dirs()

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    try:
        configure_logging()
        assert root_logger.level == logging.DEBUG
        logging.getLogger("preview.probe").debug("dpi override accepted")
        root_logger.handlers[-1].flush()
        contents = (paths.log_dir() / "uploader_debug.log").read_text(
            encoding="utf-8")
    finally:
        for h in list(root_logger.handlers):
            if h not in original_handlers:
                root_logger.removeHandler(h)
                h.close()
        root_logger.setLevel(original_level)

    assert "dpi override accepted" in contents

